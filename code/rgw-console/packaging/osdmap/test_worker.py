import base64
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from worker import compare_placements, main, mapping_diagnostics, parse_placements, run_tool, simulate, tool_identity


class RuntimePolicyTests(unittest.TestCase):
    def test_ceph_shared_library_matches_the_tested_donor(self):
        # Matching executable hashes alone is insufficient: both tools load
        # their placement/map implementation from this Pacific shared library.
        library = Path('/usr/lib64/ceph/libceph-common.so.2')
        self.assertEqual(hashlib.sha256(library.read_bytes()).hexdigest(),
                         'e6a4768ebf2e3836c7d38258840b27620bb0ea6bf1070fe90be635ce899462b9')

    def run_one_iteration(self, spool):
        original_sleep = time.sleep
        def stop_after_heartbeat(seconds):
            # subprocess.run(timeout=...) also uses time.sleep while waiting.
            # Stop only after startup has completed, not inside that wait.
            if (spool / 'capabilities.json').exists():
                raise RuntimeError('iteration complete')
            original_sleep(seconds)
        with patch.dict('os.environ', {'OSDMAP_PREVIEW_SPOOL': str(spool)}), \
                patch('worker.time.sleep', side_effect=stop_after_heartbeat):
            with self.assertRaisesRegex(RuntimeError, 'iteration complete'):
                main()

    def test_unsupported_version_never_advertises_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp)
            with patch.dict('os.environ', {'OSDMAP_PREVIEW_SPOOL': tmp}), \
                    patch('worker.run_tool', return_value='ceph version 17.2.9'), \
                    patch('worker.tool_identity') as identity:
                with self.assertRaisesRegex(ValueError, 'Only the tested Ceph'):
                    main()
            identity.assert_not_called()
            self.assertFalse((spool / 'capabilities.json').exists())

    def test_changed_binary_never_advertises_capability(self):
        import worker
        for name in worker.EXPECTED_TOOL_SHA256:
            with self.subTest(binary=name), tempfile.TemporaryDirectory() as tmp:
                identity = dict(worker.EXPECTED_TOOL_SHA256)
                identity[name] = '0' * 64
                with patch.dict('os.environ', {'OSDMAP_PREVIEW_SPOOL': tmp}), \
                        patch('worker.run_tool', return_value='ceph version 16.2.15'), \
                        patch('worker.tool_identity', return_value=identity):
                    with self.assertRaisesRegex(ValueError, 'amd64 tool binaries'):
                        main()
                self.assertFalse((Path(tmp) / 'capabilities.json').exists())

    def test_expired_job_does_not_run_tool_simulation(self):
        from uuid import uuid4
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp)
            job = spool / str(uuid4())
            job.mkdir()
            (job / 'request.json').write_text(json.dumps({'queued_at': time.time() - 360}))
            with patch('worker.simulate') as simulate_job:
                self.run_one_iteration(spool)
            simulate_job.assert_not_called()
            self.assertEqual(json.loads((job / 'result.json').read_text()),
                             {'ok': False, 'code': 'OSDMAP_REQUEST_EXPIRED'})

    def test_symlink_job_cannot_escape_spool(self):
        from uuid import uuid4
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            target = Path(outside)
            (target / 'request.json').write_text(json.dumps({'queued_at': time.time()}))
            (Path(tmp) / str(uuid4())).symlink_to(target, target_is_directory=True)
            with patch('worker.simulate') as simulate_job:
                self.run_one_iteration(Path(tmp))
            simulate_job.assert_not_called()
            self.assertFalse((target / 'result.json').exists())

    def test_symlink_request_and_non_uuid_job_are_ignored(self):
        from uuid import uuid4
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp)
            original = spool / 'external-request.json'
            original.write_text(json.dumps({'queued_at': time.time()}))
            linked = spool / str(uuid4())
            linked.mkdir()
            (linked / 'request.json').symlink_to(original)
            untrusted = spool / 'not-a-job-id'
            untrusted.mkdir()
            (untrusted / 'request.json').write_text(original.read_text())
            with patch('worker.simulate') as simulate_job:
                self.run_one_iteration(spool)
            simulate_job.assert_not_called()
            self.assertFalse((linked / 'result.json').exists())
            self.assertFalse((untrusted / 'result.json').exists())


class PlacementTests(unittest.TestCase):
    def test_real_worker_startup_reports_tested_tools_and_replicated_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_sleep = time.sleep
            def after_heartbeat(seconds):
                if (Path(tmp) / 'capabilities.json').exists():
                    raise RuntimeError('stop')
                original_sleep(seconds)
            with patch.dict('os.environ', {'OSDMAP_PREVIEW_SPOOL': tmp}), patch('worker.time.sleep', side_effect=after_heartbeat):
                with self.assertRaisesRegex(RuntimeError, 'stop'):
                    main()
            capabilities = json.loads((Path(tmp) / 'capabilities.json').read_text())
            self.assertTrue(capabilities['available'])
            self.assertEqual(capabilities['pool_types'], ['replicated'])
            self.assertEqual(capabilities['parser_version'], 2)
            self.assertEqual(capabilities['tool_binary_sha256'], tool_identity())

    def test_preserves_raw_up_acting_and_order(self):
        left = parse_placements("1.0 raw ([0,1], p0) up ([1,0], p1) acting ([0,1], p0)", 1)
        right = parse_placements("1.0 raw ([1,0], p1) up ([1,0], p1) acting ([0,1], p0)", 1)
        result = compare_placements(left, right, [0, 1, 5])
        self.assertEqual(result["summary"]["changed_pgs"], 1)
        self.assertTrue(result["pg_changes"][0]["order_changed"])
        self.assertFalse(result["pg_changes"][0]["membership_changed"])
        self.assertEqual(result["osd_distribution"][-1]["after_pg"], 0)
        self.assertEqual(result["osd_distribution"][0]["delta_primary"], 0)

    def test_missing_or_duplicate_rows_rejected(self):
        line = "1.0 raw ([0,1], p0) up ([0,1], p0) acting ([0,1], p0)"
        for text, count in [(line, 2), (line + "\n" + line, 2), (line.replace("raw", "broken"), 1)]:
            with self.assertRaises(ValueError):
                parse_placements(text, count)

    def test_invalid_member_and_primary_rejected(self):
        for members, primary in [('0,0', 0), ('0,-2', 0), ('0,1', 3)]:
            line = '1.0 raw ([{}], p{}) up ([0,1], p0) acting ([0,1], p0)'.format(members, primary)
            with self.assertRaisesRegex(ValueError, 'OSDMAP_PLACEMENT_'):
                parse_placements(line, 1)
        with self.assertRaisesRegex(ValueError, 'PARSE_FAILED'):
            parse_placements('  1.0 broken ([0,1], p0)', 1)

    def test_undersized_mapping_warns_unknown_osd_rejects(self):
        rows = parse_placements('1.0 raw ([0], p0) up ([0], p0) acting ([0], p0)', 1)
        warnings = mapping_diagnostics(rows, [{'pool': 1, 'size': 3}], [0, 1])
        self.assertEqual(len(warnings), 3)
        self.assertEqual(warnings[0]['expected_members'], 3)
        with self.assertRaisesRegex(ValueError, 'OSD_UNKNOWN'):
            mapping_diagnostics(rows, [{'pool': 1, 'size': 3}], [1])

    def test_ec_pool_and_unknown_types_fail_closed_before_mapping(self):
        for pool_type in (2, 3, None):
            with tempfile.TemporaryDirectory() as tmp:
                raw = b'opaque map'
                request = {'map': base64.b64encode(raw).decode(), 'base_sha256': hashlib.sha256(raw).hexdigest(), 'fsid': 'fixture'}
                decoded = {'fsid': 'fixture', 'pools': [{'pool': 1, 'type': pool_type, 'pg_num': 1, 'size': 3}]}
                with patch('worker.run_tool', return_value=json.dumps(decoded)) as tool:
                    with self.assertRaisesRegex(ValueError, 'POOL_TYPE_UNSUPPORTED'):
                        simulate(request, Path(tmp), '16.2.15')
                    self.assertEqual(tool.call_count, 1)

    def test_binary_pool_scope_rechecks_allowlist_after_api_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = b'opaque map'
            request = {'map': base64.b64encode(raw).decode(), 'base_sha256': hashlib.sha256(raw).hexdigest(),
                       'fsid': 'fixture', 'allowed_pool_ids': [1]}
            decoded = {'fsid': 'fixture', 'pools': [{'pool': 2, 'type': 1, 'pg_num': 1, 'size': 3}]}
            with patch('worker.run_tool', return_value=json.dumps(decoded)) as tool:
                with self.assertRaisesRegex(ValueError, 'POOL_SCOPE_REJECTED'):
                    simulate(request, Path(tmp), '16.2.15')
                self.assertEqual(tool.call_count, 1)

    def test_real_tool_keeps_upmap_items_on_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'fixture.osdmap'
            run_tool([str(source), '--createsimple', '6', '--with-default-pool', '--mark-up-in',
                      '--osd-crush-chooseleaf-type', '0'], root)
            # This is a generated isolated test map. --save never appears in the
            # worker's simulate() argv and these commands are never sent to Ceph.
            run_tool([str(source), '--adjust-crush-weight', '0:0.5', '--upmap', str(root / 'upmap-commands'),
                      '--upmap-max', '10', '--save'], root)
            decoded = json.loads(run_tool([str(source), '--dump', 'json'], root))
            self.assertTrue(decoded['pg_upmap_items'])
            before_text = run_tool([str(source), '--test-map-pgs-dump-all'], root)
            before = parse_placements(before_text, decoded['pools'][0]['pg_num'])
            self.assertTrue(any(row['raw'] != row['up'] for row in before.values()))
            raw = source.read_bytes()
            request = {'map': base64.b64encode(raw).decode(), 'base_sha256': hashlib.sha256(raw).hexdigest(),
                       'fsid': decoded['fsid'], 'changes': [{'osd_id': 0, 'crush_weight': 0.5}]}
            scratch = root / 'simulation'
            scratch.mkdir()
            result = simulate(request, scratch, '16.2.15')
            self.assertEqual(result['summary']['changed_pgs'], 0)
            self.assertEqual(result['mapping_validation']['quality'], 'VALID')
            after_decoded = json.loads(run_tool([str(scratch / 'base.osdmap'), '--dump', 'json'], root))
            self.assertEqual(after_decoded['pg_upmap_items'], decoded['pg_upmap_items'])
            self.assertEqual(result['placement_sha256']['before'], result['placement_sha256']['after'])

    def test_real_tool_no_op_and_multiple_weight_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "fixture.osdmap"
            run_tool([str(source), "--createsimple", "6", "--with-default-pool", "--mark-up-in"], root)
            raw = source.read_bytes()
            decoded = json.loads(run_tool([str(source), "--dump", "json"], root))
            request = {"map": base64.b64encode(raw).decode(), "base_sha256": hashlib.sha256(raw).hexdigest(),
                       "fsid": decoded["fsid"], "pool_id": None,
                       "changes": [{"osd_id": 0, "crush_weight": 1.0}, {"osd_id": 1, "crush_weight": 1.0}]}
            no_op = root / "no-op"
            no_op.mkdir()
            baseline = simulate(request, no_op, "16.2.15")
            self.assertEqual(baseline["summary"]["changed_pgs"], 0)
            self.assertEqual(baseline['scope']['pool_types'], ['replicated'])
            self.assertEqual(baseline['mapping_validation']['quality'], 'PARTIAL')
            self.assertTrue(baseline['mapping_validation']['before_warnings'])
            self.assertEqual(baseline['tool_binary_sha256'], tool_identity())
            self.assertEqual(baseline['parser_version'], 2)
            self.assertEqual(set(baseline['osd_distribution_by_set']), {'raw', 'up', 'acting'})
            changed = root / "changed"
            changed.mkdir()
            request["changes"] = [{"osd_id": 0, "crush_weight": 0}, {"osd_id": 1, "crush_weight": 0}]
            result = simulate(request, changed, "16.2.15")
            self.assertGreater(result["summary"]["changed_pgs"], 0)
            self.assertEqual(result["osd_distribution"][0]["after_pg"], 0)
            self.assertEqual(result["osd_distribution"][1]["after_pg"], 0)
            self.assertEqual(result["scope"]["pg_count"], baseline["scope"]["pg_count"])
            self.assertEqual(hashlib.sha256((changed / "base.osdmap").read_bytes()).hexdigest(), request["base_sha256"])

    def test_pg_ids_cannot_escape_the_scoped_pool_even_at_expected_count(self):
        import worker
        real_parse = worker.parse_placements
        def wrong_pool(text, expected):
            return {'999.' + key.split('.')[1]: value for key, value in real_parse(text, expected).items()}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'fixture.osdmap'
            run_tool([str(source), '--createsimple', '3', '--with-default-pool', '--mark-up-in'], root)
            raw = source.read_bytes()
            decoded = json.loads(run_tool([str(source), '--dump', 'json'], root))
            request = {'map': base64.b64encode(raw).decode(), 'base_sha256': hashlib.sha256(raw).hexdigest(),
                       'fsid': decoded['fsid'], 'changes': [{'osd_id': 0, 'crush_weight': 1}]}
            simulation = root / 'simulation'
            simulation.mkdir()
            with patch('worker.parse_placements', side_effect=wrong_pool):
                with self.assertRaisesRegex(ValueError, 'PG_SCOPE_INVALID'):
                    simulate(request, simulation, '16.2.15')

    def test_wrong_fsid_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "fixture.osdmap"
            run_tool([str(source), "--createsimple", "3", "--with-default-pool", "--mark-up-in"], root)
            raw = source.read_bytes()
            with self.assertRaisesRegex(ValueError, "FSID"):
                simulate({"map": base64.b64encode(raw).decode(), "base_sha256": hashlib.sha256(raw).hexdigest(), "fsid": "wrong"}, root, "16.2.15")


if __name__ == "__main__":
    unittest.main()
