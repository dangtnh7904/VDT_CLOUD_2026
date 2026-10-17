from __future__ import annotations

import copy
import hashlib
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.as_is.api import router
from app.modules.as_is.service import AsIsError, digest
import test_as_is as fixtures


class FilteredExportTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AsIsTests()
        fixture.setUp()
        self.service = fixture.service
        original = fixture.collect()
        # A mixed saved collection with two OSD rows, retaining a valid checksum.
        row = fixture.repo.rows[original['id']]
        second = copy.deepcopy(next(item for item in row['payload']['daemons'] if item['type'] == 'osd'))
        second.update(key='osd.1', id='1', name='osd.1')
        row['payload']['daemons'].append(second)
        row['payload']['requested_daemon_keys'].append('osd.1')
        row['sha256'] = digest(row['payload'])
        self.service.settings.upgrade_allowed_osds = '0,1'
        self.saved = self.service.get(original['id'])
        self.original_row = copy.deepcopy(row)
        self.app = FastAPI()
        self.app.include_router(router)

    def test_no_filter_returns_exact_original_export(self):
        self.assertEqual(self.service.export_view(self.saved['id']), self.saved)

    def test_mixed_collection_type_and_exact_daemon_filters_do_not_change_parent(self):
        with patch('app.modules.as_is.api._service', return_value=self.service), TestClient(self.app) as http:
            response = http.get(f"/api/v1/as-is/collections/{self.saved['id']}/export", params={'daemon_type': 'osd'})
            self.assertEqual(response.status_code, 200)
            projected = response.json()
            self.assertEqual(projected['kind'], 'FILTERED_AS_IS_EXPORT')
            self.assertEqual({row['key'] for row in projected['daemons']}, {'osd.0', 'osd.1'})
            self.assertEqual(projected['source_collection']['id'], self.saved['id'])
            self.assertEqual(projected['source_sha256'], self.saved['sha256'])
            self.assertNotIn('sha256', projected)
            self.assertNotIn('artifact', projected)
            self.assertEqual(response.headers['x-export-sha256'], hashlib.sha256(response.content).hexdigest())
            self.assertNotEqual(response.headers['x-export-sha256'], projected['source_sha256'])
            response = http.get(f"/api/v1/as-is/collections/{self.saved['id']}/export", params={'daemon_type': 'osd', 'daemon_key': 'osd.1'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row['key'] for row in response.json()['daemons']], ['osd.1'])
        self.assertEqual(self.service.repository.rows[self.saved['id']], self.original_row)
        self.assertEqual(self.service.get(self.saved['id']), self.saved)

    def test_missing_daemon_and_mismatched_prefix_rejected(self):
        with patch('app.modules.as_is.api._service', return_value=self.service), TestClient(self.app) as http:
            for params, status in [({'daemon_type': 'nope'}, 422),
                ({'daemon_type': 'mon', 'daemon_key': 'osd.1'}, 422),
                ({'daemon_type': 'osd', 'daemon_key': 'osd.0;echo'}, 422),
                ({'daemon_type': 'osd', 'daemon_key': 'osd.9'}, 404),
                ({'daemon_type': 'rgw'}, 404)]:
                with self.subTest(params=params):
                    response = http.get(f"/api/v1/as-is/collections/{self.saved['id']}/export", params=params)
                    self.assertEqual(response.status_code, status)
        self.assertEqual(self.service.repository.rows[self.saved['id']], self.original_row)

    def test_key_only_filter_derives_type_and_service_validates_bad_keys(self):
        result = self.service.export_view(self.saved['id'], daemon_key='mon.one')
        self.assertEqual(result['filter'], {'daemon_type': 'mon', 'daemon_key': 'mon.one'})
        self.assertEqual([row['key'] for row in result['daemons']], ['mon.one'])
        for filters in ({'daemon_type': 'bogus'}, {'daemon_key': 'not-a-daemon'},
                        {'daemon_type': 'mon', 'daemon_key': 'osd.1'}):
            with self.subTest(filters=filters), self.assertRaises(AsIsError) as caught:
                self.service.export_view(self.saved['id'], **filters)
            self.assertEqual(caught.exception.status, 422)


if __name__ == '__main__':
    unittest.main()
