"""Failure diagnostics retain causes without copying request or worker secrets."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from integration_diagnostics import CheckFailure, IntegrationDiagnostics, safe_exception, write_source_snapshots


SECRET = 'diagnostic-test-password'
PRIVATE_URL = 'postgresql://operator:' + SECRET + '@private.example/production'
SQL = 'SELECT secret_password FROM private_credentials'


class FakeResponse:
    def __init__(self, status_code, body=None, *, json_exception=None, content=None):
        self.status_code = status_code
        self.body = body
        self.json_exception = json_exception
        self.content = content if content is not None else json.dumps(body).encode()

    def json(self):
        if self.json_exception is not None:
            raise self.json_exception
        return self.body


class FakeClient:
    def __init__(self, response=None, exception=None):
        self.response = response
        self.exception = exception
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if self.exception is not None:
            raise self.exception
        return self.response


class FakePreviewError(ValueError):
    def __init__(self, code, status=503):
        super().__init__(PRIVATE_URL + ' ' + SQL)
        self.code = code
        self.status = status


def service_type(output, *, decode_error=None, validation_error=None, calls=None, saved=None):
    """A minimal synchronous service with the production hook signatures."""
    class Service:
        def capabilities(self):
            return {'available': True, 'code': None}

        @staticmethod
        def _worker_result(envelope):
            if decode_error is not None:
                raise decode_error
            return envelope['result']

        @staticmethod
        def _validate_result_identity(result, capabilities, pool_id):
            if validation_error is not None:
                raise validation_error

        def create(self, changes, pool_id=None, actor='operator'):
            capability = self.capabilities()
            if calls is not None:
                calls.append('ceph.osd_map_export')
            result = self._worker_result(output)
            self._validate_result_identity(result, capability, pool_id)
            if saved is not None:
                saved.append('saved-artifact')
            return result

    return Service


class IntegrationDiagnosticsTests(unittest.TestCase):
    def test_source_snapshots_are_hash_addressed_and_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = b'print("synthetic source")\n'
            saved = write_source_snapshots(root, {'test_script': content})
            self.assertEqual(saved, write_source_snapshots(root, {'test_script': content}))
            self.assertEqual(saved['test_script']['sha256'], hashlib.sha256(content).hexdigest())
            self.assertEqual((root / saved['test_script']['path']).read_bytes(), content)

    def test_source_snapshot_conflict_cannot_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = b'expected source'
            target = root / 'sources' / (hashlib.sha256(content).hexdigest() + '.py')
            target.parent.mkdir()
            target.write_bytes(b'existing contents')
            with self.assertRaisesRegex(CheckFailure, 'SOURCE_SNAPSHOT_CONFLICT'):
                write_source_snapshots(root, {'test_script': content})
            self.assertEqual(target.read_bytes(), b'existing contents')

    def setUp(self):
        self.report = {'checks': {}}
        self.diagnostics = IntegrationDiagnostics(self.report)

    def assert_private_values_absent(self, value):
        encoded = json.dumps(value)
        for private in (SECRET, PRIVATE_URL, SQL):
            self.assertNotIn(private, encoded)

    def test_http_error_before_tamper_is_in_final_failure(self):
        response = FakeResponse(503, {'detail': {
            'code': 'OSDMAP_CAPABILITIES_STALE', 'message': PRIVATE_URL + ' ' + SQL}})
        client = FakeClient(response)
        returned = self.diagnostics.request(
            client, 'tamper_post', 'POST', '/api/v1/osdmap-previews',
            json={'password': SECRET}, headers={'Authorization': 'Bearer ' + SECRET})
        self.assertIs(returned, response)
        self.assertEqual(client.calls[0][2]['json'], {'password': SECRET})
        with self.assertRaises(CheckFailure) as raised:
            self.diagnostics.check('tampered_real_worker_result_identity_rejected', False)
        self.diagnostics.record_failure(raised.exception)
        context = self.report['failure_context']
        self.assertEqual(context['stage'], 'tamper_post')
        self.assertEqual(context['failed_check'], 'tampered_real_worker_result_identity_rejected')
        self.assertEqual(context['http']['status_code'], 503)
        self.assertEqual(context['http']['code'], 'OSDMAP_CAPABILITIES_STALE')
        self.assertEqual(self.report['http_requests'], [self.report['last_http']])
        self.assert_private_values_absent(self.report)

    def test_invalid_json_keeps_http_status_and_safe_decode_error(self):
        failure = ValueError(PRIVATE_URL + ' ' + SQL)
        response = FakeResponse(502, json_exception=failure, content=(SECRET + SQL).encode())
        self.assertIs(self.diagnostics.request(FakeClient(response), 'invalid_json', 'POST',
                                              '/api/v1/osdmap-previews'), response)
        trace = self.report['last_http']
        self.assertEqual(trace['status_code'], 502)
        self.assertIsNone(trace['code'])
        self.assertEqual(trace['json_decode_exception'], {'type': 'ValueError'})
        self.assert_private_values_absent(self.report)

    def test_transport_exception_keeps_stage_and_original_exception(self):
        failure = ConnectionError(PRIVATE_URL + ' ' + SQL)
        with self.assertRaises(ConnectionError) as raised:
            self.diagnostics.request(FakeClient(exception=failure), 'transport_failed', 'GET',
                                     '/api/v1/osdmap-previews/capabilities')
        self.assertIs(raised.exception, failure)
        self.diagnostics.record_failure(failure)
        context = self.report['failure_context']
        self.assertEqual(context['stage'], 'transport_failed')
        self.assertIsNone(context['http']['status_code'])
        self.assertEqual(context['http']['exception'], {'type': 'ConnectionError'})
        self.assertGreaterEqual(context['http']['duration_seconds'], 0)
        self.assert_private_values_absent(self.report)

    def test_error_code_and_endpoint_are_redacted_without_raw_body(self):
        response = FakeResponse(400, {'detail': {'code': PRIVATE_URL, 'message': SQL}})
        self.diagnostics.request(FakeClient(response), 'error_response', 'GET',
                                 'https://operator:' + SECRET + '@host/api/private/' + SECRET)
        trace = self.report['last_http']
        self.assertEqual(trace['status_code'], 400)
        self.assertEqual(trace['endpoint'], 'REDACTED_ENDPOINT')
        self.assertIsNone(trace['code'])
        self.assertTrue(trace['code_rejected'])
        self.assert_private_values_absent(self.report)

    def test_oversized_error_body_is_not_decoded(self):
        response = FakeResponse(500, json_exception=AssertionError('json must not be read'),
                                content=b'x' * 65537)
        self.diagnostics.request(FakeClient(response), 'large_error', 'POST',
                                 '/api/v1/osdmap-previews')
        self.assertEqual(self.report['last_http']['error_body_inspection'], 'SIZE_LIMIT')
        self.assertNotIn('json_decode_exception', self.report['last_http'])

    def test_unavailable_capability_in_http_200_keeps_reason_code(self):
        response = FakeResponse(200, {'available': False, 'code': 'OSDMAP_CAPABILITIES_STALE',
                                      'reason': PRIVATE_URL + ' ' + SQL})
        self.diagnostics.request(FakeClient(response), 'capability_read', 'GET',
                                 '/api/v1/osdmap-previews/capabilities')
        trace = self.report['last_http']
        self.assertEqual(trace['status_code'], 200)
        self.assertEqual(trace['code'], 'OSDMAP_CAPABILITIES_STALE')
        self.assertIs(trace['available'], False)
        self.assert_private_values_absent(self.report)

    def test_rejected_request_does_not_inherit_previous_service_trace(self):
        service = service_type({'ok': True, 'result': {}})

        class CreateClient:
            def request(self, method, path, **kwargs):
                service().create([], pool_id=13)
                return FakeResponse(201, {'id': 'previous-created-preview'})

        with self.diagnostics.trace_service(service, source_calls=lambda: [], snapshot=lambda: (0, ())):
            self.diagnostics.request(CreateClient(), 'previous_create', 'POST',
                                     '/api/v1/osdmap-previews')
            self.diagnostics.request(
                FakeClient(FakeResponse(503, {'detail': {'code': 'OSDMAP_CAPABILITIES_STALE'}})),
                'next_request_rejected', 'POST', '/api/v1/osdmap-previews')
        self.assertEqual(self.report['last_service']['http_sequence'], 1)
        self.assertEqual(self.report['last_http']['sequence'], 2)
        self.diagnostics.record_failure(CheckFailure('unexpected_tamper_response'))
        context = self.report['failure_context']
        self.assertEqual(context['http']['code'], 'OSDMAP_CAPABILITIES_STALE')
        self.assertIsNone(context['service'])
        self.assertEqual(len(self.report['service_requests']), 1)
        self.assertTrue(self.report['service_requests'][0]['returned_successfully'])

    def test_http_trace_limit_preserves_latest_failure(self):
        response = FakeResponse(200, {'available': True})
        for index in range(513):
            self.diagnostics.request(FakeClient(response), 'capability_read', 'GET',
                                     '/api/v1/osdmap-previews/capabilities')
        self.diagnostics.request(
            FakeClient(FakeResponse(503, {'detail': {'code': 'OSDMAP_WORKER_UNAVAILABLE'}})),
            'last_failed_request', 'POST', '/api/v1/osdmap-previews')
        traces = self.report['http_requests']
        self.assertEqual(len(traces), 512)
        self.assertTrue(self.report['diagnostics_truncated'])
        self.assertEqual(traces[0]['sequence'], 3)
        self.assertIs(traces[-1], self.report['last_http'])
        self.assertEqual(traces[-1]['sequence'], 514)
        self.diagnostics.record_failure(CheckFailure('worker_unavailable'))
        context = self.report['failure_context']
        self.assertEqual(context['stage'], 'last_failed_request')
        self.assertEqual(context['http']['status_code'], 503)
        self.assertEqual(context['http']['code'], 'OSDMAP_WORKER_UNAVAILABLE')

    def test_worker_failure_retains_code_and_unchanged_storage(self):
        failure = FakePreviewError('OSDMAP_TOOL_FAILED', 409)
        calls = ['earlier.call']
        service = service_type({'ok': False, 'code': failure.code, 'message': PRIVATE_URL},
                               decode_error=failure, calls=calls)
        self.diagnostics.stage('worker_failed')
        with self.diagnostics.trace_service(service, source_calls=lambda: calls,
                                            snapshot=lambda: (2, frozenset({'private-artifact'}))):
            with self.assertRaises(FakePreviewError) as raised:
                service().create([{'osd_id': 2, 'weight': 0.9}], pool_id=13)
        self.assertIs(raised.exception, failure)
        self.diagnostics.record_failure(failure)
        trace = self.report['failure_context']['service']
        self.assertTrue(trace['worker_envelope_received'])
        self.assertFalse(trace['worker_success_decoded'])
        self.assertFalse(trace['identity_validation_entered'])
        self.assertEqual(trace['worker_envelope']['ok'], False)
        self.assertEqual(trace['worker_envelope']['code'], 'OSDMAP_TOOL_FAILED')
        self.assertEqual(trace['exception'], {'type': 'FakePreviewError', 'code': 'OSDMAP_TOOL_FAILED',
                                             'status': 409})
        self.assertEqual(trace['source_calls'], ['ceph.osd_map_export'])
        self.assertEqual(trace['storage_before'], {'row_count': 2, 'file_count': 1})
        self.assertFalse(trace['storage_changed'])
        self.assertNotIn('private-artifact', json.dumps(self.report))
        self.assert_private_values_absent(self.report)

    def test_identity_failure_is_distinct_from_worker_failure(self):
        failure = FakePreviewError('OSDMAP_RESULT_IDENTITY_MISMATCH')
        service = service_type({'ok': True, 'result': {'secret': PRIVATE_URL}}, validation_error=failure)
        with self.diagnostics.trace_service(service, source_calls=lambda: [], snapshot=lambda: (2, ())):
            with self.assertRaises(FakePreviewError):
                service().create([], pool_id=13)
        trace = self.report['last_service']
        self.assertTrue(trace['worker_success_decoded'])
        self.assertTrue(trace['identity_validation_entered'])
        self.assertEqual(trace['last_worker_stage'], 'WORKER_IDENTITY_VALIDATION')
        self.assertEqual(trace['exception']['code'], 'OSDMAP_RESULT_IDENTITY_MISMATCH')
        self.assertFalse(trace['storage_changed'])
        self.assert_private_values_absent(self.report)

    def test_malformed_envelopes_do_not_mask_decoder_exception(self):
        for output in (PRIVATE_URL, [PRIVATE_URL], {'ok': SECRET, 'code': PRIVATE_URL},
                       {'ok': False, 'code': 'X' * 129}):
            with self.subTest(output_type=type(output).__name__):
                failure = FakePreviewError('OSDMAP_WORKER_RESULT_INVALID')
                service = service_type(output, decode_error=failure)
                with self.diagnostics.trace_service(service, source_calls=lambda: [], snapshot=lambda: (0, ())):
                    with self.assertRaises(FakePreviewError) as raised:
                        service().create([])
                self.assertIs(raised.exception, failure)
                trace = self.report['last_service']
                self.assertTrue(trace['worker_envelope_received'])
                self.assertFalse(trace['worker_success_decoded'])
                self.assertEqual(trace['exception']['code'], 'OSDMAP_WORKER_RESULT_INVALID')
                if isinstance(output, dict):
                    self.assertIsNone(trace['worker_envelope']['code'])
                    self.assertTrue(trace['worker_envelope']['code_rejected'])
                self.assert_private_values_absent(self.report)

    def test_snapshot_failure_cannot_mask_original_service_exception(self):
        failure = FakePreviewError('OSDMAP_TIMEOUT')
        service = service_type({'ok': False}, decode_error=failure)

        def unavailable_snapshot():
            raise OSError(5, PRIVATE_URL + ' ' + SQL)

        with self.diagnostics.trace_service(service, source_calls=lambda: [], snapshot=unavailable_snapshot):
            with self.assertRaises(FakePreviewError) as raised:
                service().create([])
        self.assertIs(raised.exception, failure)
        trace = self.report['last_service']
        self.assertIsNone(trace['storage_changed'])
        self.assertIsNone(trace['storage_before'])
        self.assertIsNone(trace['storage_after'])
        self.assertEqual(trace['exception']['code'], 'OSDMAP_TIMEOUT')
        self.assertEqual([entry['stage'] for entry in self.report['diagnostic_errors']],
                         ['storage-before', 'storage-after'])
        self.assert_private_values_absent(self.report)

    def test_all_creates_are_recorded_and_hooks_restored(self):
        saved = []
        service = service_type({'ok': True, 'result': {'ok': 'result'}}, saved=saved)
        originals = (service.create, service.capabilities, service._worker_result,
                     service._validate_result_identity)
        with self.diagnostics.trace_service(service, source_calls=lambda: [],
                                            snapshot=lambda: (len(saved), tuple(saved))):
            service().create([], pool_id=13)
            service().create([], pool_id=13)
        traces = self.report['service_requests']
        self.assertEqual(len(traces), 2)
        self.assertEqual([trace['sequence'] for trace in traces], [1, 2])
        self.assertTrue(all(trace['returned_successfully'] and trace['storage_changed'] for trace in traces))
        self.assertEqual((service.create, service.capabilities, service._worker_result,
                          service._validate_result_identity), originals)

    def test_safe_exception_keeps_only_bounded_metadata(self):
        failure = FakePreviewError('OSDMAP_TOOL_FAILED', 503)
        failure.errno = 13
        self.assertEqual(safe_exception(failure), {'type': 'FakePreviewError',
                                                'code': 'OSDMAP_TOOL_FAILED', 'status': 503, 'errno': 13})
        for code, status, errno in ((PRIVATE_URL, True, -1), ('X' * 129, 999, 4097),
                                    (SQL, '503', '13')):
            with self.subTest(code_type=type(code).__name__):
                failure.code, failure.status, failure.errno = code, status, errno
                value = safe_exception(failure)
                self.assertEqual(value, {'type': 'FakePreviewError'})
                self.assert_private_values_absent(value)

    def test_unreadable_exception_properties_are_nonfatal(self):
        class OpaqueError(Exception):
            @property
            def code(self):
                raise RuntimeError(PRIVATE_URL)

            @property
            def status(self):
                raise RuntimeError(SQL)

        self.assertEqual(safe_exception(OpaqueError(SECRET)), {'type': 'OpaqueError'})


if __name__ == '__main__':
    unittest.main()
