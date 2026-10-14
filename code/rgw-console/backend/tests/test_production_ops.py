import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from production_ops import backup_age, deployment_identity, container_checks
from production_acceptance import AcceptanceError


class ProductionOpsTests(unittest.TestCase):
    def test_project_marker_is_required_before_docker_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'compose.production.yml').write_text('services: {}')
            (root/'.env').write_text('COMPOSE_PROJECT_NAME=storage-lab-console-staging-test\nAPP_INSTANCE_ID=storage-lab-console-staging-test\nCONSOLE_HTTPS_PORT=8446\n')
            self.assertEqual(deployment_identity(root), ('storage-lab-console-staging-test',8446))
            (root/'.env').write_text('COMPOSE_PROJECT_NAME=other-project\n')
            with self.assertRaises(AcceptanceError): deployment_identity(root)

    def test_missing_failed_future_and_old_backups_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(backup_age(root,26)['healthy'])
            item = root/'backup-test'; item.mkdir()
            for status, age in [('FAILED',0),('COMPLETE',30),('COMPLETE',-1)]:
                (item/'backup-metadata.json').write_text(json.dumps({'status':status,'started_at':(datetime.now(timezone.utc)-timedelta(hours=age)).isoformat()}))
                self.assertFalse(backup_age(root,26)['healthy'])
            (item/'backup-metadata.json').write_text(json.dumps({'status':'COMPLETE','started_at':datetime.now(timezone.utc).isoformat()}))
            self.assertTrue(backup_age(root,26)['healthy'])

    def test_container_inspection_checks_exact_project_without_mutations(self):
        project = 'storage-lab-console-staging-test'
        rows = [{'Config':{'Labels':{'com.docker.compose.project':project,'com.docker.compose.service':service}},'State':{'Running':True,'Status':'running'}} for service in ('api','postgres','ingress')]
        with patch('production_ops.run_docker',side_effect=['abcde0123456',json.dumps(rows)]) as docker:
            self.assertTrue(container_checks(project)['healthy'])
            self.assertEqual([call.args[0][0] for call in docker.call_args_list],['ps','inspect'])
        rows[0]['Config']['Labels']['com.docker.compose.project']='other'
        with patch('production_ops.run_docker',side_effect=['abcde0123456',json.dumps(rows)]), self.assertRaises(AcceptanceError): container_checks(project)


if __name__ == '__main__': unittest.main()
