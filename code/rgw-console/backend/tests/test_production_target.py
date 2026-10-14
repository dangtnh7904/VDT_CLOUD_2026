import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from production_target import approved_api_base, https_origin
from production_acceptance import AcceptanceError
SPEC = importlib.util.spec_from_file_location('console_production_ready_test', ROOT/'deploy/check-production-ready.py')
checker = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(checker)


class ProductionTargetTests(unittest.TestCase):
    def test_canonical_origin(self):
        self.assertEqual(https_origin('https://Console.Example:443/'), 'https://console.example')
        self.assertEqual(https_origin('https://[::1]:8443/'), 'https://[::1]:8443')

    def test_no_http_userinfo_paths_query_fragment_or_bad_port(self):
        for value in ('http://console.example', 'https://user:pass@console.example', 'https://console.example/path',
                      'https://console.example?token=secret', 'https://console.example#x','https://console.example:bad',
                      'https://console.example:99999','https:// console.example', 'https://console..example', 'https://'):
            with self.subTest(value=value), self.assertRaises(AcceptanceError): https_origin(value)
        with self.assertRaises(AcceptanceError): https_origin('https://console.example:0')

    def test_explicit_domain_requires_deployment_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'.env').write_text('CORS_ORIGINS=https://console.example,https://localhost:8446\n')
            self.assertEqual(approved_api_base(root,'https://console.example:443',8446),'https://console.example')
            self.assertEqual(approved_api_base(root,None,8446),'https://localhost:8446')
            with self.assertRaises(AcceptanceError): approved_api_base(root,'https://other.example',8446)
            (root/'.env').write_text('CORS_ORIGINS=https://console.example\nCORS_ORIGINS=https://other.example\n')
            with self.assertRaises(AcceptanceError): approved_api_base(root,'https://console.example',8446)

    def test_missing_or_wildcard_allowlist_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for line in ('', 'CORS_ORIGINS=*\n', 'CORS_ORIGINS=http://console.example\n', 'CORS_ORIGINS=https://console.example,\n'):
                (root/'.env').write_text(line)
                with self.assertRaises(AcceptanceError): approved_api_base(root,'https://console.example',8443)

    @staticmethod
    def runtime():
        return {'environment':'production','deployment_scope':'production','deployment_id':'storage-lab-console-production-test',
                'console_role':'viewer','application_version':'5.2.0-rc.1','console_read_only':True,'ceph_mutations_enabled':False,
                'features':{'upgrade':True,'lab':False,'legacy_rgw':False,'legacy_rbd':False}}

    def test_runtime_scope_readonly_role_and_mutation_flags(self):
        good=self.runtime(); checker.validate_production_runtime(good,good['deployment_id'],'5.2.0-rc.1')
        for field,value in (('deployment_scope','staging'),('console_role','admin'),('console_read_only',False),('ceph_mutations_enabled',True)):
            row=self.runtime();row[field]=value
            with self.assertRaises(checker.client.ReadyCheckError): checker.validate_production_runtime(row,good['deployment_id'],'5.2.0-rc.1')
        for field in ('lab','legacy_rgw','legacy_rbd'):
            row=self.runtime();row['features'][field]=True
            with self.assertRaises(checker.client.ReadyCheckError): checker.validate_production_runtime(row,good['deployment_id'],'5.2.0-rc.1')

    def test_unapproved_target_rejected_before_credentials_or_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'compose.production.yml').write_text('services: {}')
            (root/'.env').write_text('COMPOSE_PROJECT_NAME=storage-lab-console-production-test\nAPP_INSTANCE_ID=storage-lab-console-production-test\nAPP_DEPLOYMENT_SCOPE=production\nCORS_ORIGINS=https://console.example\n')
            with patch.object(checker.client,'viewer_authorization') as auth, patch.object(checker.client,'get_json') as http, redirect_stdout(io.StringIO()):
                code=checker.main(['--deployment-directory',directory,'--base-url','https://other.example','--ca-file',str(root/'ca'), '--auth-user-file',str(root/'auth')])
            self.assertEqual(code,2);auth.assert_not_called();http.assert_not_called()

    def test_production_checker_rejects_staging_before_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'compose.production.yml').write_text('services: {}')
            (root/'.env').write_text('COMPOSE_PROJECT_NAME=storage-lab-console-staging-test\nAPP_INSTANCE_ID=storage-lab-console-staging-test\nAPP_DEPLOYMENT_SCOPE=staging\n')
            with patch.object(checker.client,'viewer_authorization') as auth, redirect_stdout(io.StringIO()):
                code=checker.main(['--deployment-directory',directory,'--base-url','https://localhost:8446','--ca-file',str(root/'ca'), '--auth-user-file',str(root/'auth')])
            self.assertEqual(code,2);auth.assert_not_called()


if __name__ == '__main__': unittest.main()
