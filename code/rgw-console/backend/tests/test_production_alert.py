import contextlib
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import production_alert as alert


def report(status='ALERT', codes=None):
    return {'kind': 'PRODUCTION_OPERATIONS_PROBE', 'status': status,
            'alerts': (['HOST_DISK_HIGH'] if status == 'ALERT' else []) if codes is None else codes,
            'checked_at': alert.utc_now(), 'thresholds_status': 'PROPOSED_NOT_APPROVED',
            'checks': {'secret': 'NEVER_EXPORT_RAW_CHECKS', 'path': '/private/path'},
            'credentials': 'NEVER_EXPORT_CREDENTIALS'}


def private_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    path.chmod(0o600)


@contextlib.contextmanager
def receiver(status=200, body=b'{}', response_headers=None, drip_delay=0):
    events = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            events.append({'payload': json.loads(self.rfile.read(length)),
                           'headers': dict(self.headers), 'path': self.path})
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            for key, value in (response_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            try:
                if drip_delay:
                    for item in body:
                        self.wfile.write(bytes([item])); self.wfile.flush()
                        time.sleep(drip_delay)
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', events
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=1)


class ProductionAlertTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config_path = self.root / 'config.json'
        self.report_path = self.root / 'report.json'
        self.state_path = self.root / 'state.json'
        private_json(self.report_path, report())
        self.configure()

    def tearDown(self):
        self.temporary.cleanup()

    def configure(self, endpoint='https://receiver.example.test/alerts', **values):
        target = alert.parse_endpoint(endpoint, True)
        private_json(self.config_path, {'format_version': 1, 'endpoint': endpoint,
                                       'allowed_origin': target['origin'], **values})

    def loaded_config(self):
        return alert.load_config(self.config_path, True)

    def run_main(self, *extra):
        receipt = self.root / f'receipt-{len(list(self.root.glob("receipt-*.json")))}.json'
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = alert.main(['--config', str(self.config_path), '--report', str(self.report_path),
                               '--state', str(self.state_path), '--receipt', str(receipt), *extra])
        return code, json.loads(receipt.read_bytes()), output.getvalue()

    def test_payload_is_a_strict_redacted_projection(self):
        config = self.loaded_config()
        with patch.object(alert, 'send_webhook', return_value=204) as send:
            result = alert.deliver(report(), config, self.state_path, False)
        self.assertEqual(result['status'], 'DELIVERED')
        payload = send.call_args.args[1]
        self.assertEqual(set(payload), {'kind', 'status', 'alerts', 'checked_at', 'thresholds_proposed',
                                        'event', 'event_id', 'test_delivery', 'production_transport'})
        encoded = alert.canonical_bytes(payload).decode()
        self.assertNotIn('NEVER_EXPORT', encoded)
        self.assertNotIn('private/path', encoded)
        self.assertNotIn('receiver.example', encoded)
        self.assertTrue(payload['thresholds_proposed'])
        self.assertTrue(alert.HASH.fullmatch(payload['event_id']))

    def test_initial_pass_never_sends_or_creates_success_state(self):
        with patch.object(alert, 'send_webhook') as send:
            result = alert.deliver(report('PASS'), self.loaded_config(), self.state_path, False)
        self.assertEqual(result['status'], 'SKIPPED_PASS')
        send.assert_not_called()
        self.assertFalse(self.state_path.exists())

    def test_backup_kind_has_the_same_bounded_safe_projection(self):
        backup = dict(report(codes=['BACKUP_FAILED']), kind='PRODUCTION_MAINTENANCE_BACKUP',
                      backup_path='/DO_NOT_EXPORT_BACKUP_PATH', raw_error='DO_NOT_EXPORT_RAW_ERROR')
        with patch.object(alert, 'send_webhook', return_value=200) as send:
            alert.deliver(backup, self.loaded_config(), self.state_path, False)
        payload = send.call_args.args[1]
        self.assertEqual(payload['kind'], 'PRODUCTION_MAINTENANCE_BACKUP')
        self.assertEqual(payload['alerts'], ['BACKUP_FAILED'])
        self.assertNotIn('DO_NOT_EXPORT', alert.canonical_bytes(payload).decode())
        state = json.loads(self.state_path.read_bytes())
        self.assertEqual(state['report_kind'], 'PRODUCTION_MAINTENANCE_BACKUP')

    def test_state_cannot_emit_false_recovery_between_check_and_backup_kind(self):
        config = self.loaded_config()
        with patch.object(alert, 'send_webhook', return_value=200):
            alert.deliver(report(), config, self.state_path, False)
        original = self.state_path.read_bytes()
        backup = dict(report('PASS'), kind='PRODUCTION_MAINTENANCE_BACKUP')
        with patch.object(alert, 'send_webhook') as send, self.assertRaisesRegex(alert.AlertError, 'STATE_REPORT_KIND_MISMATCH'):
            alert.deliver(backup, config, self.state_path, False)
        send.assert_not_called()
        self.assertEqual(self.state_path.read_bytes(), original)

    def test_durable_dedup_ignores_timestamp_order_and_duplicates(self):
        config = self.loaded_config()
        with patch.object(alert, 'send_webhook', return_value=200) as send:
            alert.deliver(report(codes=['BACKUP_STALE', 'HOST_DISK_HIGH']), config, self.state_path, False)
            result = alert.deliver(report(codes=['HOST_DISK_HIGH', 'BACKUP_STALE', 'HOST_DISK_HIGH']),
                                   config, self.state_path, False)
        self.assertEqual(result['status'], 'SKIPPED_DUPLICATE')
        self.assertEqual(send.call_count, 1)

    def test_changed_alert_sends_new_event_and_recovery_only_once(self):
        config = self.loaded_config()
        with patch.object(alert, 'send_webhook', return_value=200) as send:
            alert.deliver(report(), config, self.state_path, False)
            alert.deliver(report(codes=['BACKUP_STALE']), config, self.state_path, False)
            recovered = alert.deliver(report('PASS'), config, self.state_path, False)
            skipped = alert.deliver(report('PASS'), config, self.state_path, False)
            alert.deliver(report(), config, self.state_path, False)
        self.assertEqual(recovered['event'], 'RECOVERY')
        self.assertEqual(skipped['status'], 'SKIPPED_PASS')
        payloads = [call.args[1] for call in send.call_args_list]
        self.assertEqual([payload['event'] for payload in payloads], ['ALERT', 'ALERT', 'RECOVERY', 'ALERT'])
        self.assertEqual(len(set(payload['event_id'] for payload in payloads)), 4)
        self.assertEqual(json.loads(self.state_path.read_bytes())['generation'], 4)

    def test_failed_delivery_never_commits_state_and_retry_id_is_stable(self):
        config = self.loaded_config()
        with patch.object(alert, 'send_webhook', side_effect=alert.AlertError('DELIVERY_TIMEOUT')) as send:
            with self.assertRaisesRegex(alert.AlertError, '^DELIVERY_TIMEOUT$'):
                alert.deliver(report(), config, self.state_path, False)
        self.assertFalse(self.state_path.exists())
        failed_id = send.call_args.args[1]['event_id']
        with patch.object(alert, 'send_webhook', return_value=200) as send:
            alert.deliver(report(), config, self.state_path, False)
        self.assertEqual(send.call_args.args[1]['event_id'], failed_id)

    def test_failed_recovery_does_not_suppress_next_recovery(self):
        config = self.loaded_config()
        with patch.object(alert, 'send_webhook', return_value=200):
            alert.deliver(report(), config, self.state_path, False)
        original = self.state_path.read_bytes()
        with patch.object(alert, 'send_webhook', side_effect=alert.AlertError('DELIVERY_TIMEOUT')):
            with self.assertRaises(alert.AlertError):
                alert.deliver(report('PASS'), config, self.state_path, False)
        self.assertEqual(self.state_path.read_bytes(), original)
        with patch.object(alert, 'send_webhook', return_value=200):
            self.assertEqual(alert.deliver(report('PASS'), config, self.state_path, False)['event'], 'RECOVERY')

    def test_explicit_test_delivery_bypasses_pass_and_never_alters_health_state(self):
        config = self.loaded_config()
        with patch.object(alert, 'send_webhook', return_value=200) as send:
            tested = alert.deliver(report('PASS'), config, self.state_path, True)
            self.assertFalse(self.state_path.exists())
            alert.deliver(report(), config, self.state_path, False)
            original = self.state_path.read_bytes()
            alert.deliver(report('PASS'), config, self.state_path, True)
        self.assertEqual(tested['event'], 'TEST')
        self.assertEqual(send.call_args.args[1]['event'], 'TEST')
        self.assertEqual(self.state_path.read_bytes(), original)

    def test_receiver_change_requires_new_state_instead_of_silent_reset(self):
        with patch.object(alert, 'send_webhook', return_value=200):
            alert.deliver(report(), self.loaded_config(), self.state_path, False)
        self.configure('https://other.example.test/alerts')
        with patch.object(alert, 'send_webhook') as send, self.assertRaisesRegex(alert.AlertError, 'STATE_FORMAT_OR_TARGET_MISMATCH'):
            alert.deliver(report(), self.loaded_config(), self.state_path, False)
        send.assert_not_called()

    def test_corrupt_state_never_disappears_and_never_sends(self):
        original = b'{"last_status": "bogus"}'
        self.state_path.write_bytes(original); self.state_path.chmod(0o600)
        with patch.object(alert, 'send_webhook') as send, self.assertRaises(alert.AlertError):
            alert.deliver(report(), self.loaded_config(), self.state_path, False)
        send.assert_not_called()
        self.assertEqual(self.state_path.read_bytes(), original)

    def test_state_commit_failure_reports_delivered_without_persisted_success(self):
        with patch.object(alert, 'send_webhook', return_value=202), \
             patch.object(alert, 'commit_state', side_effect=alert.AlertError('STATE_COMMIT_FAILED')):
            code, receipt, output = self.run_main()
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'STATE_COMMIT_FAILED')
        self.assertEqual(receipt['http_status'], 202)
        self.assertTrue(receipt['delivery_completed'])
        self.assertFalse(self.state_path.exists())
        self.assertNotIn(str(self.root), output)

    def test_parallel_run_cannot_send_during_locked_state(self):
        with alert.state_lock(self.state_path.with_name('state.json.lock')):
            with patch.object(alert, 'send_webhook') as send, self.assertRaisesRegex(alert.AlertError, 'STATE_LOCK_BUSY_OR_UNAVAILABLE'):
                alert.deliver(report(), self.loaded_config(), self.state_path, False)
        send.assert_not_called()
        with patch.object(alert, 'send_webhook', return_value=200):
            self.assertEqual(alert.deliver(report(), self.loaded_config(), self.state_path, False)['status'], 'DELIVERED')

    def test_receipt_reservation_refuses_overwrite_before_any_delivery(self):
        receipt = self.root / 'existing.json'; receipt.write_bytes(b'original')
        with patch.object(alert, 'send_webhook') as send, contextlib.redirect_stdout(io.StringIO()) as output:
            code = alert.main(['--config', str(self.config_path), '--report', str(self.report_path),
                               '--state', str(self.state_path), '--receipt', str(receipt)])
        self.assertEqual(code, 2)
        self.assertEqual(receipt.read_bytes(), b'original')
        send.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['reason'], 'RECEIPT_ALREADY_EXISTS')

    def test_missing_output_directory_fails_before_sending(self):
        with patch.object(alert, 'send_webhook') as send, contextlib.redirect_stdout(io.StringIO()) as output:
            code = alert.main(['--config', str(self.config_path), '--report', str(self.report_path),
                               '--state', str(self.state_path), '--receipt', str(self.root/'missing'/'receipt.json')])
        self.assertEqual(code, 2)
        send.assert_not_called()
        self.assertNotIn(str(self.root), output.getvalue())

    def test_receipt_is_safe_metadata_without_remote_body_config_or_paths(self):
        token = self.root / 'token'; token.write_text('VERY_PRIVATE_BEARER'); token.chmod(0o600)
        self.configure(bearer_token_file='token')
        with patch.object(alert, 'send_webhook', return_value=200):
            code, receipt, output = self.run_main()
        self.assertEqual(code, 0)
        combined = json.dumps(receipt) + output
        for secret in ('VERY_PRIVATE_BEARER', 'receiver.example', 'NEVER_EXPORT', str(self.root), '/private/path'):
            self.assertNotIn(secret, combined)
        self.assertTrue(receipt['not_a_production_signoff'])

    def test_endpoint_rejects_credentials_query_fragments_controls_or_other_protocols(self):
        invalid = ['https://u:p@example.test/a', 'https://u@example.test', 'https://example.test/a?k=v',
                   'https://example.test/a?', 'https://example.test/#fragment', 'https://example.test/#',
                   'ftp://example.test', 'file:///secret', 'https://example.test\n/token',
                   'https://example.test\\@other', 'https://%65xample.test', 'https://example.test:0',
                   'https://example.test:65536', 'https://example.test:bad', 'https://例.test', None, 4]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(alert.AlertError):
                alert.parse_endpoint(value, False)

    def test_http_requires_explicit_flag_and_exact_loopback_host(self):
        for value in ['http://127.0.0.1:8080/a', 'http://localhost/a', 'http://[::1]/a']:
            with self.assertRaisesRegex(alert.AlertError, 'HTTPS_REQUIRED'):
                alert.parse_endpoint(value, False)
            self.assertFalse(alert.parse_endpoint(value, True)['production_transport'])
        for value in ['http://example.test/a', 'http://localhost.example/a', 'http://10.20.20.11/a', 'http://0.0.0.0/a']:
            with self.assertRaisesRegex(alert.AlertError, 'HTTPS_REQUIRED'):
                alert.parse_endpoint(value, True)

    def test_origin_allowlist_is_exact_and_canonical(self):
        self.configure()
        value = json.loads(self.config_path.read_bytes())
        for origin in ['https://other.example.test', 'http://receiver.example.test',
                       'https://receiver.example.test/', 'https://receiver.example.test:443', None]:
            value['allowed_origin'] = origin; private_json(self.config_path, value)
            with self.assertRaisesRegex(alert.AlertError, 'ENDPOINT_ORIGIN_NOT_ALLOWLISTED'):
                self.loaded_config()

    def test_unknown_config_or_unsafe_timeout_rejected(self):
        for extra in ({'verify_tls': False}, {'timeout_seconds': 0}, {'timeout_seconds': 10.1},
                      {'timeout_seconds': True}, {'timeout_seconds': '5'}, {'timeout_seconds': float('nan')},
                      {'format_version': 1.0}):
            self.configure(**extra)
            with self.subTest(extra=extra), self.assertRaises(alert.AlertError):
                self.loaded_config()

    def test_tls_context_requires_certificate_chain_and_hostname(self):
        config = self.loaded_config()
        self.assertEqual(config['ssl_context'].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(config['ssl_context'].check_hostname)
        self.assertGreaterEqual(config['ssl_context'].minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_invalid_ca_cannot_disable_tls_validation(self):
        ca = self.root/'bad-ca.pem'; ca.write_text('not a CA')
        self.configure(ca_file='bad-ca.pem')
        with self.assertRaisesRegex(alert.AlertError, 'TLS_CONFIGURATION_INVALID'):
            self.loaded_config()

    def test_token_file_relative_path_and_final_newline_are_supported_but_header_injection_is_not(self):
        token = self.root/'token'; token.chmod(0o600) if token.exists() else None
        for value in ['secret\r\n', '', 'x\nInjected: bad', 'x y', 'x\t', 'x\x00', '☃']:
            token.write_text(value, encoding='utf-8'); token.chmod(0o600)
            self.configure(bearer_token_file='token')
            if value == 'secret\r\n':
                self.assertEqual(self.loaded_config()['bearer'], 'secret')
            else:
                with self.subTest(value=value), self.assertRaises(alert.AlertError):
                    self.loaded_config()

    @unittest.skipIf(os.name == 'nt', 'Windows deployment requires explicit host ACL review')
    def test_posix_config_and_token_require_private_mode(self):
        self.config_path.chmod(0o644)
        with self.assertRaisesRegex(alert.AlertError, 'PRIVATE_FILE_PERMISSIONS_REQUIRED'):
            self.loaded_config()
        self.config_path.chmod(0o600)
        token = self.root/'token'; token.write_text('secret'); token.chmod(0o640)
        self.configure(bearer_token_file='token')
        with self.assertRaisesRegex(alert.AlertError, 'PRIVATE_FILE_PERMISSIONS_REQUIRED'):
            self.loaded_config()

    def test_duplicate_json_keys_non_finite_and_oversized_input_fail_closed(self):
        for raw in (b'{"a":1,"a":2}', b'{"a": NaN}', b'{"a": Infinity}', b'[]', b'bad',
                    b'[' * 10000, b'x' * (alert.MAX_JSON_BYTES + 1)):
            self.report_path.write_bytes(raw)
            with self.subTest(raw=raw[:32]), self.assertRaises(alert.AlertError):
                alert.read_json(self.report_path)

    def test_malformed_report_status_alerts_codes_and_thresholds_never_send(self):
        rows = [dict(report(), kind='OTHER'), dict(report(), status=[]), dict(report(), status='FAILED'),
                dict(report(), alerts=None), dict(report(), alerts=[]), dict(report(), alerts=[{}]),
                dict(report(), alerts=['code with text']), dict(report(), alerts=['A'*97]),
                dict(report(), alerts=['A']*65), dict(report('PASS'), alerts=['HOST_DISK_HIGH']),
                dict(report(), thresholds_status=[]), dict(report(), thresholds_status='unknown')]
        for value in rows:
            with self.subTest(value=value), self.assertRaises(alert.AlertError):
                alert.redacted_report(value)

    def test_stale_future_or_naive_report_is_not_sent(self):
        times = ['invalid', '2026-10-14T00:00:00', None,
                 (datetime.now(timezone.utc)-timedelta(seconds=601)).isoformat(),
                 (datetime.now(timezone.utc)+timedelta(seconds=61)).isoformat()]
        for stamp in times:
            with self.subTest(stamp=stamp), self.assertRaises(alert.AlertError):
                alert.redacted_report(dict(report(), checked_at=stamp))
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + '0Z'
        self.assertTrue(alert.redacted_report(dict(report(), checked_at=stamp))['checked_at'].endswith('+00:00'))

    def test_malformed_state_shapes_fail_without_reset(self):
        config = self.loaded_config()
        with patch.object(alert, 'send_webhook', return_value=200):
            alert.deliver(report(), config, self.state_path, False)
        valid = json.loads(self.state_path.read_bytes())
        variants = [dict(valid, generation=True), dict(valid, generation=0), dict(valid, generation='1'),
                    dict(valid, last_delivered_status=[]), dict(valid, last_delivered_fingerprint='bad'),
                    dict(valid, unexpected='x'), dict(valid, format_version=1.0)]
        for row in variants:
            private_json(self.state_path, row)
            with self.subTest(row=row), self.assertRaises(alert.AlertError):
                alert.load_state(self.state_path, config['target_hash'], 'PRODUCTION_OPERATIONS_PROBE')

    def test_generation_exhaustion_never_sends(self):
        config = self.loaded_config()
        private_json(self.state_path, {'format_version':1, 'target_hash': config['target_hash'],
                                      'report_kind':'PRODUCTION_OPERATIONS_PROBE',
                                      'generation':2**53-1, 'last_delivered_status':'ALERT',
                                      'last_delivered_fingerprint':'0'*64})
        with patch.object(alert, 'send_webhook') as send, self.assertRaisesRegex(alert.AlertError, 'STATE_GENERATION_EXHAUSTED'):
            alert.deliver(report(), config, self.state_path, False)
        send.assert_not_called()

    def test_controlled_loopback_http_delivers_redacted_alert_auth_and_receipt(self):
        token = self.root/'token'; token.write_text('LOCAL_TEST_ONLY_TOKEN'); token.chmod(0o600)
        with receiver() as (origin, events):
            self.configure(origin+'/hook', bearer_token_file='token')
            code, receipt, output = self.run_main('--allow-loopback-test')
        self.assertEqual(code, 0)
        self.assertEqual(receipt['http_status'], 200)
        self.assertFalse(receipt['production_transport'])
        self.assertEqual(events[0]['headers']['Authorization'], 'Bearer LOCAL_TEST_ONLY_TOKEN')
        self.assertEqual(events[0]['headers']['Idempotency-Key'], events[0]['payload']['event_id'])
        self.assertEqual(events[0]['path'], '/hook')
        self.assertNotIn('LOCAL_TEST_ONLY_TOKEN', output+json.dumps(receipt)+json.dumps(events[0]['payload']))
        self.assertNotIn('NEVER_EXPORT', json.dumps(events[0]['payload']))

    def test_proxy_environment_is_ignored_for_controlled_local_request(self):
        with receiver() as (origin, events), patch.dict(os.environ, {
                'HTTP_PROXY':'http://proxy.example.invalid', 'HTTPS_PROXY':'https://proxy.example.invalid',
                'ALL_PROXY':'http://proxy.example.invalid', 'NO_PROXY':''}):
            self.configure(origin+'/hook')
            code, receipt, _ = self.run_main('--allow-loopback-test')
        self.assertEqual(code, 0)
        self.assertEqual(receipt['status'], 'DELIVERED')
        self.assertEqual(len(events), 1)

    def test_http_redirect_never_follows_location_and_keeps_state_unsuccessful(self):
        with receiver(status=302, response_headers={'Location':'https://unconfigured.example.invalid/private'}) as (origin, events):
            self.configure(origin+'/hook')
            code, receipt, output = self.run_main('--allow-loopback-test')
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'HTTP_REDIRECT_REFUSED')
        self.assertEqual(receipt['http_status'], 302)
        self.assertFalse(self.state_path.exists())
        self.assertEqual(len(events), 1)
        self.assertNotIn('unconfigured', json.dumps(receipt)+output)

    def test_http_error_never_includes_body_and_never_commits_state(self):
        with receiver(status=500, body=b'PRIVATE_REMOTE_BODY') as (origin, events):
            self.configure(origin+'/hook')
            code, receipt, output = self.run_main('--allow-loopback-test')
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'HTTP_STATUS_REJECTED')
        self.assertEqual(receipt['http_status'], 500)
        self.assertNotIn('PRIVATE_REMOTE_BODY', output+json.dumps(receipt))
        self.assertFalse(self.state_path.exists())

    def test_oversized_response_is_a_failure_even_after_2xx(self):
        with receiver(body=b'x'*(alert.MAX_RESPONSE_BYTES+1)) as (origin, events):
            self.configure(origin+'/hook')
            code, receipt, _ = self.run_main('--allow-loopback-test')
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'RESPONSE_SIZE_INVALID_OR_TOO_LARGE')
        self.assertEqual(receipt['http_status'], 200)
        self.assertFalse(self.state_path.exists())

    def test_response_headers_are_bounded_before_any_success_state(self):
        with receiver(response_headers={'X-Fill':'x'*(alert.MAX_RESPONSE_HEADER_BYTES+1)}) as (origin, events):
            self.configure(origin+'/hook')
            code, receipt, _ = self.run_main('--allow-loopback-test')
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'RESPONSE_HEADERS_TOO_LARGE')
        self.assertEqual(receipt['event'], 'ALERT')
        self.assertFalse(self.state_path.exists())

    def test_total_timeout_bounds_trickled_body_not_only_each_socket_read(self):
        with receiver(body=b'0123456789', drip_delay=0.08) as (origin, events):
            self.configure(origin+'/hook', timeout_seconds=0.15)
            started = time.monotonic()
            code, receipt, _ = self.run_main('--allow-loopback-test')
            elapsed = time.monotonic()-started
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'DELIVERY_TIMEOUT')
        self.assertLess(elapsed, 0.5)
        self.assertFalse(self.state_path.exists())

    def test_slow_dns_is_bounded_and_cannot_late_send(self):
        self.configure('http://localhost:12345/hook', timeout_seconds=0.1)
        def slow_dns(*args, **kwargs):
            time.sleep(0.3)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 12345))]
        started = time.monotonic()
        with patch.object(alert.socket, 'getaddrinfo', side_effect=slow_dns), patch.object(alert.socket, 'socket') as stream:
            code, receipt, _ = self.run_main('--allow-loopback-test')
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'DELIVERY_TIMEOUT')
        self.assertLess(time.monotonic()-started, 0.5)
        stream.assert_not_called()

    def test_loopback_dns_cannot_resolve_to_non_loopback(self):
        self.configure('http://localhost:12345/hook')
        rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('203.0.113.10', 12345))]
        with patch.object(alert, '_resolved_addresses', return_value=rows), patch.object(alert.socket, 'socket') as stream:
            code, receipt, _ = self.run_main('--allow-loopback-test')
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'LOOPBACK_RESOLUTION_REQUIRED')
        stream.assert_not_called()

    def test_untrusted_tls_is_a_stable_failure_never_a_verification_bypass(self):
        # No external server: the stdlib client factory is intercepted before
        # connecting. Certificate-chain failures retain their safe category.
        with patch.object(alert.http.client, 'HTTPSConnection') as connection:
            connection.return_value.request.side_effect = ssl.SSLCertVerificationError('PRIVATE CERT DETAIL')
            code, receipt, output = self.run_main()
        self.assertEqual(code, 2)
        self.assertEqual(receipt['reason'], 'TLS_VERIFICATION_FAILED')
        self.assertNotIn('PRIVATE CERT DETAIL', output+json.dumps(receipt))
        context = connection.call_args.kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)


if __name__ == '__main__':
    unittest.main()
