import unittest
from unittest.mock import patch
from starlette.requests import Request
from types import SimpleNamespace
from app.main import runtime_config


class RuntimeMarkerTests(unittest.TestCase):
    def test_marker_and_role_come_from_configuration_and_authenticated_state(self):
        settings = SimpleNamespace(console_read_only=True, app_env='production', app_instance_id='storage-lab-console-staging-test',
            feature_upgrade=True, feature_lab=False, feature_legacy_rgw=False, feature_legacy_rbd=False)
        scope = {'type':'http','method':'GET','path':'/api/runtime-config','headers':[],
                 'state':{'console_actor':'staging-viewer','console_role':'viewer'}}
        with patch('app.main.get_settings',return_value=settings), patch.dict('os.environ', {'APP_DEPLOYMENT_SCOPE':'staging'}):
            result = runtime_config(Request(scope))
        self.assertEqual(result['environment'],'production')
        self.assertEqual(result['deployment_scope'],'staging')
        self.assertEqual(result['deployment_id'],settings.app_instance_id)
        self.assertEqual(result['console_role'],'viewer')

    def test_unauthenticated_lab_does_not_claim_admin_login(self):
        settings = SimpleNamespace(console_read_only=True, app_env='lab', app_instance_id='lab',
            feature_upgrade=True, feature_lab=False, feature_legacy_rgw=False, feature_legacy_rbd=False)
        scope = {'type':'http','method':'GET','path':'/api/runtime-config','headers':[],
                 'state':{'console_actor':'','console_role':'admin'}}
        with patch('app.main.get_settings',return_value=settings):
            self.assertIsNone(runtime_config(Request(scope))['console_role'])


if __name__ == '__main__': unittest.main()
