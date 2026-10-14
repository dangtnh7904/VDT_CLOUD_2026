from contextlib import ExitStack, redirect_stdout
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from production_ops import backup_age, deployment_identity, container_checks, parse_filesystem_usage, volume_disk_checks, host_disk_check, validate_operator_runtime, validate_readiness_payload, main
from production_acceptance import AcceptanceError


class ProductionOpsTests(unittest.TestCase):
    @staticmethod
    def runtime_payload():
        return {'environment': 'production', 'deployment_id': 'storage-lab-console-staging-test',
                'deployment_scope':'staging', 'console_read_only':True, 'ceph_mutations_enabled':False,
                'console_role':'viewer', 'features':{'lab':False,'legacy_rgw':False,'legacy_rbd':False,'upgrade':True}}

    @staticmethod
    def ready_payload():
        return {'ready':True, 'status':'ready', 'blocking_dependencies':[],
                'features':{'upgrade':True,'lab':False,'legacy_rgw':False,'legacy_rbd':False},
                'dependencies':{'config':{'status':'ready','required':True},
                                'database':{'status':'ready','required':True,'schema_version':21},
                                'frontend':{'status':'ready','required':True},
                                'ceph_executor':{'status':'ready','required':True,'required_by':['upgrade']},
                                'rgw':{'status':'disabled','required':False}}}

    @staticmethod
    def response(payload, status=200, error=None):
        row = Mock()
        row.status = status; row.error = error
        row.summary.return_value = {'http_status':status, 'error_code':error}
        row.json.return_value = payload
        return row

    def isolated_main(self, ready, extra=None):
        """All source, HTTP and Docker boundaries are doubles; local files only."""
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            stack.enter_context(patch('production_ops.deployment_identity', return_value=('storage-lab-console-staging-test',8446)))
            stack.enter_context(patch('production_ops.load_accounts', return_value={'viewer':object()}))
            stack.enter_context(patch('production_ops.container_checks', return_value={'healthy':True}))
            stack.enter_context(patch('production_ops.host_disk_check', return_value={'status':'PASS'}))
            stack.enter_context(patch('production_ops.volume_disk_checks', return_value={'healthy':True,'volumes':[]}))
            stack.enter_context(patch('production_ops.backup_age', return_value={'healthy':True}))
            client = stack.enter_context(patch('production_ops.Client'))
            client.return_value.request.side_effect = [self.response(self.runtime_payload()), ready]
            output = stack.enter_context(redirect_stdout(io.StringIO()))
            if extra:
                extra(stack)
            code = main(['--deployment-directory',directory,'--ca-file',str(root/'ca'),
                         '--auth-user-file',str(root/'users'),'--backup-root',directory,'--report',str(root/'report.json')])
            path = root/'report.json'
            row = json.loads(path.read_bytes()) if path.exists() and path.stat().st_size else None
            return code, row, output.getvalue(), client

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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('production_ops.deployment_identity', return_value=('storage-lab-console-staging-test', 8446)), \
                 patch('production_ops.load_accounts', return_value={'viewer': object()}), \
                 patch('production_ops.Client') as client, \
                 patch('production_ops.container_checks', return_value={'healthy': True}), \
                 patch('production_ops.shutil.disk_usage', return_value=type('Usage', (), {'used': 10, 'total': 100, 'free':90})()), \
                 patch('production_ops.backup_age', return_value={'healthy': True}), \
                 patch('production_ops.volume_disk_checks', return_value={'healthy': False, 'volumes': [{'status': 'HIGH'}, {'status': 'UNAVAILABLE'}]}):
                client.return_value.request.side_effect = [self.response(self.runtime_payload()), self.response(self.ready_payload())]
                code = main(['--deployment-directory', directory, '--ca-file', str(root/'ca'),
                             '--auth-user-file', str(root/'users'), '--backup-root', directory,
                             '--report', str(root/'report.json')])
            report = json.loads((root/'report.json').read_bytes())
            self.assertEqual(code, 2)
            self.assertEqual(report['alerts'], ['VOLUME_FILESYSTEM_DISK_HIGH', 'VOLUME_FILESYSTEM_DISK_UNAVAILABLE'])

    def test_runtime_mutations_role_or_scope_mismatch_is_not_operational_pass(self):
        project='storage-lab-console-production-test'
        row={'environment':'production','deployment_id':project,'deployment_scope':'production','console_read_only':True,
             'ceph_mutations_enabled':False,'console_role':'viewer','features':{'lab':False,'legacy_rgw':False,'legacy_rbd':False}}
        validate_operator_runtime(row,project)
        for key,value in (('console_read_only',False),('ceph_mutations_enabled',True),('console_role','admin'),('deployment_scope','staging')):
            invalid={**row,key:value}
            with self.assertRaises(AcceptanceError): validate_operator_runtime(invalid,project)
        with self.assertRaises(AcceptanceError): validate_operator_runtime({**row,'features':{'lab':True}},project)

    def test_ready_payload_requires_boolean_ready_exact_status_and_empty_blockers(self):
        validate_readiness_payload(self.ready_payload())
        for payload in (None, [], {}, dict(self.ready_payload(), ready=1), dict(self.ready_payload(), ready=False),
                        dict(self.ready_payload(), status='not_ready'), dict(self.ready_payload(), blocking_dependencies=None),
                        dict(self.ready_payload(), blocking_dependencies=''), dict(self.ready_payload(), blocking_dependencies=['database'])):
            with self.subTest(payload=payload), self.assertRaises(AcceptanceError):
                validate_readiness_payload(payload)

    def test_ready_requires_every_core_dependency_required_and_ready(self):
        for name in ('config','database','frontend','ceph_executor'):
            for replacement in (None, {}, {'required':False,'status':'ready'}, {'required':1,'status':'ready'},
                                {'required':True,'status':'disabled'}, {'required':True,'status':'unavailable'}):
                payload = self.ready_payload(); payload['dependencies'][name] = replacement
                with self.subTest(name=name, replacement=replacement), self.assertRaises(AcceptanceError):
                    validate_readiness_payload(payload)

    def test_ready_requires_exact_current_integer_schema_version(self):
        for version in (None, True, 21.0, '21', 20, 22, [], {}):
            payload = self.ready_payload(); payload['dependencies']['database']['schema_version'] = version
            with self.subTest(version=version), self.assertRaisesRegex(AcceptanceError, 'DATABASE_SCHEMA_VERSION_NOT_VERIFIED'):
                validate_readiness_payload(payload)

    def test_ready_cannot_hide_legacy_feature_or_extra_blocking_dependency(self):
        for key in ('upgrade','lab','legacy_rgw','legacy_rbd'):
            payload = self.ready_payload(); payload['features'][key] = False if key == 'upgrade' else True
            with self.subTest(key=key), self.assertRaises(AcceptanceError):
                validate_readiness_payload(payload)
        for replacement in (None, {'status':'ready','required':True}, {'status':'unavailable','required':False}):
            payload = self.ready_payload(); payload['dependencies']['rgw'] = replacement
            with self.assertRaises(AcceptanceError): validate_readiness_payload(payload)
        for extra in (None, {'required':True,'status':'unavailable'}, {'required':'false','status':'ready'}):
            payload = self.ready_payload(); payload['dependencies']['unknown'] = extra
            with self.assertRaises(AcceptanceError): validate_readiness_payload(payload)

    def test_http200_malformed_ready_is_alert_not_pass_and_probe_continues(self):
        invalid = self.ready_payload(); invalid['dependencies']['database']['schema_version'] = 20
        code, row, output, client = self.isolated_main(self.response(invalid))
        self.assertEqual(code, 2)
        self.assertEqual(row['status'], 'ALERT')
        self.assertIn('DATABASE_SCHEMA_VERSION_NOT_VERIFIED', row['alerts'])
        self.assertFalse(row['checks']['ready']['payload_verified'])
        self.assertIn('backup', row['checks'])
        self.assertEqual(client.return_value.request.call_count, 2)

    def test_http200_protocol_error_summary_cannot_pass_readiness(self):
        ready = self.response(self.ready_payload(), error='RESPONSE_TOO_LARGE')
        code, row, output, _ = self.isolated_main(ready)
        self.assertEqual(code, 2)
        self.assertEqual(row['alerts'], ['DEPENDENCY_READINESS_PAYLOAD_INVALID'])
        ready.json.assert_not_called()

    def test_http200_invalid_json_ready_is_alert_not_traceback(self):
        ready = self.response(None); ready.json.side_effect = AcceptanceError('INVALID_JSON_RESPONSE')
        code, row, _, _ = self.isolated_main(ready)
        self.assertEqual(code, 2)
        self.assertEqual(row['alerts'], ['INVALID_JSON_RESPONSE'])
        self.assertFalse(row['checks']['ready']['payload_verified'])

    def test_http503_stays_alert_and_valid_http200_can_pass(self):
        code, row, _, _ = self.isolated_main(self.response({'ready':False},status=503))
        self.assertEqual(code, 2)
        self.assertEqual(row['alerts'], ['DEPENDENCY_NOT_READY'])
        code, row, _, _ = self.isolated_main(self.response(self.ready_payload()))
        self.assertEqual(code, 0)
        self.assertEqual(row['status'], 'PASS')
        self.assertTrue(row['checks']['ready']['payload_verified'])

    def test_existing_report_is_preserved_before_auth_network_or_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'report.json'; path.write_bytes(b'preserve-original')
            with patch('production_ops.load_accounts') as accounts, patch('production_ops.Client') as client, \
                 patch('production_ops.deployment_identity') as identity, redirect_stdout(io.StringIO()) as output:
                code = main(['--deployment-directory',directory,'--ca-file','fake-ca','--auth-user-file','fake-users',
                             '--backup-root',directory,'--report',str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(path.read_bytes(), b'preserve-original')
            self.assertEqual(json.loads(output.getvalue())['alerts'], ['OPERATIONS_REPORT_ALREADY_EXISTS'])
            accounts.assert_not_called(); client.assert_not_called(); identity.assert_not_called()
            self.assertNotIn(directory, output.getvalue())

    def test_report_create_error_is_safe_and_precedes_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); blocked = root/'not-a-directory'; blocked.write_text('do-not-modify')
            with patch('production_ops.load_accounts') as accounts, patch('production_ops.Client') as client, redirect_stdout(io.StringIO()) as output:
                code = main(['--deployment-directory',directory,'--ca-file','fake-ca','--auth-user-file','fake-users',
                             '--backup-root',directory,'--report',str(blocked/'report.json')])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())['alerts'], ['OPERATIONS_REPORT_CREATE_FAILED'])
            accounts.assert_not_called(); client.assert_not_called()
            self.assertNotIn(directory, output.getvalue())
            self.assertEqual(blocked.read_text(), 'do-not-modify')

    def test_report_is_reserved_before_authentication_and_source_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'report.json'
            def inspect_reservation(*args):
                self.assertTrue(path.exists())
                self.assertEqual(path.stat().st_size, 0)
                raise AcceptanceError('ACCOUNT_FILE_UNAVAILABLE')
            with patch('production_ops.deployment_identity', return_value=('storage-lab-console-staging-test',8446)), \
                 patch('production_ops.load_accounts', side_effect=inspect_reservation), patch('production_ops.Client') as client, redirect_stdout(io.StringIO()):
                code = main(['--deployment-directory',directory,'--ca-file','fake-ca','--auth-user-file','fake-users',
                             '--backup-root',directory,'--report',str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(path.read_bytes())['alerts'], ['ACCOUNT_FILE_UNAVAILABLE'])
            client.assert_not_called()

    def test_report_write_error_is_failure_without_raw_exception_or_path(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Mock(); fake.write.side_effect = OSError('PRIVATE_PASSWORD_AND_PATH')
            with patch('production_ops.reserve_report', return_value=fake), \
                 patch('production_ops.deployment_identity', side_effect=AcceptanceError('PRODUCTION_COMPOSE_REQUIRED')), redirect_stdout(io.StringIO()) as output:
                code = main(['--deployment-directory',directory,'--ca-file','fake-ca','--auth-user-file','fake-users',
                             '--backup-root',directory,'--report',str(Path(directory)/'report.json')])
            self.assertEqual(code, 2)
            self.assertIn('OPERATIONS_REPORT_WRITE_FAILED',json.loads(output.getvalue())['alerts'])
            self.assertNotIn('PRIVATE_PASSWORD_AND_PATH',output.getvalue())
            self.assertNotIn(directory,output.getvalue())
            fake.close.assert_called_once()

    def test_report_fsync_and_close_errors_cannot_return_pass(self):
        for stage in ('fsync','close'):
            fake = Mock(); fake.fileno.return_value = 9
            if stage == 'close': fake.close.side_effect = OSError('PRIVATE_CLOSE_PATH')
            with tempfile.TemporaryDirectory() as directory, patch('production_ops.reserve_report', return_value=fake), \
                 patch('production_ops.deployment_identity', side_effect=AcceptanceError('PRODUCTION_COMPOSE_REQUIRED')), \
                 patch('production_ops.os.fsync', side_effect=OSError('PRIVATE_FSYNC_PATH') if stage == 'fsync' else None), redirect_stdout(io.StringIO()) as output:
                code = main(['--deployment-directory',directory,'--ca-file','fake-ca','--auth-user-file','fake-users',
                             '--backup-root',directory,'--report',str(Path(directory)/'report.json')])
            self.assertEqual(code, 2)
            self.assertIn('OPERATIONS_REPORT_WRITE_FAILED',json.loads(output.getvalue())['alerts'])
            self.assertNotIn('PRIVATE_',output.getvalue())

    def test_otherwise_passing_probe_is_alert_for_any_report_persistence_error(self):
        for stage in ('write','flush','fsync','close'):
            handle = Mock(); handle.fileno.return_value = 9
            if stage != 'fsync': getattr(handle,stage).side_effect = OSError('PRIVATE_STORAGE_ERROR')
            def additional_mocks(stack):
                stack.enter_context(patch('production_ops.reserve_report', return_value=handle))
                stack.enter_context(patch('production_ops.os.fsync', side_effect=OSError('PRIVATE_FSYNC') if stage == 'fsync' else None))
            code, row, output, _ = self.isolated_main(self.response(self.ready_payload()), additional_mocks)
            with self.subTest(stage=stage):
                self.assertEqual(code, 2)
                self.assertIsNone(row)
                self.assertEqual(json.loads(output)['status'], 'ALERT')
                self.assertEqual(json.loads(output)['alerts'], ['OPERATIONS_REPORT_WRITE_FAILED'])
                self.assertNotIn('PRIVATE_', output)
                handle.close.assert_called_once()

    def test_unexpected_process_failure_releases_reserved_file_and_is_not_hidden(self):
        handle = Mock()
        with tempfile.TemporaryDirectory() as directory, patch('production_ops.reserve_report', return_value=handle), \
             patch('production_ops.deployment_identity', side_effect=RuntimeError('PROGRAMMER_FAULT')), redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(RuntimeError, 'PROGRAMMER_FAULT'):
                main(['--deployment-directory',directory,'--ca-file','fake-ca','--auth-user-file','fake-users',
                      '--backup-root',directory,'--report',str(Path(directory)/'report.json')])
        handle.close.assert_called_once()
        self.assertEqual(output.getvalue(), '')

    def test_untrusted_acceptance_error_text_is_replaced_by_stable_code(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('production_ops.deployment_identity', side_effect=AcceptanceError('PRIVATE_URL https://secret/path')), redirect_stdout(io.StringIO()) as output:
            path = Path(directory)/'report.json'
            code = main(['--deployment-directory',directory,'--ca-file','fake-ca','--auth-user-file','fake-users',
                         '--backup-root',directory,'--report',str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(path.read_bytes())['alerts'], ['OPERATIONS_RESPONSE_INVALID'])
            self.assertNotIn('https://secret',output.getvalue())


if __name__ == '__main__': unittest.main()
