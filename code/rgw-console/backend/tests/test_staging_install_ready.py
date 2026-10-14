import base64
from contextlib import redirect_stdout
from email.message import Message
from http.client import BadStatusLine, IncompleteRead, LineTooLong
import importlib.util
import io
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError


SCRIPT = Path(__file__).resolve().parents[2] / 'deploy' / 'check-staging-ready.py'
SPEC = importlib.util.spec_from_file_location('console_staging_install_ready', SCRIPT)
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class Response:
    def __init__(self, body=b'{}', status=200, content_type='application/json'):
        self.body = body; self.status = status; self.headers = Message()
        self.headers['Content-Type'] = content_type
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, maximum): return self.body[:maximum]


class StagingInstallReadinessTests(unittest.TestCase):
    project = 'storage-lab-console-staging-test'

    def runtime(self):
        return {'environment':'production', 'deployment_scope':'staging', 'deployment_id':self.project,
                'console_role':'viewer', 'application_version':'5.2.0-rc.1', 'console_read_only':True,
                'ceph_mutations_enabled':False}

    def ready(self):
        return {'ready':True, 'status':'ready', 'blocking_dependencies':[], 'dependencies':{
            'database':{'status':'ready','schema_version':21},
            **{key:{'status':'ready','required':True} for key in ('config','frontend','ceph_executor')}}}

    def prepare(self, root):
        (root/'compose.production.yml').write_text('services: {}')
        (root/'.env').write_text(f'COMPOSE_PROJECT_NAME={self.project}\nAPP_INSTANCE_ID={self.project}\nAPP_DEPLOYMENT_SCOPE=staging\nCONSOLE_HTTPS_PORT=8446\n')
        (root/'viewer.password').write_text('a'*64+'\n')
        (root/'accounts.json').write_text(json.dumps({'accounts':[{'role':'viewer','username':'staging-viewer',
                                                                   'password_file':str(root/'viewer.password')}] }))

    def test_only_explicit_staging_identity_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.prepare(root)
            self.assertEqual(check.staging_identity(root),(self.project,8446))
            (root/'.env').write_text('COMPOSE_PROJECT_NAME=other\n')
            with self.assertRaises(check.ReadyCheckError): check.staging_identity(root)

    def test_duplicate_runtime_key_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.prepare(root)
            with (root/'.env').open('a') as output: output.write('CONSOLE_HTTPS_PORT=8447\n')
            with self.assertRaisesRegex(check.ReadyCheckError,'DUPLICATE_RUNTIME_KEY'): check.staging_identity(root)

    def test_viewer_password_file_not_inline_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.prepare(root)
            header = check.viewer_authorization(root/'accounts.json')
            self.assertEqual(base64.b64decode(header.split()[1]).decode(), 'staging-viewer:'+('a'*64))
            (root/'accounts.json').write_text(json.dumps({'accounts':[{'role':'viewer','username':'x','password':'secret'}]}))
            with self.assertRaisesRegex(check.ReadyCheckError,'REFERENCE_INVALID'): check.viewer_authorization(root/'accounts.json')

    def test_duplicate_or_missing_viewer_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.prepare(root)
            row = json.loads((root/'accounts.json').read_text())['accounts'][0]
            for accounts in ([],[row,row],[None]):
                (root/'accounts.json').write_text(json.dumps({'accounts':accounts}))
                with self.assertRaises(check.ReadyCheckError): check.viewer_authorization(root/'accounts.json')

    def test_password_multiline_and_short_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.prepare(root)
            for password in ('short', 'a'*32+'\n'+'b'*32):
                (root/'viewer.password').write_text(password)
                with self.assertRaisesRegex(check.ReadyCheckError,'PASSWORD_FILE_INVALID'): check.viewer_authorization(root/'accounts.json')

    def test_redirect_is_not_followed_with_credentials(self):
        self.assertIsNone(check.NoRedirect().redirect_request(None,None,302,'Moved',{},'https://other/'))

    def test_http_failure_retains_status_without_body_or_credentials(self):
        with patch.object(check.request.OpenerDirector,'open',side_effect=HTTPError('https://localhost',401,'sensitive',{},None)):
            with self.assertRaises(check.ReadyCheckError) as failure:
                check.get_json(check.request.build_opener(),'https://localhost','Basic sensitive')
        self.assertEqual(str(failure.exception),'HTTP_NOT_OK')
        self.assertEqual(failure.exception.http_status,401)

    def test_connection_error_diagnostics_do_not_echo_exception(self):
        with patch.object(check.request.OpenerDirector,'open',side_effect=URLError('password=secret')):
            with self.assertRaisesRegex(check.ReadyCheckError,'^TLS_OR_CONNECTION_FAILED$'):
                check.get_json(check.request.build_opener(),'https://localhost','Basic sensitive')

    def test_protocol_error_diagnostics_do_not_leak_response_fragments(self):
        for problem in (BadStatusLine('password=fake-secret'),IncompleteRead(b'fake-secret'),LineTooLong('fake-secret')):
            with patch.object(check.request.OpenerDirector,'open',side_effect=problem):
                with self.assertRaisesRegex(check.ReadyCheckError,'^HTTP_PROTOCOL_INVALID$') as failure:
                    check.get_json(check.request.build_opener(),'https://localhost','Basic sensitive')
            self.assertNotIn('fake-secret',str(failure.exception))

    def test_body_type_size_and_json_shape_are_checked(self):
        for response in (Response(b'{}',content_type='text/html'),Response(b'a'*65537),
                         Response(b'[]'),Response(b'bad json'),Response(status=503)):
            with patch.object(check.request.OpenerDirector,'open',return_value=response):
                with self.assertRaises(check.ReadyCheckError):
                    check.get_json(check.request.build_opener(),'https://localhost','Basic sensitive')

    def test_runtime_role_scope_version_and_readonly_must_match(self):
        check.validate_runtime(self.runtime(),self.project,'5.2.0-rc.1')
        for key, value in (('environment','lab'),('deployment_scope','production'),('deployment_id','other'),
                           ('console_role','admin'),('application_version','old'),('console_read_only',False),
                           ('ceph_mutations_enabled',True)):
            row = self.runtime(); row[key] = value
            with self.assertRaises(check.ReadyCheckError): check.validate_runtime(row,self.project,'5.2.0-rc.1')

    def test_ready_false_and_schema_mismatch_are_fail_not_http_200_pass(self):
        check.validate_ready(self.ready(),21)
        for key, value in (('ready',False),('status','not_ready'),('blocking_dependencies',['database']),('dependencies',{})):
            row = self.ready(); row[key] = value
            with self.assertRaises(check.ReadyCheckError): check.validate_ready(row,21)
        with self.assertRaises(check.ReadyCheckError): check.validate_ready(self.ready(),22)

    def test_required_executor_and_frontend_not_silently_optional(self):
        for key in ('config','frontend','ceph_executor'):
            row = self.ready(); row['dependencies'][key]['required'] = False
            with self.assertRaises(check.ReadyCheckError): check.validate_ready(row,21)

    def test_main_uses_verified_context_no_proxy_and_does_not_log_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.prepare(root); captured = io.StringIO()
            context = ssl.create_default_context()
            with patch.object(check.ssl,'create_default_context',return_value=context) as tls, \
                 patch.object(check.request,'build_opener') as opener, \
                 patch.object(check,'get_json',side_effect=[self.runtime(),self.ready()]) as calls, redirect_stdout(captured):
                code = check.main(['--deployment-directory',directory,'--ca-file',str(root/'ca.crt'),
                                   '--auth-user-file',str(root/'accounts.json'),'--report',str(root/'report.json')])
            self.assertEqual(code,0)
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
            tls.assert_called_once_with(cafile=str(root/'ca.crt'))
            handlers = opener.call_args.args
            self.assertEqual(handlers[0].proxies,{})
            self.assertIsInstance(handlers[-1],check.NoRedirect)
            self.assertEqual([item.args[1] for item in calls.call_args_list],
                             ['https://localhost:8446/api/runtime-config','https://localhost:8446/api/ready'])
            self.assertNotIn('Basic',captured.getvalue())
            self.assertNotIn('a'*64,captured.getvalue())
            report = json.loads((root/'report.json').read_text())
            self.assertTrue(report['certificate_revocation_policy_not_validated'])

    def test_report_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'report.json').write_text('preserve')
            with self.assertRaises(FileExistsError):
                check.main(['--deployment-directory',directory,'--ca-file',str(root/'ca'),
                            '--auth-user-file',str(root/'users'),'--report',str(root/'report.json')])
            self.assertEqual((root/'report.json').read_text(),'preserve')


if __name__ == '__main__': unittest.main()
