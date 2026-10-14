from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'deploy' / 'ssh' / 'console-readonly-dispatch.py'
spec = importlib.util.spec_from_file_location('console_readonly_dispatch_tests', SCRIPT)
dispatch = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dispatch
spec.loader.exec_module(dispatch)
FSID = '11111111-2222-3333-4444-555555555555'
POLICY = dispatch.validate_policy({'expected_fsid': FSID, 'allowed_osds': [0, 2, 5], 'collector_sha256': 'a' * 64})
HELPER = dispatch.HELPER_PATH.as_posix()


class CommandPolicyTests(unittest.TestCase):
    def test_every_current_fixed_inventory_argv_matches_allowlist(self):
        source = (ROOT / 'rbd-console' / 'src' / 'executor.js').read_text(encoding='utf-8')
        commands = source.split('const INVENTORY_COMMANDS = {', 1)[1].split('\n};', 1)[0]
        rows = re.findall(r'"ceph\.[a-z_]+": (\[[^\n]+\]),', commands)
        self.assertGreaterEqual(len(rows), 18)
        for row in rows:
            command = ' '.join(json.loads(row))
            with self.subTest(command=command):
                self.assertEqual(dispatch.parse_command(command, POLICY).kind, 'ceph')
                self.assertEqual(dispatch.parse_command('sudo -n ' + command, POLICY).kind, 'ceph')

    def test_current_collect_and_environment_transport_frames_work_without_sudo(self):
        for sudo in ['', 'sudo -n ']:
            for inner_sudo in ['', ' --sudo-ceph']:
                with self.subTest(sudo=sudo, inner_sudo=inner_sudo):
                    plan = dispatch.parse_command(f'{sudo}python3 {HELPER} --osd 0 --osd 5{inner_sudo} --timeout 45', POLICY)
                    self.assertEqual((plan.kind, plan.osd_ids, plan.timeout), ('collect', (0, 5), 45))
                    self.assertEqual(dispatch.parse_command(f'{sudo}python3 {HELPER} --environment-only{inner_sudo} --timeout 2', POLICY).kind, 'environment')

    def test_shell_paths_overrides_write_commands_and_legacy_surfaces_are_rejected(self):
        rejected = [
            '', 'bash', 'internal-sftp', 'scp -t /tmp/a', 'ceph auth get client.admin',
            'ceph config set mon.a key value', 'ceph mon add a 1.2.3.4', 'ceph orch restart mgr',
            'ceph osd reweight 0 0', 'ceph osd getmap -o /tmp/owned', 'rbd ls --format=json',
            'sudo ceph fsid', 'sudo -n -u root ceph fsid', 'sudo -n sudo -n ceph fsid',
            'ceph fsid; id', 'ceph fsid && id', 'ceph fsid\nid', 'ceph\tfsid',
            'ceph fsid > /tmp/x', 'ceph fsid $(id)', 'ceph fsid `id`', 'ceph  fsid',
            f'python3 -c print(1)', f'python3 /tmp/collect_osd.py --osd 0 --timeout 45',
            f'python3 {HELPER} --all --timeout 45', f'python3 {HELPER} --osd 0 --ceph-bin /bin/sh --timeout 45',
            f'python3 {HELPER} --osd 0 --conf /tmp/conf --timeout 45',
            f'python3 {HELPER} --osd 0 --name client.admin --timeout 45',
            f'python3 {HELPER} --osd 0 --keyring /tmp/key --timeout 45',
            f'python3 {HELPER} --osd 0 --output /etc/ceph/x --timeout 45',
            f'python3 {HELPER} --osd 0 --timeout 45 --version',
            f'python3 {HELPER} --environment-only --timeout 45',
        ]
        for command in rejected:
            with self.subTest(command=command), self.assertRaises(dispatch.Rejected):
                dispatch.parse_command(command, POLICY)

    def test_osd_scope_duplicates_count_and_timeout_are_bounded(self):
        for selection in ['--osd 3', '--osd -1', '--osd 00', '--osd 0 --osd 0', '--osd 99999999999']:
            with self.subTest(selection=selection), self.assertRaises(dispatch.Rejected):
                dispatch.parse_command(f'python3 {HELPER} {selection} --timeout 45', POLICY)
        for timeout in ['0', '46', '1e9', 'nan', 'inf', '-1']:
            with self.subTest(timeout=timeout), self.assertRaises(dispatch.Rejected):
                dispatch.parse_command(f'python3 {HELPER} --osd 0 --timeout {timeout}', POLICY)
        large_policy = dispatch.Policy(FSID, frozenset(range(32)), 'a' * 64)
        selection = ' '.join(f'--osd {number}' for number in range(17))
        with self.assertRaises(dispatch.Rejected):
            dispatch.parse_command(f'python3 {HELPER} {selection} --timeout 45', large_policy)

    def test_policy_rejects_unknown_fields_invalid_hash_or_ids(self):
        original = {'expected_fsid': FSID, 'allowed_osds': [0], 'collector_sha256': 'a' * 64}
        for raw in [None, {**original, 'ceph_name': 'client.admin'}, {**original, 'expected_fsid': 'bad'},
            {**original, 'allowed_osds': [True]}, {**original, 'allowed_osds': []},
            {**original, 'allowed_osds': [0, 0]}, {**original, 'collector_sha256': 'bad'}]:
            with self.subTest(policy=raw), self.assertRaises(dispatch.Rejected):
                dispatch.validate_policy(raw)


class ExecutionTests(unittest.TestCase):
    def runner(self, *, fsids=None):
        values = iter(fsids or [FSID, FSID])
        runner = Mock()

        def run(args, **kwargs):
            if tuple(args[-1:]) == ('fsid',):
                return 0, (next(values) + '\n').encode()
            return 0, b'{"health":"ok"}'

        runner.run.side_effect = run
        runner.evidence.return_value = {'exit_code': 0, 'data': {}, 'format': 'json'}
        return runner

    def test_direct_execution_injects_only_fixed_readonly_identity_and_paths(self):
        runner = self.runner()
        output = dispatch.execute(dispatch.parse_command('sudo -n ceph status --format=json', POLICY), POLICY, runner)
        self.assertEqual(json.loads(output), {'health': 'ok'})
        self.assertEqual(runner.run.call_count, 3)
        for call in runner.run.call_args_list:
            args = call.args[0]
            self.assertEqual(tuple(args[:len(dispatch.ceph_prefix())]), dispatch.ceph_prefix())
            self.assertNotIn('sudo', args)
            self.assertNotIn('client.admin', args)

    def test_fsid_mismatch_before_and_after_never_returns_collection(self):
        for fsids, count in [(['aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'], 1),
            ([FSID, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'], 3)]:
            runner = self.runner(fsids=fsids)
            with self.subTest(fsids=fsids), self.assertRaisesRegex(dispatch.Rejected, 'SSH_FSID_MISMATCH'):
                dispatch.execute(dispatch.Plan('ceph', ('status', '--format=json')), POLICY, runner)
            self.assertEqual(runner.run.call_count, count)

    def test_helper_cannot_override_binary_identity_or_selected_osds(self):
        runner = self.runner()
        observed = []

        def collect(**kwargs):
            observed.append(kwargs)
            kwargs['runner']([*dispatch.ceph_prefix(), 'osd', 'metadata', '2', '--format=json'])
            return {'cluster_fsid': FSID, 'osds': []}

        with patch.object(dispatch, 'load_helper', return_value=SimpleNamespace(collect=collect)):
            result = dispatch.execute(dispatch.Plan('collect', osd_ids=(2,)), POLICY, runner)
        self.assertEqual(json.loads(result)['cluster_fsid'], FSID)
        self.assertEqual(observed[0]['ceph_bin'], '/usr/bin/ceph')
        self.assertEqual(observed[0]['ceph_args'], dispatch.ceph_prefix()[1:])
        self.assertEqual(observed[0]['osd_ids'], (2,))

    def test_helper_catching_rejection_cannot_convert_it_into_success(self):
        for invalid in [['sudo', '-n', 'ceph', 'status'],
            [*dispatch.ceph_prefix(), 'auth', 'get', 'client.admin'],
            [*dispatch.ceph_prefix(), 'osd', 'metadata', '5', '--format=json']]:
            runner = self.runner()

            def collect(**kwargs):
                try:
                    kwargs['runner'](invalid)
                except Exception:
                    pass  # The legacy helper catches per-command failures.
                return {'cluster_fsid': FSID, 'osds': []}

            with self.subTest(command=invalid), patch.object(dispatch, 'load_helper', return_value=SimpleNamespace(collect=collect)):
                with self.assertRaisesRegex(dispatch.Rejected, 'SSH_HELPER_COMMAND_REJECTED'):
                    dispatch.execute(dispatch.Plan('collect', osd_ids=(2,)), POLICY, runner)
            runner.evidence.assert_not_called()

    def test_environment_probes_use_only_fixed_absolute_binaries(self):
        runner = self.runner()

        def collect_environment(**kwargs):
            kwargs['runner'](['ssh', '-V'])
            return {'kind': 'CEPH_CLIENT_ENVIRONMENT', 'scope': 'SSH_CLIENT_HOST_ONLY'}

        with patch.object(dispatch, 'load_helper', return_value=SimpleNamespace(collect_environment=collect_environment)):
            dispatch.execute(dispatch.Plan('environment', timeout=2), POLICY, runner)
        runner.evidence.assert_called_once_with(('/usr/bin/ssh', '-V'), timeout=2, maximum=8192)

    def test_binary_hash_mismatch_blocks_loading_helper(self):
        with patch.object(dispatch, 'trusted_file', return_value=b'unapproved source'):
            with self.assertRaisesRegex(dispatch.Rejected, 'SSH_COLLECTOR_CHECKSUM_MISMATCH'):
                dispatch.load_helper(POLICY)

    def test_cancelled_runner_cannot_start_process(self):
        runner = dispatch.BoundedRunner()
        runner.cancel()
        with patch.object(dispatch.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(dispatch.Rejected, 'SSH_COLLECTION_CANCELLED'):
                runner.run(['/usr/bin/ceph', 'fsid'])
        start.assert_not_called()

    def test_root_account_is_rejected_without_reading_config_or_command(self):
        with patch.object(dispatch.os, 'geteuid', return_value=0, create=True), \
             patch.object(dispatch, 'trusted_file') as trusted, patch.object(dispatch.sys, 'stderr'):
            self.assertEqual(dispatch.main(), 126)
        trusted.assert_not_called()

    @unittest.skipUnless(os.name == 'posix', 'server runtime is Linux-only')
    def test_bounded_runner_executes_argv_without_inherited_environment_or_shell(self):
        runner = dispatch.BoundedRunner(timeout=3)
        with patch.dict(os.environ, {'CEPH_ARGS': '--name client.admin', 'PYTHONPATH': 'PRIVATE'}, clear=False):
            code, result = runner.run([sys.executable, '-I', '-c', 'import os; print(os.environ.get("CEPH_ARGS", "clean"))'], timeout=2)
        self.assertEqual((code, result.strip()), (0, b'clean'))

    @unittest.skipUnless(os.name == 'posix', 'process group termination is Linux-only')
    def test_output_overflow_and_timeout_terminate_process_group(self):
        for code, source, maximum, timeout in [
            ('SSH_SOURCE_OUTPUT_LIMIT', 'print("x" * 65536)', 128, 2),
            ('SSH_COLLECTION_TIMEOUT', 'import time; time.sleep(5)', 1024, 0.05),
        ]:
            with self.subTest(code=code), self.assertRaisesRegex(dispatch.Rejected, code):
                dispatch.BoundedRunner(timeout=3).run([sys.executable, '-I', '-c', source], maximum=maximum, timeout=timeout)

    @unittest.skipUnless(os.name == 'posix', 'server cancellation is Linux-only')
    def test_cancellation_terminates_active_process_group(self):
        runner = dispatch.BoundedRunner(timeout=3)
        results = []

        def execute():
            try:
                runner.run([sys.executable, '-I', '-c', 'import time; time.sleep(5)'], timeout=2)
            except dispatch.Rejected as exc:
                results.append(str(exc))

        task = threading.Thread(target=execute)
        task.start()
        try:
            deadline = time.monotonic() + 1
            while not runner.active and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(runner.active)
            runner.cancel()
            task.join(timeout=1)
            self.assertFalse(task.is_alive())
            self.assertEqual(results, ['SSH_COLLECTION_CANCELLED'])
        finally:
            runner.cancel()
            task.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
