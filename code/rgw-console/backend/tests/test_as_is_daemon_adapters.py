from __future__ import annotations

import copy
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.modules.as_is.api import router
from app.modules.cluster_metrics.normalization import normalize, daemon_source_valid
import test_as_is as fixtures


FSMAP = {'epoch': 4, 'filesystems': [{'id': 3, 'mdsmap': {'fs_name': 'labfs', 'info': {
    'gid_41': {'name': 'labfs.node-a.abc', 'gid': 41, 'rank': 0, 'state': 'up:active'}}}}],
    'standbys': [{'name': 'labfs.node-b.def', 'gid': 42, 'rank': -1, 'state': 'up:standby'}]}


class DaemonClient(fixtures.Client):
    def capabilities(self):
        result = super().capabilities()
        result['actions'] += ['ceph.client_environment']
        return result

    def request(self, action, **kwargs):
        response = super().request(action, **kwargs)
        if action == 'ceph.daemon_ls':
            response['data'] = [{'daemon_name': 'rgw.lab.node-a.abc', 'hostname': 'host-a',
                'version': '16.2.5', 'status_desc': 'running', 'container_id': 'abcdef',
                'last_refresh': '2026-01-01T00:00:00Z', 'cpu_percentage': '0.2%', 'memory_usage': 8192},
                {'daemon_name': 'mds.labfs.node-a.abc', 'hostname': 'host-a', 'version': '16.2.15'}]
        elif action == 'ceph.fs_dump':
            response['data'] = copy.deepcopy(FSMAP)
        elif action == 'ceph.client_environment':
            response['data'] = {'kind': 'CEPH_CLIENT_ENVIRONMENT', 'scope': 'SSH_CLIENT_HOST_ONLY',
                'quality': 'PARTIAL', 'host': {'hostname': 'ssh-host'}, 'shell': {'configured_path': '/bin/bash'}}
        return response


class DaemonAdapterTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AsIsTests()
        fixture.setUp()
        self.service = fixture.service
        self.client = DaemonClient()
        self.service.client = self.client

    def test_rgw_supported_without_invented_traffic_and_with_cache_timestamp(self):
        result = self.service.observe(daemon_types=['rgw'])
        self.assertEqual(len(result['daemons']), 1)
        row = result['daemons'][0]
        self.assertEqual(row['key'], 'rgw.lab.node-a.abc')
        self.assertEqual(row['observed_at'], '2026-01-01T00:00:00Z')
        self.assertEqual(row['fields']['ceph_version'], '16.2.5')
        self.assertEqual(row['quality'], 'PARTIAL')
        self.assertTrue(all(metric['quality'] == 'STALE' for metric in row['metrics']))
        self.assertFalse(any('latency' in metric['metric_id'] for metric in row['metrics']))

    def test_mds_active_and_standby_union_and_fs_identity(self):
        result = self.service.observe(daemon_types=['mds'])
        by_key = {row['key']: row for row in result['daemons']}
        active = by_key['mds.labfs.node-a.abc']['fields']
        self.assertEqual(active['filesystem'], 'labfs')
        self.assertEqual(active['rank'], 0)
        self.assertEqual(active['state'], 'up:active')
        self.assertIn('mds.labfs.node-b.def', by_key)
        self.assertEqual(result['system']['cephfs']['epoch'], 4)
        self.assertEqual(len(by_key), 2)

    def test_future_cached_metrics_and_negative_gauges_are_not_fresh_valid(self):
        original = self.client.request
        def future(action, **kwargs):
            response = original(action, **kwargs)
            if action == 'ceph.daemon_ls':
                response['data'][0].update(last_refresh='2099-01-01T00:00:00Z', memory_usage=-1)
            return response
        self.client.request = future
        row = self.service.observe(daemon_types=['rgw'])['daemons'][0]
        self.assertTrue(all(m['quality'] == 'UNAVAILABLE' for m in row['metrics']))
        self.assertIsNone(next(m['value'] for m in row['metrics'] if m['metric_id'] == 'container.memory_usage'))
        self.assertEqual(row['quality'], 'PARTIAL')

    def test_null_or_invalid_orchestrator_refresh_is_partial_not_server_error(self):
        original = self.client.request
        for timestamp in (None, '', 'invalid', 123, [], {}):
            with self.subTest(timestamp=timestamp):
                def invalid_refresh(action, **kwargs):
                    response = original(action, **kwargs)
                    if action == 'ceph.daemon_ls':
                        response['data'][0]['last_refresh'] = timestamp
                    return response
                self.client.request = invalid_refresh
                row = self.service.observe(daemon_types=['rgw'])['daemons'][0]
                self.assertEqual(row['key'], 'rgw.lab.node-a.abc')
                self.assertEqual(row['quality'], 'PARTIAL')
                self.assertIn('DAEMON_RUNTIME_TIMESTAMP_UNAVAILABLE', row['limitations'])
                self.assertEqual(row['fields']['orchestrator_observed_at'], timestamp)

    def test_no_mds_is_valid_empty_not_missing_or_fabricated(self):
        self.assertEqual(normalize('mds', {'ceph.fs_dump': {'data': {'filesystems': [], 'standbys': []}}}), [])

    def test_malformed_sources_cannot_masquerade_as_empty_inventory(self):
        for action, value in [('ceph.daemon_ls', {}), ('ceph.daemon_ls', [None]),
            ('ceph.fs_dump', {}), ('ceph.fs_dump', {'filesystems': [{}], 'standbys': []}),
            ('ceph.fs_dump', {'filesystems': [], 'standbys': [{'gid': 1}]})]:
            self.assertFalse(daemon_source_valid(action, value))
        self.assertTrue(daemon_source_valid('ceph.fs_dump', {'filesystems': [], 'standbys': []}))
        self.assertTrue(daemon_source_valid('ceph.daemon_ls', []))
        original = self.client.request
        def malformed(action, **kwargs):
            response = original(action, **kwargs)
            if action == 'ceph.daemon_ls':
                response['data'] = {'not': 'a daemon list'}
            return response
        self.client.request = malformed
        result = self.service.observe(daemon_types=['rgw'])
        self.assertEqual(result['sources']['ceph.daemon_ls']['quality'], 'UNAVAILABLE')
        self.assertEqual(result['quality'], 'PARTIAL')
        self.assertEqual(result['daemons'], [])

    def test_deep_environment_keeps_source_quality_and_exact_host_scope(self):
        result = self.service.observe(daemon_keys=['rgw.lab.node-a.abc'], deep=True)
        self.assertEqual(result['system']['environment']['scope'], 'SSH_CLIENT_HOST_ONLY')
        self.assertEqual(result['sources']['ceph.client_environment']['quality'], 'PARTIAL')
        self.assertEqual(result['quality'], 'PARTIAL')
        self.assertNotIn('session_id', result)

    def test_rgw_collection_compare_and_api_all_five_types(self):
        first = self.service.create(daemon_keys=['rgw.lab.node-a.abc'], phase='BEFORE')
        second = self.service.create(daemon_keys=['rgw.lab.node-a.abc'], phase='AFTER')
        comparison = self.service.compare(collection_a_id=first['id'], collection_b_id=second['id'], daemon_type='rgw')
        self.assertEqual(len(comparison['rows']), 1)
        app = FastAPI()
        app.include_router(router)
        with patch('app.modules.as_is.api._service', return_value=self.service), TestClient(app) as http:
            response = http.post('/api/v1/as-is/observe', json={'daemon_types': ['mon', 'mgr', 'osd', 'rgw', 'mds']})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['capabilities']['mds'])
            self.assertEqual(http.post('/api/v1/as-is/observe', json={'daemon_keys': ['rgw.name;echo']} ).status_code, 422)


if __name__ == '__main__':
    unittest.main()
