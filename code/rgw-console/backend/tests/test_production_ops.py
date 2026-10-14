import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from production_ops import backup_age, deployment_identity, container_checks, parse_filesystem_usage, volume_disk_checks, host_disk_check, main
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
                (item/'backup-metadata.json').write_text(json.dumps({'format_version':1,'status':status,'started_at':(datetime.now(timezone.utc)-timedelta(hours=age)).isoformat()}))
                self.assertFalse(backup_age(root,26)['healthy'])
            (item/'backup-metadata.json').write_text(json.dumps({'format_version':1,'status':'COMPLETE','started_at':datetime.now(timezone.utc).isoformat()}))
            self.assertTrue(backup_age(root,26)['healthy'])

    def test_container_inspection_checks_exact_project_without_mutations(self):
        project = 'storage-lab-console-staging-test'
        rows = [{'Id':f'{index+1:064x}','Config':{'Labels':{'com.docker.compose.project':project,'com.docker.compose.service':service}},'State':{'Running':True,'Status':'running'}} for index,service in enumerate(('api','postgres','ingress'))]
        ids = ' '.join(row['Id'] for row in rows)
        with patch('production_ops.run_docker',side_effect=[ids,json.dumps(rows)]) as docker:
            self.assertTrue(container_checks(project)['healthy'])
            self.assertEqual([call.args[0][0] for call in docker.call_args_list],['ps','inspect'])
        rows[0]['Config']['Labels']['com.docker.compose.project']='other'
        with patch('production_ops.run_docker',side_effect=[ids,json.dumps(rows)]), self.assertRaises(AcceptanceError): container_checks(project)

    def test_powershell_utc_z_checkpoint_is_supported_on_python_310(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root/'backup-powershell'; item.mkdir()
            stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + '0Z'
            (item/'backup-metadata.json').write_text(json.dumps({'format_version':1,'status':'COMPLETE','started_at':stamp}))
            self.assertTrue(backup_age(root,26)['healthy'])

    def test_malformed_checkpoint_shape_does_not_crash_monitor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root/'backup-invalid'; item.mkdir()
            for row in ([], None, {'status':'COMPLETE','started_at':42},
                        {'status':'COMPLETE','started_at':'not-a-timestamp'}):
                (item/'backup-metadata.json').write_text(json.dumps(row))
                self.assertFalse(backup_age(root,26)['healthy'])

    def test_posix_df_retains_reserved_space_percentage_and_bytes(self):
        output = 'Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/sdc 1000 800 100 89% /etc/resolv.conf\n'
        usage = parse_filesystem_usage(output)
        self.assertEqual(usage['used_percent'], 89)
        self.assertEqual(usage['reported_used_percent'], 89)
        self.assertEqual(usage['total_bytes'], 1024000)
        self.assertEqual(usage['used_bytes'], 819200)
        self.assertEqual(usage['available_bytes'], 102400)

    def test_missing_malformed_or_impossible_df_is_not_zero_usage(self):
        for output in ('', 'permission denied', 'Filesystem\n/dev/sdc 0 0 0 0% /x',
                       'Filesystem\n/dev/sdc 100 60 50 60% /x',
                       'Filesystem\n/dev/sdc 100 110 0 100% /x',
                       'Filesystem\n/dev/sdc 100 90 10 101% /x',
                       'Filesystem\n/dev/sdc 1000 900 100 1% /x',
                       'Filesystem\n/dev/sdc 99999999999999999999999999 0 0 0% /x',
                       'Filesystem\n/dev/sdc 100 90 10 90% /x\nextra',
                       'Filesystem\n/dev/sdc 100 90 -10 90% /x'):
            with self.subTest(output=output), self.assertRaises(AcceptanceError):
                parse_filesystem_usage(output)

    def test_busybox_total_ratio_is_converted_to_conservative_free_space_ratio(self):
        usage = parse_filesystem_usage('Filesystem\n/dev/sdc 1000 800 100 80% /alias\n')
        self.assertEqual(usage['reported_used_percent'], 80)
        self.assertEqual(usage['used_percent'], 89)

    def test_backup_from_other_project_or_unknown_format_cannot_clear_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); item = root/'backup-other'; item.mkdir()
            project = 'storage-lab-console-staging-test'
            row = {'format_version':1, 'status':'COMPLETE', 'source_project':'other-project',
                   'started_at':datetime.now(timezone.utc).isoformat()}
            path = item/'backup-metadata.json'
            path.write_text(json.dumps(row))
            self.assertFalse(backup_age(root,26,project)['healthy'])
            row.update(source_project=project, format_version=2); path.write_text(json.dumps(row))
            self.assertFalse(backup_age(root,26,project)['healthy'])
            row.update(format_version=1); path.write_text(json.dumps(row))
            report = backup_age(root,26,project)
            self.assertTrue(report['healthy'])
            self.assertTrue(report['source_project_verified'])
            self.assertTrue(report['archive_integrity_and_restore_not_checked_by_this_age_probe'])

    def test_invalid_container_shape_cardinality_and_duplicate_identity_fail_closed(self):
        project = 'storage-lab-console-staging-test'
        valid = {'Id':'1'*64, 'Config':{'Labels':{'com.docker.compose.project':project,
                                              'com.docker.compose.service':'api'}}, 'State':{'Running':True}}
        rows_to_try = ({}, [], [None], [valid,valid], [{'Id':'1'*64}],
                       [dict(valid, State=None)], [dict(valid, Config=None)],
                       [dict(valid, State={'Health':None})])
        for rows in rows_to_try:
            with self.subTest(rows=rows), patch('production_ops.run_docker', side_effect=['1'*64,json.dumps(rows)]):
                with self.assertRaises(AcceptanceError): container_checks(project)
        with patch('production_ops.run_docker', side_effect=['1'*64+' '+'2'*64,json.dumps([valid,valid])]):
            with self.assertRaises(AcceptanceError): container_checks(project)

    @staticmethod
    def disk_fixture(include_executor=True):
        project = 'storage-lab-console-staging-test'
        targets = [('postgres', 'postgres-data', '/var/lib/postgresql/data'),
                   ('api', 'evidence', '/var/lib/storage-lab-console/evidence')]
        if include_executor:
            targets.append(('executor', 'executor-state', '/var/lib/rbd-executor'))
        rows = []; volumes = {}
        for index, (service, key, target) in enumerate(targets):
            name = f'{project}_{key}'
            rows.append({'Id': f'{index + 1:064x}',
                         'Config': {'Labels': {'com.docker.compose.project': project,
                                               'com.docker.compose.service': service}},
                         'State': {'Running': True},
                         'Mounts': [{'Destination': target, 'Type': 'volume', 'Name': name}]})
            volumes[name] = {'Name': name, 'Labels': {'com.docker.compose.project': project,
                                                     'com.docker.compose.volume': key}}
        return project, rows, volumes

    def disk_runner(self, rows, volumes, percent=6):
        def run(arguments):
            if arguments[0] == 'ps': return ' '.join(row['Id'] for row in rows)
            if arguments[0] == 'inspect': return json.dumps(rows)
            if arguments[:2] == ['volume', 'inspect']: return json.dumps([volumes[arguments[2]]])
            if arguments[0] == 'exec':
                self.assertEqual(arguments[2:4], ['df', '-Pk'])
                self.assertIn(arguments[1], [row['Id'] for row in rows])
                return f'Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/sdc 1000 {percent * 10} {1000 - percent * 10} {percent}% /etc/resolv.conf\n'
            self.fail(f'Unexpected Docker operation: {arguments[0]}')
        return run

    def test_volume_probe_verifies_labels_and_uses_only_fixed_read_commands(self):
        project, rows, volumes = self.disk_fixture()
        with patch('production_ops.run_docker', side_effect=self.disk_runner(rows, volumes)) as docker:
            report = volume_disk_checks(project, 85)
        self.assertTrue(report['healthy'])
        self.assertEqual([item['status'] for item in report['volumes']], ['PASS'] * 3)
        self.assertTrue(report['shared_filesystem_values_must_not_be_summed'])
        self.assertTrue(report['does_not_measure_backing_host_or_volume_quota'])
        self.assertEqual([call.args[0][0] for call in docker.call_args_list],
                         ['ps', 'inspect', 'volume', 'exec', 'volume', 'exec', 'volume', 'exec'])

    def test_high_volume_filesystem_uses_alert_threshold(self):
        project, rows, volumes = self.disk_fixture()
        with patch('production_ops.run_docker', side_effect=self.disk_runner(rows, volumes, 85)):
            report = volume_disk_checks(project, 85)
        self.assertFalse(report['healthy'])
        self.assertEqual([item['status'] for item in report['volumes']], ['HIGH'] * 3)

    def test_wrong_volume_project_or_role_blocks_exec_for_that_mount(self):
        for field in ('com.docker.compose.project', 'com.docker.compose.volume'):
            project, rows, volumes = self.disk_fixture()
            volumes[f'{project}_postgres-data']['Labels'][field] = 'other'
            with patch('production_ops.run_docker', side_effect=self.disk_runner(rows, volumes)) as docker:
                report = volume_disk_checks(project, 85)
            self.assertEqual(report['volumes'][0]['reason'], 'VOLUME_PROJECT_OR_ROLE_MISMATCH')
            self.assertFalse(report['healthy'])
            self.assertFalse(any(call.args[0][:2] == ['exec', rows[0]['Id']] for call in docker.call_args_list))

    def test_wrong_container_project_or_id_blocks_all_exec(self):
        for kind in ('project', 'id'):
            project, rows, volumes = self.disk_fixture()
            if kind == 'project': rows[0]['Config']['Labels']['com.docker.compose.project'] = 'other'
            else: rows[0]['Id'] = 'unsafe-id'
            with patch('production_ops.run_docker', side_effect=self.disk_runner(rows, volumes)) as docker:
                with self.assertRaises(AcceptanceError): volume_disk_checks(project, 85)
            self.assertFalse(any(call.args[0][0] == 'exec' for call in docker.call_args_list))

    def test_missing_required_or_bind_mount_is_unavailable_without_exec(self):
        for mount in ([], [{'Destination': '/var/lib/postgresql/data', 'Type': 'bind', 'Name': 'anything'}]):
            project, rows, volumes = self.disk_fixture()
            rows[0]['Mounts'] = mount
            with patch('production_ops.run_docker', side_effect=self.disk_runner(rows, volumes)) as docker:
                report = volume_disk_checks(project, 85)
            self.assertEqual(report['volumes'][0]['status'], 'UNAVAILABLE')
            self.assertFalse(any(call.args[0][:2] == ['exec', rows[0]['Id']] for call in docker.call_args_list))

    def test_optional_executor_not_deployed_is_explicit_not_run(self):
        project, rows, volumes = self.disk_fixture(include_executor=False)
        with patch('production_ops.run_docker', side_effect=self.disk_runner(rows, volumes)):
            report = volume_disk_checks(project, 85)
        self.assertTrue(report['healthy'])
        self.assertEqual(report['volumes'][2]['status'], 'NOT_RUN')

    def test_stopped_volume_service_never_execs_and_is_not_healthy(self):
        project, rows, volumes = self.disk_fixture()
        rows[0]['State']['Running'] = False
        with patch('production_ops.run_docker', side_effect=self.disk_runner(rows, volumes)) as docker:
            report = volume_disk_checks(project, 85)
        self.assertEqual(report['volumes'][0]['reason'], 'VOLUME_SERVICE_NOT_RUNNING')
        self.assertFalse(any(call.args[0][:2] == ['exec', rows[0]['Id']] for call in docker.call_args_list))

    def test_duplicate_service_does_not_choose_arbitrary_container(self):
        project, rows, volumes = self.disk_fixture()
        rows[2]['Config']['Labels']['com.docker.compose.service'] = 'postgres'
        with patch('production_ops.run_docker', side_effect=self.disk_runner(rows, volumes)) as docker:
            report = volume_disk_checks(project, 85)
        self.assertEqual(report['volumes'][0]['reason'], 'VOLUME_SERVICE_MISSING_OR_AMBIGUOUS')
        self.assertFalse(any(call.args[0][0] == 'exec' and call.args[0][1] in {rows[0]['Id'], rows[2]['Id']}
                             for call in docker.call_args_list))

    def test_failed_df_is_unavailable_and_other_mounts_are_still_checked(self):
        project, rows, volumes = self.disk_fixture()
        runner = self.disk_runner(rows, volumes)
        def fail_first_exec(arguments):
            if arguments[:2] == ['exec', rows[0]['Id']]: raise AcceptanceError('DOCKER_OPERATION_FAILED')
            return runner(arguments)
        with patch('production_ops.run_docker', side_effect=fail_first_exec):
            report = volume_disk_checks(project, 85)
        self.assertFalse(report['healthy'])
        self.assertEqual([item['status'] for item in report['volumes']], ['UNAVAILABLE', 'PASS', 'PASS'])

    def test_host_storage_uses_raw_threshold_and_missing_paths_are_not_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(host_disk_check(root/'missing',85)['status'], 'UNAVAILABLE')
            for used, status in ((84.999, 'PASS'), (85, 'HIGH'), (100, 'HIGH')):
                usage = type('Usage', (), {'used':used,'total':100,'free':100-used})()
                with patch('production_ops.shutil.disk_usage',return_value=usage):
                    self.assertEqual(host_disk_check(root,85)['status'], status)
            with patch('production_ops.shutil.disk_usage', side_effect=OSError):
                self.assertEqual(host_disk_check(root,85)['status'], 'UNAVAILABLE')

    def test_main_emits_volume_high_and_unavailable_alerts_without_mutations(self):
        class Response:
            status = 200
            def summary(self): return {'http_status': 200}
            def json(self): return {'environment': 'production', 'deployment_id': 'storage-lab-console-staging-test'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('production_ops.deployment_identity', return_value=('storage-lab-console-staging-test', 8446)), \
                 patch('production_ops.load_accounts', return_value={'viewer': object()}), \
                 patch('production_ops.Client') as client, \
                 patch('production_ops.container_checks', return_value={'healthy': True}), \
                 patch('production_ops.shutil.disk_usage', return_value=type('Usage', (), {'used': 10, 'total': 100, 'free':90})()), \
                 patch('production_ops.backup_age', return_value={'healthy': True}), \
                 patch('production_ops.volume_disk_checks', return_value={'healthy': False, 'volumes': [{'status': 'HIGH'}, {'status': 'UNAVAILABLE'}]}):
                client.return_value.request.return_value = Response()
                code = main(['--deployment-directory', directory, '--ca-file', str(root/'ca'),
                             '--auth-user-file', str(root/'users'), '--backup-root', directory,
                             '--report', str(root/'report.json')])
            report = json.loads((root/'report.json').read_bytes())
            self.assertEqual(code, 2)
            self.assertEqual(report['alerts'], ['VOLUME_FILESYSTEM_DISK_HIGH', 'VOLUME_FILESYSTEM_DISK_UNAVAILABLE'])


if __name__ == '__main__': unittest.main()
