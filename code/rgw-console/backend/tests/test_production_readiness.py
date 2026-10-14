"""Production readiness CLI contracts using synthetic copies and mocked I/O."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('console_production_readiness_contract', ROOT / 'deploy/check-production-ready.py')
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)
PROJECT = 'storage-lab-console-production-synthetic'
BASE = 'https://console.example'
SENTINEL = 'SYNTHETIC_PASSWORD_NOT_FOR_REPORT_0123456789'


class ProductionReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'compose.production.yml').write_text('services: {}')
        (self.root / '.env').write_text(
            'COMPOSE_PROJECT_NAME=' + PROJECT + '\nAPP_INSTANCE_ID=' + PROJECT
            + '\nAPP_DEPLOYMENT_SCOPE=production\nCORS_ORIGINS=' + BASE + '\n')
        (self.root / 'viewer.password').write_text(SENTINEL + '\n')
        (self.root / 'accounts.json').write_text(json.dumps({'accounts': [{
            'role': 'viewer', 'username': 'synthetic-viewer',
            'password_file': str(self.root / 'viewer.password')}]}))

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def runtime():
        return {'environment': 'production', 'deployment_scope': 'production',
                'deployment_id': PROJECT, 'console_role': 'viewer',
                'application_version': '5.2.0-rc.1', 'console_read_only': True,
                'ceph_mutations_enabled': False,
                'features': {'upgrade': True, 'lab': False, 'legacy_rgw': False, 'legacy_rbd': False},
                'untrusted_debug_field': SENTINEL}

    @staticmethod
    def ready():
        return {'ready': True, 'status': 'ready', 'blocking_dependencies': [], 'dependencies': {
            'database': {'status': 'ready', 'required': True, 'schema_version': 21},
            **{key: {'status': 'ready', 'required': True} for key in ('config', 'frontend', 'ceph_executor')}}}

    def args(self, report=None, base=BASE, extra=()):
        arguments = ['--deployment-directory', str(self.root), '--base-url', base,
                     '--ca-file', str(self.root / 'synthetic-ca.crt'),
                     '--auth-user-file', str(self.root / 'accounts.json')]
        if report:
            arguments += ['--report', str(report)]
        return arguments + list(extra)

    def run_fake(self, runtime=None, ready=None, report=None, extra=()):
        stdout = io.StringIO()
        context = ssl.create_default_context()
        with patch.object(check.ssl, 'create_default_context', return_value=context) as tls, \
             patch.object(check.client.request, 'build_opener') as opener, \
             patch.object(check.client, 'get_json', side_effect=[runtime or self.runtime(), ready or self.ready()]) as http, \
             redirect_stdout(stdout):
            code = check.main(self.args(report, extra=extra))
        return code, json.loads(stdout.getvalue()), tls, opener, http

    def test_cli_pass_creates_new_receipt_with_strict_ca_and_bound_origin(self):
        report = self.root / 'receipts/readiness.json'
        env_before = (self.root / '.env').read_bytes()
        code, result, tls, opener, calls = self.run_fake(report=report)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['tls_ca_and_hostname_verified'])
        self.assertTrue(result['origin_bound_to_deployment'])
        self.assertTrue(result['viewer_authenticated'])
        self.assertTrue(result['not_a_production_signoff'])
        self.assertTrue(result['dedicated_ssh_authority_and_image_signature_not_checked'])
        tls.assert_called_once_with(cafile=str(self.root / 'synthetic-ca.crt'))
        handlers = opener.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertTrue(handlers[1]._context.check_hostname)
        self.assertEqual(handlers[1]._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertIsInstance(handlers[2], check.client.NoRedirect)
        self.assertEqual([call.args[1] for call in calls.call_args_list],
                         [BASE + '/api/runtime-config', BASE + '/api/ready'])
        self.assertTrue(all(call.args[2].startswith('Basic ') for call in calls.call_args_list))
        self.assertEqual(json.loads(report.read_text()), result)
        self.assertEqual((self.root / '.env').read_bytes(), env_before)
        for sensitive in (SENTINEL, 'Basic ', str(self.root), 'synthetic-viewer', BASE):
            self.assertNotIn(sensitive, json.dumps(result) + report.read_text())

    def test_runtime_missing_identity_flags_and_wrong_role_are_rejected(self):
        keys = ('environment', 'deployment_scope', 'deployment_id', 'console_role',
                'application_version', 'console_read_only', 'ceph_mutations_enabled')
        for key in keys:
            row = self.runtime(); del row[key]
            with self.subTest(key=key), self.assertRaises(check.client.ReadyCheckError):
                check.validate_production_runtime(row, PROJECT, '5.2.0-rc.1')
        for field, value in (('console_role', 'admin'), ('console_read_only', 1),
                             ('ceph_mutations_enabled', 0), ('deployment_scope', 'staging')):
            row = self.runtime(); row[field] = value
            with self.subTest(field=field), self.assertRaises(check.client.ReadyCheckError):
                check.validate_production_runtime(row, PROJECT, '5.2.0-rc.1')

    def test_production_features_must_be_explicit_literal_booleans(self):
        for field in ('upgrade', 'lab', 'legacy_rgw', 'legacy_rbd'):
            row = self.runtime(); del row['features'][field]
            with self.subTest(field=field), self.assertRaises(check.client.ReadyCheckError):
                check.validate_production_runtime(row, PROJECT, '5.2.0-rc.1')
        for features in (None, [], {}, 'read-only'):
            row = self.runtime(); row['features'] = features
            with self.assertRaises(check.client.ReadyCheckError):
                check.validate_production_runtime(row, PROJECT, '5.2.0-rc.1')

    def test_bad_runtime_stops_before_second_request_and_writes_fail_receipt(self):
        runtime = self.runtime(); runtime['ceph_mutations_enabled'] = True
        report = self.root / 'failed-runtime.json'
        code, result, _, _, calls = self.run_fake(runtime=runtime, report=report)
        self.assertEqual(code, 2)
        self.assertEqual(result['error_code'], 'PRODUCTION_IDENTITY_OR_READONLY_MISMATCH')
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(json.loads(report.read_text()), result)
        self.assertNotIn(SENTINEL, report.read_text())

    def test_ready_false_schema_or_required_dependency_is_not_http_200_pass(self):
        bad_rows = []
        row = self.ready(); row['ready'] = False; bad_rows.append(row)
        for schema in (20, 21.0, '21', True):
            row = self.ready(); row['dependencies']['database']['schema_version'] = schema; bad_rows.append(row)
        for key in ('database', 'config', 'frontend', 'ceph_executor'):
            row = self.ready(); row['dependencies'][key]['required'] = False; bad_rows.append(row)
            row = self.ready(); del row['dependencies'][key]['required']; bad_rows.append(row)
        for row in bad_rows:
            with self.subTest(row=row):
                code, result, _, _, calls = self.run_fake(ready=row)
                self.assertEqual(code, 2)
                self.assertEqual(result['error_code'], 'DEPENDENCY_OR_SCHEMA_NOT_READY')
                self.assertEqual(calls.call_count, 2)

    def test_unapproved_origin_is_rejected_before_credentials_or_tls(self):
        stdout = io.StringIO()
        with patch.object(check.client, 'viewer_authorization') as auth, \
             patch.object(check.ssl, 'create_default_context') as tls, \
             patch.object(check.client, 'get_json') as http, redirect_stdout(stdout):
            code = check.main(self.args(base='https://other.example'))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())['error_code'], 'API_ORIGIN_NOT_IN_DEPLOYMENT_ALLOWLIST')
        auth.assert_not_called(); tls.assert_not_called(); http.assert_not_called()

    def test_invalid_release_and_deployment_markers_do_not_read_credentials(self):
        for extra in (['--expected-schema', '0'], ['--expected-schema', '10000'],
                      ['--expected-version', 'release/unsafe']):
            with patch.object(check.client, 'viewer_authorization') as auth, redirect_stdout(io.StringIO()):
                code = check.main(self.args(extra=extra))
            self.assertEqual(code, 2); auth.assert_not_called()
        env = self.root / '.env'
        env.write_text(env.read_text().replace('APP_DEPLOYMENT_SCOPE=production', 'APP_DEPLOYMENT_SCOPE=staging'))
        with patch.object(check.client, 'viewer_authorization') as auth, redirect_stdout(io.StringIO()):
            code = check.main(self.args())
        self.assertEqual(code, 2); auth.assert_not_called()

    def test_http_error_preserves_status_but_not_body_or_auth(self):
        stdout = io.StringIO()
        with patch.object(check.ssl, 'create_default_context'), \
             patch.object(check.client.request, 'build_opener'), \
             patch.object(check.client, 'get_json', side_effect=check.client.ReadyCheckError('HTTP_NOT_OK', 503)), \
             redirect_stdout(stdout):
            code = check.main(self.args())
        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result['http_status'], 503)
        self.assertEqual(result['error_code'], 'HTTP_NOT_OK')
        self.assertNotIn(SENTINEL, stdout.getvalue())
        self.assertNotIn('Basic ', stdout.getvalue())

    def test_configuration_error_does_not_echo_private_path(self):
        stdout = io.StringIO()
        with patch.object(check.client, 'viewer_authorization', side_effect=OSError(SENTINEL + str(self.root))), \
             patch.object(check.client, 'get_json') as http, redirect_stdout(stdout):
            code = check.main(self.args())
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())['error_code'], 'PRODUCTION_CHECK_CONFIGURATION_INVALID')
        self.assertNotIn(SENTINEL, stdout.getvalue()); self.assertNotIn(str(self.root), stdout.getvalue())
        http.assert_not_called()

    def test_existing_report_is_not_overwritten_and_prevents_auth_or_requests(self):
        report = self.root / 'existing.json'; report.write_text('preserve-original')
        stdout = io.StringIO()
        with patch.object(check.client, 'viewer_authorization') as auth, \
             patch.object(check.client, 'get_json') as http, redirect_stdout(stdout):
            code = check.main(self.args(report=report))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())['error_code'], 'REPORT_ALREADY_EXISTS')
        self.assertEqual(report.read_text(), 'preserve-original')
        auth.assert_not_called(); http.assert_not_called()

    def test_report_creation_error_is_redacted_and_prevents_auth(self):
        stdout = io.StringIO()
        with patch.object(Path, 'open', side_effect=OSError(SENTINEL + str(self.root))), \
             patch.object(check.client, 'viewer_authorization') as auth, \
             patch.object(check.client, 'get_json') as http, redirect_stdout(stdout):
            code = check.main(self.args(report=self.root / 'new.json'))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())['error_code'], 'REPORT_WRITE_FAILED')
        self.assertNotIn(SENTINEL, stdout.getvalue()); self.assertNotIn(str(self.root), stdout.getvalue())
        auth.assert_not_called(); http.assert_not_called()

    def test_failed_report_write_or_close_converts_pass_to_fail_without_traceback(self):
        for operation in ('write', 'close'):
            class FailedOutput:
                closed = False
                def write(self, content):
                    if operation == 'write': raise OSError(SENTINEL)
                def flush(self): pass
                def close(self):
                    self.closed = True
                    if operation == 'close': raise ValueError(SENTINEL)
            output = FailedOutput()
            with patch.object(check.client, 'reserve_report', return_value=output):
                code, result, _, _, _ = self.run_fake(report=self.root / 'failed-write.json')
            self.assertEqual(code, 2)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(result['error_code'], 'REPORT_WRITE_FAILED')
            self.assertTrue(output.closed)
            self.assertNotIn(SENTINEL, json.dumps(result))


if __name__ == '__main__':
    unittest.main()
