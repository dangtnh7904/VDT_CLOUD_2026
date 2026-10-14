from __future__ import annotations

import io
import threading
import unittest
from datetime import datetime, timedelta, timezone
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from app.modules.as_is.service import AsIsError, AsIsService
from app.services.performance import (
    PerformanceTelemetryError,
    PrometheusText,
    collect_ceph_samples,
    fetch_prometheus_text,
    parse_prometheus_counters,
    prometheus_identity_binding,
)
import test_as_is as fixtures


FSID = fixtures.FSID
ENDPOINT = 'http://metrics.invalid:9283/metrics'


def counters(*, value=100, fsid=None):
    binding = f',fsid="{fsid}"' if fsid else ''
    return '\n'.join(f'{name}{{ceph_daemon="osd.0"{binding}}} {value}'
        for name in ('ceph_osd_op_r', 'ceph_osd_op_w', 'ceph_osd_op_r_out_bytes', 'ceph_osd_op_w_in_bytes'))


class Response:
    def __init__(self, payload=b'', content_type='text/plain', status=200):
        self.payload = payload
        self.status = status
        self.headers = Message()
        self.headers['Content-Type'] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return self.payload[:limit]


class HttpDiagnosticsTests(unittest.TestCase):
    def fetch(self, response):
        with patch('app.services.performance._open_prometheus_request', return_value=response):
            return fetch_prometheus_text(ENDPOINT, bearer_token='PRIVATE-TOKEN')

    def test_success_keeps_http_status_without_changing_text_contract(self):
        result = self.fetch(Response(counters().encode()))
        self.assertIsInstance(result, str)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result, counters())

    def test_empty_invalid_content_oversize_and_encoding_have_distinct_safe_reasons(self):
        examples = [
            ('METRICS_RESPONSE_EMPTY', Response(b' \n')),
            ('METRICS_CONTENT_TYPE_INVALID', Response(b'PRIVATE-BODY', 'text/html')),
            ('METRICS_RESPONSE_TOO_LARGE', Response(b'x' * 65)),
            ('METRICS_ENCODING_INVALID', Response(b'\xff')),
        ]
        for code, response in examples:
            with self.subTest(code=code), patch('app.services.performance.MAX_PROMETHEUS_BYTES', 64):
                with self.assertRaises(PerformanceTelemetryError) as caught:
                    self.fetch(response)
                self.assertEqual(caught.exception.diagnostics(), {'quality': 'UNAVAILABLE', 'reason': code, 'http_status': 200})
                self.assertNotIn('PRIVATE', str(caught.exception))

    def test_http_error_preserves_only_status_and_closes_body(self):
        body = io.BytesIO(b'PRIVATE-ERROR-TOKEN')
        error = HTTPError('http://private.invalid/?token=secret', 503, 'PRIVATE-ERROR', {}, body)
        with patch('app.services.performance._open_prometheus_request', side_effect=error):
            with self.assertRaises(PerformanceTelemetryError) as caught:
                fetch_prometheus_text(ENDPOINT)
        self.assertEqual(caught.exception.diagnostics(), {'quality': 'UNAVAILABLE', 'reason': 'METRICS_HTTP_ERROR', 'http_status': 503})
        self.assertTrue(body.closed)
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertNotIn('token', str(caught.exception))

    def test_timeout_and_connection_failure_never_expose_raw_exception(self):
        for error, code in [(TimeoutError('PRIVATE-TIMEOUT'), 'METRICS_TIMEOUT'),
            (URLError(TimeoutError('PRIVATE-TIMEOUT')), 'METRICS_TIMEOUT'),
            (URLError('http://PRIVATE.invalid/secret'), 'METRICS_CONNECTION_FAILED')]:
            with self.subTest(code=code), patch('app.services.performance._open_prometheus_request', side_effect=error):
                with self.assertRaises(PerformanceTelemetryError) as caught:
                    fetch_prometheus_text(ENDPOINT)
                self.assertEqual(caught.exception.code, code)
                self.assertIsNone(caught.exception.http_status)
                self.assertNotIn('PRIVATE', str(caught.exception))

    def test_real_http_redirect_does_not_contact_destination_or_forward_bearer(self):
        destination_calls = []

        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                destination_calls.append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(counters().encode())

            def log_message(self, *args):
                pass

        destination = ThreadingHTTPServer(('127.0.0.1', 0), Destination)

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', f'http://127.0.0.1:{destination.server_port}/metrics')
                self.end_headers()

            def log_message(self, *args):
                pass

        source = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        threads = [threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
            for server in (source, destination)]
        for thread in threads:
            thread.start()
        try:
            with self.assertRaises(PerformanceTelemetryError) as caught:
                fetch_prometheus_text(f'http://127.0.0.1:{source.server_port}/metrics', bearer_token='PRIVATE-TOKEN')
            self.assertEqual(caught.exception.diagnostics(), {'quality': 'UNAVAILABLE', 'reason': 'METRICS_REDIRECT_REJECTED', 'http_status': 302})
            self.assertEqual(destination_calls, [])
        finally:
            for server in (source, destination):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=1)

    def test_parser_and_missing_counters_are_distinct(self):
        for payload, code in [
            ('', 'METRICS_RESPONSE_EMPTY'),
            ('<html>PRIVATE-TOKEN</html>', 'METRICS_PARSE_FAILED'),
            ('# TYPE ceph_health_status gauge\nceph_health_status 0', 'METRICS_OSD_COUNTERS_MISSING'),
            ('ceph_osd_op_r{ceph_daemon="osd.0",broken} 1', 'METRICS_PARSE_FAILED'),
            ('ceph_osd_op_r{ceph_daemon="osd.0"} -1', 'METRICS_INVALID_COUNTER'),
            ('ceph_osd_op_r{ceph_daemon="osd.0",fsid="x",fsid="y"} 1', 'METRICS_PARSE_FAILED'),
            (counters() + '\nceph_osd_op_r{ceph_daemon="osd.0"} 2', 'METRICS_DUPLICATE_SERIES'),
        ]:
            with self.subTest(code=code), self.assertRaises(PerformanceTelemetryError) as caught:
                parse_prometheus_counters(payload)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('PRIVATE', str(caught.exception))


class IdentityBindingTests(unittest.TestCase):
    def test_every_used_counter_series_requires_matching_source_label(self):
        self.assertEqual(prometheus_identity_binding(counters(fsid=FSID), FSID), 'source_fsid_labels')
        mixed = counters().replace('ceph_osd_op_r{ceph_daemon="osd.0"}', f'ceph_osd_op_r{{ceph_daemon="osd.0",fsid="{FSID}"}}')
        self.assertEqual(prometheus_identity_binding(mixed, FSID), 'unverified')
        self.assertEqual(prometheus_identity_binding(counters() + f'\n# fsid="{FSID}"', FSID), 'unverified')

    def test_mismatch_is_rejected_even_with_verified_service_endpoint(self):
        with self.assertRaises(PerformanceTelemetryError) as caught:
            prometheus_identity_binding(counters(fsid='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'), FSID,
                configured_url=ENDPOINT, verified_service_url=ENDPOINT)
        self.assertEqual(caught.exception.code, 'METRICS_FSID_MISMATCH')

    def test_verified_mgr_service_allows_normal_pacific_without_fsid_labels(self):
        self.assertEqual(prometheus_identity_binding(counters(), FSID, configured_url=ENDPOINT,
            verified_service_url='http://metrics.invalid:9283/'), 'verified_ceph_mgr_service_endpoint')
        self.assertEqual(prometheus_identity_binding(counters(), FSID,
            configured_url='https://METRICS.invalid/metrics', verified_service_url='https://metrics.invalid:443/'),
            'verified_ceph_mgr_service_endpoint')

    def test_endpoint_binding_rejects_different_host_port_scheme_path_and_credentials(self):
        for other in ['http://other.invalid:9283/', 'http://metrics.invalid:9284/',
            'https://metrics.invalid:9283/', 'http://metrics.invalid:9283/not-metrics',
            'http://user:secret@metrics.invalid:9283/', 'http://metrics.invalid:9283/?token=secret',
            'http://metrics.invalid:9283/#private', 'http://metrics.invalid:0/', None]:
            with self.subTest(endpoint=other):
                self.assertEqual(prometheus_identity_binding(counters(), FSID,
                    configured_url=ENDPOINT, verified_service_url=other), 'unverified')


class ObservationTelemetryTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AsIsTests()
        fixture.setUp()
        self.settings = fixture.settings.model_copy(update={
            'performance_source': 'prometheus', 'performance_prometheus_url': ENDPOINT})
        self.client = fixture.client
        self.repo = fixture.repo
        self.original_request = self.client.request

    def observe(self, fetcher, *, services=None, service_fsid=FSID, stale=False):
        def read(action, **kwargs):
            response = self.original_request(action, **kwargs)
            if action == 'ceph.mgr_services':
                response['data'] = services or {}
                response['fsid'] = service_fsid
                if stale:
                    response['collected_at'] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            if action == 'ceph.osd_df':
                response['data']['nodes'] = [response['data']['nodes'][0]]
            return response

        # This fixture isolates identity/diagnostics from the real 15s wait.
        # Advance past Windows' coarse monotonic tick so the mocked window is
        # positive; test_metric_window checks the real wait/cancellation rules.
        with patch.object(self.client, 'request', side_effect=read), \
             patch('app.modules.as_is.service.wait_for_metric_window',
                   side_effect=lambda control, *_: control.cancelled.wait(.03)):
            return AsIsService(self.settings, self.repo, self.client, fetcher).observe(daemon_keys=['osd.0'])

    def test_http_200_empty_source_is_reported_precisely_in_export_projection(self):
        fetcher = Mock(side_effect=PerformanceTelemetryError('METRICS_RESPONSE_EMPTY', http_status=200))
        result = self.observe(fetcher)
        self.assertEqual(result['sources']['prometheus'], {'quality': 'UNAVAILABLE', 'reason': 'METRICS_RESPONSE_EMPTY', 'http_status': 200})
        self.assertFalse(any(m['metric_id'].endswith('iops') for m in result['daemons'][0]['metrics']))

    def test_parser_failure_keeps_http_status_and_body_private(self):
        result = self.observe(Mock(return_value=PrometheusText('PRIVATE-NON-METRICS', http_status=200)))
        self.assertEqual(result['sources']['prometheus']['reason'], 'METRICS_PARSE_FAILED')
        self.assertEqual(result['sources']['prometheus']['http_status'], 200)
        self.assertNotIn('PRIVATE', str(result))

    def test_unbound_exporter_rates_stay_partial_without_cluster_aggregate(self):
        result = self.observe(Mock(side_effect=[PrometheusText(counters(), http_status=200), PrometheusText(counters(value=110), http_status=200)]))
        source = result['sources']['prometheus']
        self.assertEqual((source['quality'], source['identity_binding'], source['reason']),
            ('PARTIAL', 'unverified', 'TELEMETRY_IDENTITY_UNVERIFIED'))
        metrics = [m for m in result['daemons'][0]['metrics'] if m['metric_id'].endswith('iops')]
        self.assertTrue(metrics)
        self.assertTrue(all(m['quality'] == 'PARTIAL' and m['value'] is not None for m in metrics))
        self.assertFalse(any(m['metric_id'].endswith('iops') for m in result['system'].get('metrics', [])))

    def test_live_fsid_checked_mgr_service_binds_unlabelled_rates_and_cluster_total(self):
        result = self.observe(Mock(side_effect=[counters(), counters(value=110)]), services={'prometheus': 'http://metrics.invalid:9283/'})
        source = result['sources']['prometheus']
        self.assertEqual((source['quality'], source['identity_binding']), ('VALID', 'verified_ceph_mgr_service_endpoint'))
        self.assertTrue(any(m['metric_id'] == 'cluster.total_iops' for m in result['system']['metrics']))
        self.assertNotIn('metrics.invalid', str(result))

    def test_stale_services_cannot_bind_source(self):
        result = self.observe(Mock(side_effect=[counters(), counters(value=110)]),
            services={'prometheus': 'http://metrics.invalid:9283/'}, stale=True)
        self.assertEqual(result['sources']['prometheus']['identity_binding'], 'unverified')

    def test_services_with_different_fsid_are_rejected(self):
        with self.assertRaises(AsIsError) as caught:
            self.observe(Mock(return_value=counters()), services={'prometheus': ENDPOINT},
                service_fsid='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.assertEqual(caught.exception.code, 'FSID_MISMATCH')

    def test_second_scrape_failure_never_leaves_first_scrape_rates_or_values(self):
        result = self.observe(Mock(side_effect=[counters(fsid=FSID),
            PerformanceTelemetryError('METRICS_HTTP_ERROR', http_status=503)]))
        self.assertEqual(result['sources']['prometheus']['http_status'], 503)
        self.assertFalse(any(m['metric_id'].endswith('iops') for m in result['daemons'][0]['metrics']))

    def test_wall_clock_shift_does_not_publish_valid_rates(self):
        first_at = datetime.now(timezone.utc)
        reads = [dict(at=first_at, monotonic_at=100, text=counters(fsid=FSID),
                      counters={'0': {'read_ops':100,'write_ops':100,'read_bytes':100,'write_bytes':100}},
                      metric_names={}, http_status=200, identity_binding='source_fsid_labels'),
                 dict(at=first_at+timedelta(seconds=315), monotonic_at=115, text=counters(fsid=FSID),
                      counters={'0': {'read_ops':110,'write_ops':110,'read_bytes':110,'write_bytes':110}},
                      metric_names={}, http_status=200, identity_binding='source_fsid_labels')]
        with patch.object(AsIsService, '_scrape', side_effect=reads):
            result = self.observe(Mock())
        self.assertEqual(result['sources']['prometheus']['reason'], 'METRICS_CLOCK_SHIFT')
        self.assertEqual(result['sources']['prometheus']['http_status'], 200)
        self.assertFalse(any(m['metric_id'].endswith('iops') for m in result['daemons'][0]['metrics']))


class PeriodicTelemetryTests(unittest.TestCase):
    def test_periodic_collection_without_source_identity_remains_partial(self):
        settings = SimpleNamespace(performance_source='prometheus', performance_prometheus_url=ENDPOINT,
            performance_prometheus_bearer_token=None, ceph_expected_fsid=FSID)
        previous = {'read_ops': 90, 'write_ops': 90, 'read_bytes': 90, 'write_bytes': 90}
        captured = datetime.now(timezone.utc)
        with patch('app.services.performance.get_settings', return_value=settings), \
             patch('app.services.performance._latest_raw_counter_sample', return_value=(previous, captured - timedelta(seconds=10))), \
             patch('app.services.performance.store_sample') as store:
            samples = collect_ceph_samples(captured_at=captured,
                fetcher=Mock(return_value=PrometheusText(counters(), http_status=200)), db_conn=object())
        self.assertEqual(store.call_count, 2)
        self.assertTrue(all(row.partial for row in samples))
        self.assertTrue(all('TELEMETRY_IDENTITY_UNVERIFIED' in row.metadata['reasons'] for row in samples))
        self.assertTrue(all(row.metadata['http_status'] == 200 for row in samples))


if __name__ == '__main__':
    unittest.main()
