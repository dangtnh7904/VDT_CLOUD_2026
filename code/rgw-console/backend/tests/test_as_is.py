from __future__ import annotations

import copy
import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.modules.as_is.api import router
from app.modules.as_is.comparison import compare_collections, ComparisonError
from app.modules.as_is.service import AsIsService, AsIsError, digest
from app.modules.cluster_metrics.service import ACTIONS
from app.services.executor_client import ExecutorClientError


FSID = '11111111-2222-3333-4444-555555555555'


class MemoryRepository:
    def __init__(self):
        self.rows = {}
        self.events = []
        self.filters = None

    def get(self, collection_id, *, include_deleted=False, **identity):
        row = self.rows.get(str(collection_id))
        if not row or any(str(row.get(k)) != str(v) for k, v in identity.items()) or row.get('deleted_at') and not include_deleted:
            return None
        return copy.deepcopy(row)

    def save(self, payload, *, sha256, request_hash, actor):
        self.rows.setdefault(payload['id'], {**copy.deepcopy(payload), 'payload': copy.deepcopy(payload),
            'sha256': sha256, 'request_hash': request_hash, 'deleted_at': None})
        self.events.append('CREATED')

    def list(self, **kwargs):
        self.filters = kwargs
        return []

    def set_deleted(self, collection_id, *, deleted, actor, **identity):
        row = self.rows[str(collection_id)]
        row['deleted_at'] = datetime.now(timezone.utc).isoformat() if deleted else None
        self.events.append('DELETED' if deleted else 'RESTORED')
        return copy.deepcopy(row)


class Client:
    def __init__(self):
        self.calls = []
        self.fsid = FSID
        self.fail = set()
        self.version = 1
        self.identity_calls = 0

    def capabilities(self):
        return {'fsid': self.fsid, 'actions': list({a for group in ACTIONS.values() for a in group})}

    def ceph_fsid(self):
        self.identity_calls += 1
        return {'fsid': self.fsid}

    def request(self, action, **kwargs):
        self.calls.append(action)
        if action in self.fail:
            raise ExecutorClientError('COMMAND_FAILED', 'SECRET-PRIVATE-ERROR')
        data = {
            'ceph.status': {'health': {'status': 'HEALTH_OK'}, 'pgmap': {'num_pgs': 3}},
            'ceph.health_detail': {'status': 'HEALTH_OK', 'checks': {}},
            'ceph.mon_dump': {'epoch': self.version, 'mons': [{'name': 'one', 'rank': 0}]},
            'ceph.quorum_status': {'quorum': [0], 'election_epoch': 8},
            'ceph.mgr_dump': {'active_name': 'one', 'available': True, 'active_gid': 24},
            'ceph.mgr_modules': {'enabled_modules': ['prometheus']},
            'ceph.osd_df': {'nodes': [{'id': 0, 'kb_used': self.version, 'kb': 100, 'kb_avail': 99, 'pgs': 3}, {'id': 5}]},
            'ceph.osd_tree': {'nodes': [{'id': 0, 'status': 'up'}]},
            'ceph.host_ls': [{'hostname': 'host-a'}, {'hostname': 'outside-host'}],
            'ceph.pool_ls_detail': [{'pool_id': 1, 'pool_name': 'allowed'}, {'pool_id': 2, 'pool_name': 'outside-pool'}],
            'ceph.df': {'stats': {'total_bytes': 100}, 'pools': []},
        }.get(action, {})
        return {'fsid': self.fsid, 'data': data, 'collected_at': datetime.now(timezone.utc).isoformat()}


class AsIsTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
            cluster_id='lab', ceph_expected_fsid=FSID, upgrade_allowed_osds='0',
            upgrade_allowed_hosts='host-a', upgrade_allowed_pools='allowed')
        self.repo, self.client = MemoryRepository(), Client()
        self.service = AsIsService(self.settings, self.repo, self.client)

    def collect(self, key='first-request', phase='BEFORE', keys=None):
        return self.service.create(daemon_keys=keys or ['mon.one', 'mgr.one', 'osd.0'], phase=phase,
                                   idempotency_key=key)

    def test_observe_reexecutes_sources_and_never_uses_saved_snapshot(self):
        first = self.service.observe()
        count = len(self.client.calls)
        self.client.version = 2
        second = self.service.observe()
        self.assertEqual(len(self.client.calls), count * 2)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(next(r for r in second['daemons'] if r['key'] == 'osd.0')['fields']['used_kb'], 2)
        self.assertEqual(self.repo.rows, {})
        self.assertNotIn('outside-pool', str(second))
        self.assertNotIn('outside-host', str(second))
        self.assertEqual({r['key'] for r in second['daemons']}, {'mon.one', 'mgr.one', 'osd.0'})

    def test_partial_source_does_not_return_fake_quorum_or_leak_exception(self):
        self.client.fail.add('ceph.quorum_status')
        result = self.service.observe(daemon_keys=['mon.one'])
        self.assertEqual(result['quality'], 'PARTIAL')
        self.assertIsNone(result['daemons'][0]['fields']['in_quorum'])
        self.assertNotIn('SECRET-PRIVATE-ERROR', str(result))

    def test_scope_and_fsid_rejected_before_data_reads(self):
        with self.assertRaises(AsIsError):
            self.service.observe(daemon_keys=['osd.5'])
        self.client.fsid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        with self.assertRaises(AsIsError):
            self.service.observe()
        self.assertEqual(self.client.calls, [])

    def test_collection_idempotency_integrity_and_softdelete_restore(self):
        first = self.collect()
        count = len(self.client.calls)
        again = self.collect()
        self.assertEqual(first, again)
        self.assertEqual(len(self.client.calls), count)
        with self.assertRaises(AsIsError):
            self.collect(phase='DURING')
        self.service.set_deleted(first['id'], deleted=True, actor='test')
        with self.assertRaises(AsIsError):
            self.service.get(first['id'])
        self.service.set_deleted(first['id'], deleted=False, actor='test')
        self.assertEqual(first, self.service.get(first['id']))
        self.assertEqual(len(self.client.calls), count)
        self.repo.rows[first['id']]['payload']['note'] = 'tampered'
        with self.assertRaisesRegex(AsIsError, 'toàn vẹn'):
            self.service.get(first['id'])

    def test_historical_export_has_verified_download_hash_and_no_recollection(self):
        app = FastAPI()
        app.include_router(router)
        saved = self.collect()
        count = len(self.client.calls)
        with patch('app.modules.as_is.api._service', return_value=self.service), TestClient(app) as http:
            response = http.get(f"/api/v1/as-is/collections/{saved['id']}/export")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['x-export-sha256'], hashlib.sha256(response.content).hexdigest())
            self.assertEqual(len(self.client.calls), count)
            response = http.post('/api/v1/as-is/export', json={'daemon_keys': ['mon.one']})
            self.assertEqual(response.status_code, 200)
            self.assertGreater(len(self.client.calls), count)
            self.assertEqual(response.headers['x-export-sha256'], hashlib.sha256(response.content).hexdigest())

    def test_filters_include_whole_local_day_and_validate_order(self):
        self.service.list(from_date='2026-10-12', to_date='2026-10-12', daemon_type='osd')
        self.assertEqual(self.repo.filters['start'].astimezone(timezone.utc).isoformat(), '2026-10-11T17:00:00+00:00')
        self.assertEqual(self.repo.filters['end'].astimezone(timezone.utc).isoformat(), '2026-10-12T17:00:00+00:00')
        with self.assertRaises(AsIsError):
            self.service.list(from_date='2026-10-13', to_date='2026-10-12')

    def test_missing_requested_daemon_retains_coverage(self):
        result = self.service.observe(daemon_keys=['mon.missing'])
        self.assertEqual(result['missing_daemon_keys'], ['mon.missing'])
        self.assertEqual(result['quality'], 'PARTIAL')

    def test_comparison_any_phase_same_type_and_union_coverage(self):
        one = self.collect(phase='AFTER', keys=['mon.one', 'mgr.one'])
        self.client.version = 9
        two = self.collect(key='second-request', phase='AFTER', keys=['mon.one'])
        result = self.service.compare(collection_a_id=one['id'], collection_b_id=two['id'], daemon_type='mon')
        self.assertEqual(result['summary']['changed'], 1)
        extra = copy.deepcopy(one['daemons'][0])
        extra.update(key='mon.two', type='mon')
        one['daemons'].append(extra)
        union = compare_collections(one, two, 'mon')
        self.assertEqual(union['summary']['only_a'], 1)
        two['fsid'] = 'different'
        with self.assertRaises(ComparisonError):
            compare_collections(one, two, 'mon')

    def test_comparison_incarnation_change_blocks_numeric_delta(self):
        one = self.collect(keys=['mgr.one'])
        two = copy.deepcopy(one)
        two['daemons'][0]['fields'].update(gid=999, count=12)
        one['daemons'][0]['fields']['count'] = 5
        result = compare_collections(one, two, 'mgr')
        count = next(c for c in result['rows'][0]['changes'] if c['field'] == 'count')
        self.assertIsNone(count['delta'])
        self.assertEqual(count['reason'], 'INCARNATION_CHANGED')

    def test_new_collection_has_no_session_requirement(self):
        app = FastAPI()
        app.include_router(router)
        with patch('app.modules.as_is.api._service', return_value=self.service), TestClient(app) as http:
            response = http.post('/api/v1/as-is/collections', json={'daemon_keys': ['mon.one'], 'phase': 'DURING'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['phase'], 'DURING')
        self.assertNotIn('session_id', response.json())


if __name__ == '__main__':
    unittest.main()
