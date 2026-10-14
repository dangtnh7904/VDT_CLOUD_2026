import base64
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from uuid import UUID

from pydantic import ValidationError

from app.config import Settings
from app.modules.osdmap_preview.api import PreviewRequest
from app.modules.osdmap_preview.service import EXPECTED_TOOL_SHA256, SUPPORTED_TOOL_VERSIONS, PreviewService, PreviewError
from app.platform.security.middleware import permitted_read_only_request

FSID = '17c77e12-a16a-11f1-838e-cf68e9c001d8'


def capability(**changes):
    result = {'available': True, 'tool_version': '16.2.15', 'operations': ['crush_weight'],
              'pool_types': ['replicated'], 'parser_version': 2,
              'tool_binary_sha256': dict(EXPECTED_TOOL_SHA256), 'heartbeat': time.time()}
    result.update(changes)
    return result


def worker_result(**changes):
    result = {'base_epoch': 42, 'tool_version': '16.2.15', 'parser_version': 2,
              'tool_binary_sha256': dict(EXPECTED_TOOL_SHA256),
              'scope': {'pool_id': 13, 'pool_ids': [13], 'pool_types': ['replicated'], 'pg_count': 1},
              'summary': {'changed_pgs': 0, 'membership_changes': 0, 'primary_changes': 0, 'order_changes': 0},
              'mapping_validation': {'quality': 'VALID', 'before_warnings': [], 'after_warnings': [],
                                     'failure_domain_checked': False},
              'pg_changes': [], 'osd_distribution': []}
    result.update(changes)
    return result


class Client:
    def __init__(self):
        self.calls = []
        self.epoch = 42
        self.weight_set_sync = True
        self.mon_version = 'ceph version 16.2.15 (commit) pacific'

    def request(self, action, **kwargs):
        self.calls.append(action)
        if action == 'ceph.osdmap_preview_context':
            return {'fsid': FSID, 'data': {'mons': [{'name': 'one', 'osd_crush_update_weight_set': self.weight_set_sync}],
                'mon_versions': {self.mon_version: 1}}}
        raw = b'\x00\xff\xfe\x80binary map'
        data = {'epoch': self.epoch, 'pools': [{'pool': 13, 'pool_name': 'test'}]} if action == 'ceph.osd_dump' else {
            'map': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest()}
        return {'fsid': FSID, 'data': data}


class Repository:
    def __init__(self):
        self.rows = {}

    def save(self, payload, artifact, actor):
        self.rows[payload['id']] = {'uri': artifact.uri, 'sha256': artifact.sha256, 'size_bytes': artifact.size_bytes}

    def get(self, preview_id, cluster_id, fsid):
        return self.rows.get(str(preview_id))


class PreviewTests(unittest.TestCase):
    def test_capability_requires_complete_pinned_identity_not_only_version_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp)
            settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
                cluster_id='lab', ceph_expected_fsid=FSID, osdmap_preview_spool=spool)
            service = PreviewService(settings)
            for key in ('available', 'tool_version', 'operations', 'pool_types', 'parser_version',
                        'tool_binary_sha256', 'heartbeat'):
                data = capability()
                del data[key]
                (spool / 'capabilities.json').write_text(json.dumps(data))
                with self.subTest(missing=key):
                    self.assertEqual(service.capabilities()['code'], 'OSDMAP_CAPABILITIES_INVALID')
            for version in SUPPORTED_TOOL_VERSIONS:
                (spool / 'capabilities.json').write_text(json.dumps(capability(tool_version=version)))
                self.assertTrue(service.capabilities()['available'])
            version = 'ceph version 16.2.15 (' + '0' * 40 + ') pacific (stable)'
            (spool / 'capabilities.json').write_text(json.dumps(capability(tool_version=version)))
            self.assertEqual(service.capabilities()['code'], 'OSDMAP_CAPABILITIES_INVALID')
            for when in (time.time() - 121, time.time() + 5):
                (spool / 'capabilities.json').write_text(json.dumps(capability(heartbeat=when)))
                self.assertEqual(service.capabilities()['code'], 'OSDMAP_CAPABILITIES_STALE')

    def test_result_must_match_complete_handshake_and_requested_replicated_scope(self):
        valid = worker_result()
        PreviewService._validate_result_identity(valid, capability(), 13)
        for key in ('tool_version', 'parser_version', 'tool_binary_sha256'):
            data = worker_result()
            del data[key]
            with self.subTest(missing=key), self.assertRaises(PreviewError) as error:
                PreviewService._validate_result_identity(data, capability(), 13)
            self.assertEqual(error.exception.code, 'OSDMAP_RESULT_IDENTITY_MISMATCH')
        for patch in ({'tool_version': []}, {'tool_version': {}}, {'parser_version': True},
                      {'tool_binary_sha256': {key: '0' * 64 for key in EXPECTED_TOOL_SHA256}},
                      {'tool_version': next(version for version in SUPPORTED_TOOL_VERSIONS if version != '16.2.15')}):
            with self.subTest(patch=patch), self.assertRaises(PreviewError) as error:
                PreviewService._validate_result_identity(worker_result(**patch), capability(), 13)
            self.assertEqual(error.exception.code, 'OSDMAP_RESULT_IDENTITY_MISMATCH')
        for scope, pool in (({'pool_id': 13}, 13), ({'pool_id': 13, 'pool_types': ['erasure']}, 13),
                            ({'pool_id': True, 'pool_types': ['replicated']}, 1),
                            ({'pool_types': ['replicated']}, None),
                            ({'pool_id': 14, 'pool_types': ['replicated']}, 13)):
            with self.subTest(scope=scope), self.assertRaises(PreviewError) as error:
                PreviewService._validate_result_identity(worker_result(scope=scope), capability(), pool)
            self.assertEqual(error.exception.code, 'OSDMAP_RESULT_SCOPE_MISMATCH')
        for data in (None, [], 'not an object'):
            with self.assertRaises(PreviewError) as error:
                PreviewService._validate_result_identity(data, capability(), 13)
            self.assertEqual(error.exception.code, 'OSDMAP_RESULT_IDENTITY_MISMATCH')

    def test_worker_envelope_rejects_truthy_success_flags_and_malformed_error_codes(self):
        for data in ([], None, {'ok': 'true', 'result': worker_result()}, {'ok': 1},
                     {'ok': False}, {'ok': False, 'code': []},
                     {'ok': False, 'code': 'OSDMAP_TOOL_FAILED\nsecret'}):
            with self.subTest(data=data), self.assertRaises(PreviewError) as error:
                PreviewService._worker_result(data)
            self.assertEqual(error.exception.code, 'OSDMAP_WORKER_RESULT_INVALID')
        with self.assertRaises(PreviewError) as error:
            PreviewService._worker_result({'ok': False, 'code': 'OSDMAP_POOL_TYPE_UNSUPPORTED'})
        self.assertEqual(error.exception.code, 'OSDMAP_POOL_TYPE_UNSUPPORTED')
        self.assertEqual(PreviewService._worker_result({'ok': True, 'result': worker_result()}), worker_result())

    def test_unpinned_worker_response_is_rejected_before_any_artifact_or_database_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spool = root / 'spool'
            spool.mkdir()
            (spool / 'capabilities.json').write_text(json.dumps(capability()))
            settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
                cluster_id='lab', ceph_expected_fsid=FSID, upgrade_allowed_osds='0',
                upgrade_allowed_pools='test', evidence_root=root / 'evidence', osdmap_preview_spool=spool)
            repository = Repository()
            service = PreviewService(settings, client=Client(), repository=repository)

            def worker():
                deadline = time.time() + 5
                while time.time() < deadline:
                    jobs = list(spool.glob('*/request.json'))
                    if jobs:
                        wrong = worker_result(tool_binary_sha256={key: '0' * 64 for key in EXPECTED_TOOL_SHA256})
                        (jobs[0].parent / 'result.json').write_text(json.dumps({'ok': True, 'result': wrong}))
                        return
                    time.sleep(0.01)
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                with self.assertRaises(PreviewError) as error:
                    service.create([{'osd_id': 0, 'crush_weight': 1}], pool_id=13)
                self.assertEqual(error.exception.code, 'OSDMAP_RESULT_IDENTITY_MISMATCH')
            finally:
                thread.join()
            self.assertEqual(repository.rows, {})
            self.assertFalse((root / 'evidence').exists())
            self.assertEqual(list(spool.glob('*/request.json')), [])

    def test_stale_unsupported_or_malformed_capabilities_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp)
            settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
                cluster_id='lab', ceph_expected_fsid=FSID, osdmap_preview_spool=spool)
            for update in ({'heartbeat': time.time() - 121}, {'tool_version': '17.2.7'},
                           {'operations': ['crush_weight', 'apply']}, {'available': 'true'},
                           {'pool_types': ['erasure']}, {'parser_version': 99},
                           {'tool_binary_sha256': {'osdmaptool_sha256': 'bad'}},
                           {'tool_binary_sha256': {key: '0' * 64 for key in EXPECTED_TOOL_SHA256}},
                           {'tool_version': []}, {'heartbeat': float('nan')}, {'heartbeat': float('inf')},
                           {'heartbeat': 10 ** 1000}):
                data = capability(**update)
                (spool / 'capabilities.json').write_text(json.dumps(data))
                self.assertFalse(PreviewService(settings).capabilities()['available'])

    def test_all_pool_scope_cannot_bypass_pool_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp)
            (spool / 'capabilities.json').write_text(json.dumps(capability()))
            settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
                cluster_id='lab', ceph_expected_fsid=FSID, upgrade_allowed_osds='0',
                upgrade_allowed_pools='another-pool', osdmap_preview_spool=spool)
            client = Client()
            with self.assertRaisesRegex(PreviewError, 'pool ngoài'):
                PreviewService(settings, client=client).create([{'osd_id': 0, 'crush_weight': 0}])
            self.assertNotIn('ceph.osd_map_export', client.calls)

    def test_preview_context_from_another_fsid_is_rejected(self):
        class ForeignClient(Client):
            def request(self, action, **kwargs):
                result = super().request(action, **kwargs)
                if action == 'ceph.osdmap_preview_context':
                    result['fsid'] = 'another-cluster'
                return result
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp)
            (spool / 'capabilities.json').write_text(json.dumps(capability()))
            settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
                cluster_id='lab', ceph_expected_fsid=FSID, upgrade_allowed_osds='0', osdmap_preview_spool=spool)
            client = ForeignClient()
            with self.assertRaises(PreviewError) as error:
                PreviewService(settings, client=client).create([{'osd_id': 0, 'crush_weight': 0}])
            self.assertEqual(error.exception.code, 'FSID_MISMATCH')
            self.assertNotIn('ceph.osd_map_export', client.calls)

    def test_unsupported_live_modes_are_rejected_before_exporting_a_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp)
            (spool / 'capabilities.json').write_text(json.dumps(capability()))
            settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
                cluster_id='lab', ceph_expected_fsid=FSID, upgrade_allowed_osds='0', osdmap_preview_spool=spool)
            for mode, version in [(False, 'ceph version 16.2.15 (commit)'), (True, 'ceph version 17.2.7 (commit)')]:
                client = Client()
                client.weight_set_sync, client.mon_version = mode, version
                with self.assertRaises(PreviewError):
                    PreviewService(settings, client=client).create([{'osd_id': 0, 'crush_weight': 0}])
                self.assertNotIn('ceph.osd_map_export', client.calls)

    def test_fixed_model_rejects_commands_duplicates_nonfinite_and_bool_id(self):
        for value in [{'changes': [{'osd_id': 0, 'crush_weight': float('nan')}]},
                      {'changes': [{'osd_id': True, 'crush_weight': 1}]},
                      {'changes': [{'osd_id': 0, 'crush_weight': 40000}]},
                      {'changes': [{'osd_id': 0, 'crush_weight': 1}], 'command': 'ceph osd out 0'},
                      {'changes': [{'osd_id': 0, 'crush_weight': 1}] * 2}]:
            with self.assertRaises(ValidationError):
                PreviewRequest(**value)

    def test_readonly_policy_names_only_new_collection_and_offline_preview_writes(self):
        identifier = '11111111-2222-3333-4444-555555555555'
        self.assertTrue(permitted_read_only_request('POST', '/api/v1/osdmap-previews'))
        self.assertTrue(permitted_read_only_request('DELETE', '/api/v1/as-is/collections/' + identifier))
        self.assertFalse(permitted_read_only_request('DELETE', '/api/v1/osdmap-previews/' + identifier))
        self.assertFalse(permitted_read_only_request('POST', '/api/v1/osdmap-previews/' + identifier + '/apply'))
        self.assertFalse(permitted_read_only_request('POST', '/api/v1/qos-runs'))

    def test_preview_fresh_read_immutable_export_scope_and_epoch_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spool = root / 'spool'
            spool.mkdir()
            (spool / 'capabilities.json').write_text(json.dumps(capability()))
            settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
                cluster_id='lab', ceph_expected_fsid=FSID, upgrade_allowed_osds='0,1',
                upgrade_allowed_pools='test', evidence_root=root / 'evidence', osdmap_preview_spool=spool)
            client, repository = Client(), Repository()
            service = PreviewService(settings, client=client, repository=repository)
            with self.assertRaises(PreviewError):
                service.create([{'osd_id': 5, 'crush_weight': 0}])
            self.assertEqual(client.calls, [])
            def worker():
                deadline = time.time() + 5
                while time.time() < deadline:
                    jobs = list(spool.glob('*/request.json'))
                    if jobs:
                        output = {'ok': True, 'result': worker_result()}
                        (jobs[0].parent / 'result.json').write_text(json.dumps(output))
                        return
                    time.sleep(0.01)
            thread = threading.Thread(target=worker)
            thread.start()
            result = service.create([{'osd_id': 0, 'crush_weight': 1}], pool_id=13)
            thread.join()
            self.assertFalse(result['stale'])
            self.assertEqual(result['worker_capabilities']['tool_binary_sha256'], EXPECTED_TOOL_SHA256)
            self.assertEqual(set(client.calls), {'ceph.osd_dump', 'ceph.osd_map_export', 'ceph.osdmap_preview_context'})
            self.assertNotIn('base_map_base64', result)
            before = list(client.calls)
            saved = service.get(UUID(result['id']), refresh=False)
            self.assertEqual(client.calls, before)
            client.epoch = 43
            self.assertTrue(service.get(UUID(result['id']))['stale'])
            self.assertEqual(saved['base_epoch'], 42)
            self.assertEqual(list(spool.glob('*/request.json')), [])


if __name__ == '__main__':
    unittest.main()
