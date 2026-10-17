from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

from app.modules.as_is.comparison import compare_collections
from app.modules.as_is.service import AsIsError
from app.modules.as_is.source_validation import source_valid
import test_as_is as fixtures


class AsIsReleaseSafetyTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AsIsTests()
        fixture.setUp()
        self.service, self.client = fixture.service, fixture.client

    def override_source(self, action, *, data=None, collected_at=None):
        original = self.client.request
        capabilities = self.client.capabilities
        self.client.capabilities = lambda: {**capabilities(), 'actions': capabilities()['actions'] + [action]}
        def request(name, **kwargs):
            response = original(name, **kwargs)
            if name == action:
                if data is not None:
                    response['data'] = data
                if collected_at is not None:
                    response['collected_at'] = collected_at
            return response
        self.client.request = request

    def test_malformed_osd_dump_is_partial_without_crashing(self):
        self.override_source('ceph.osd_dump', data=[{'osd': 0}])
        result = self.service.observe(daemon_keys=['osd.0'])
        self.assertEqual(result['sources']['ceph.osd_dump']['quality'], 'UNAVAILABLE')
        self.assertEqual(result['quality'], 'PARTIAL')
        self.assertIsNone(result['daemons'][0]['fields']['up'])

    def test_nonfinite_source_is_rejected_not_exported(self):
        self.override_source('ceph.osd_df', data={'nodes': [{'id': 0, 'utilization': float('nan')}]})
        result = self.service.observe(daemon_keys=['osd.0'])
        self.assertEqual(result['sources']['ceph.osd_df']['quality'], 'UNAVAILABLE')
        self.assertEqual(result['missing_daemon_keys'], ['osd.0'])
        json.dumps(result, allow_nan=False)

    def test_invalid_numeric_metric_field_is_not_valid(self):
        for value in ('not a number', 10 ** 1000, -1):
            self.override_source('ceph.osd_df', data={'nodes': [{'id': 0, 'kb_used': value}]})
            row = self.service.observe(daemon_keys=['osd.0'])['daemons'][0]
            metric = next(item for item in row['metrics'] if item['metric_id'] == 'osd.used_kb')
            self.assertIsNone(metric['value'])
            self.assertEqual(metric['quality'], 'UNAVAILABLE')
            self.assertEqual(metric['reason'], 'INVALID_SOURCE_FIELD')

    def test_old_cli_source_is_not_valid_fresh_metric(self):
        self.override_source('ceph.quorum_status', collected_at='2026-01-01T00:00:00+00:00')
        result = self.service.observe(daemon_keys=['mon.one'])
        self.assertEqual(result['sources']['ceph.quorum_status']['quality'], 'STALE')
        metrics = result['daemons'][0]['metrics']
        self.assertTrue(all(item['quality'] == 'STALE' for item in metrics))
        self.assertTrue(all(item['observed_at'] == '2026-01-01T00:00:00+00:00' for item in metrics))

    def test_metric_uses_its_own_source_timestamp(self):
        timestamp = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        self.override_source('ceph.quorum_status', collected_at=timestamp)
        row = self.service.observe(daemon_keys=['mon.one'])['daemons'][0]
        self.assertNotEqual(row['observed_at'], timestamp)
        self.assertTrue(all(item['observed_at'] == timestamp for item in row['metrics']))

    def test_source_shape_validator_rejects_invalid_empty_maps(self):
        for action in ('ceph.mon_dump', 'ceph.quorum_status', 'ceph.mgr_dump', 'ceph.osd_df', 'ceph.osd_tree', 'ceph.osd_dump', 'ceph.crush_dump', 'ceph.pg_dump'):
            self.assertFalse(source_valid(action, {}), action)
        self.assertTrue(source_valid('ceph.mon_dump', {'mons': []}))
        self.assertTrue(source_valid('ceph.osd_dump', {'osds': [], 'pools': []}))

    def test_invalid_or_unrepresentable_date_filters_are_422(self):
        for value in ('9999-12-31', '20261012', '2026-W42-1', '2026-02-30'):
            with self.assertRaises(AsIsError) as error:
                self.service.list(to_date=value)
            self.assertEqual(error.exception.code, 'INVALID_DATE')
            self.assertEqual(error.exception.status, 422)

    def test_historical_profile_change_blocks_reads_not_metadata_delete_restore(self):
        first = self.service.create(daemon_keys=['osd.0'], phase='BEFORE')
        sha = first['sha256']
        for option in ('upgrade_allowed_osds', 'upgrade_allowed_hosts', 'upgrade_allowed_pools'):
            original = getattr(self.service.settings, option)
            setattr(self.service.settings, option, 'other')
            with self.assertRaises(AsIsError) as error:
                self.service.get(first['id'])
            self.assertEqual(error.exception.code, 'COLLECTION_SCOPE_REJECTED')
            self.assertEqual(error.exception.status, 403)
            self.assertEqual(self.service.set_deleted(first['id'], deleted=True, actor='test')['sha256'], sha)
            self.assertEqual(self.service.set_deleted(first['id'], deleted=False, actor='test')['sha256'], sha)
            setattr(self.service.settings, option, original)
        self.assertEqual(self.service.get(first['id'])['sha256'], sha)

    def test_metric_kind_change_blocks_delta_even_with_same_value_and_unit(self):
        a = self.service.create(daemon_keys=['mon.one'], phase='BEFORE')
        b = copy.deepcopy(a)
        a['daemons'][0]['metrics'] = [{'metric_id': 'test', 'value': 10, 'kind': 'counter', 'unit': 'count', 'quality': 'VALID'}]
        b['daemons'][0]['metrics'] = [{**a['daemons'][0]['metrics'][0], 'kind': 'gauge'}]
        change = compare_collections(a, b, 'mon')['rows'][0]['changes'][0]
        self.assertEqual(change['reason'], 'METRIC_KIND_CHANGED')
        self.assertIsNone(change['delta'])

    def test_counter_reset_does_not_mask_incarnation_change(self):
        a = self.service.create(daemon_keys=['mgr.one'], phase='BEFORE')
        b = copy.deepcopy(a)
        b['daemons'][0]['fields']['gid'] = 50
        a['daemons'][0]['metrics'] = [{'metric_id': 'test', 'value': 10, 'kind': 'counter', 'unit': 'count', 'quality': 'VALID'}]
        b['daemons'][0]['metrics'] = [{**a['daemons'][0]['metrics'][0], 'value': 2}]
        change = next(item for item in compare_collections(a, b, 'mgr')['rows'][0]['changes'] if item['field'] == 'metrics.test')
        self.assertEqual(change['reason'], 'INCARNATION_CHANGED')
        self.assertIsNone(change['delta'])

    def test_overflow_delta_has_reason_and_remains_json_safe(self):
        a = self.service.create(daemon_keys=['mon.one'], phase='BEFORE')
        b = copy.deepcopy(a)
        a['daemons'][0]['metrics'] = [{'metric_id': 'test', 'value': -1e308, 'kind': 'gauge', 'unit': 'count', 'quality': 'VALID'}]
        b['daemons'][0]['metrics'] = [{**a['daemons'][0]['metrics'][0], 'value': 1e308}]
        comparison = compare_collections(a, b, 'mon')
        change = comparison['rows'][0]['changes'][0]
        self.assertEqual(change['reason'], 'NUMERIC_OUT_OF_RANGE')
        self.assertIsNone(change['delta'])
        json.dumps(comparison, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
