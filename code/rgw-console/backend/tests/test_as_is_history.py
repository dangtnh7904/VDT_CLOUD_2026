from __future__ import annotations

import base64
import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.modules.as_is.api import router
from app.modules.as_is.pagination import decode_cursor, encode_cursor, InvalidCursor
from app.modules.as_is.repository import AsIsRepository
from app.modules.as_is.service import AsIsService, AsIsError, digest


FSID = '11111111-2222-3333-4444-555555555555'


class HistoryRepository:
    def __init__(self, count=215):
        self.filters = None
        stamp = datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)
        self.rows = [{
            'id': str(UUID(int=i + 1)), 'cluster_id': 'lab', 'fsid': FSID,
            'started_at': stamp.isoformat(), 'completed_at': stamp.isoformat(),
            'daemon_keys': ['osd.2'], 'daemon_types': ['osd'], 'phase': 'BEFORE',
            'note': 'lịch sử', 'quality': 'VALID', 'deleted_at': None,
        } for i in range(count)]

    def list(self, *, before=None, limit, **filters):
        self.filters = filters
        rows = [r for r in self.rows if r['cluster_id'] == filters['cluster_id'] and r['fsid'] == filters['fsid']]
        for name in ('phase', 'quality'):
            if filters.get(name):
                rows = [r for r in rows if r[name] == filters[name]]
        if filters.get('daemon_type'):
            rows = [r for r in rows if filters['daemon_type'] in r['daemon_types']]
        if filters.get('daemon_key'):
            rows = [r for r in rows if filters['daemon_key'] in r['daemon_keys']]
        if not filters['include_deleted']:
            rows = [r for r in rows if not r.get('deleted_at')]
        if filters.get('query'):
            rows = [r for r in rows if filters['query'].lower() in f"{r['id']} {r['note']} {' '.join(r['daemon_keys'])}".lower()]
        def position(row):
            return datetime.fromisoformat(row['started_at']), UUID(row['id'])
        rows.sort(key=position, reverse=True)
        if before:
            rows = [row for row in rows if position(row) < before]
        return copy.deepcopy(rows[:limit])

    def get(self, collection_id, *, include_deleted=False, **identity):
        row = next((r for r in self.rows if r['id'] == str(collection_id)), None)
        if not row or any(row[k] != value for k, value in identity.items()) or row.get('deleted_at') and not include_deleted:
            return None
        payload = {k: v for k, v in row.items() if k not in {'deleted_at'}}
        return {**row, 'payload': payload, 'sha256': digest(payload)}


class AsIsHistoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = HistoryRepository()
        self.service = AsIsService(Settings(_env_file=None, cluster_id='lab', ceph_expected_fsid=FSID), self.repo)

    def test_keyset_reaches_all_215_rows_with_identical_timestamps(self):
        cursor = None
        ids = []
        while True:
            page = self.service.list(limit=10, cursor=cursor)
            self.assertLessEqual(len(page['items']), 10)
            self.assertEqual(page['has_more'], bool(page['next_cursor']))
            ids.extend(row['id'] for row in page['items'])
            cursor = page['next_cursor']
            if not cursor:
                break
        self.assertEqual(len(ids), 215)
        self.assertEqual(len(set(ids)), 215)
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_newer_insert_between_pages_does_not_shift_original_rows(self):
        first = self.service.list(limit=10)
        self.repo.rows.append({**self.repo.rows[0], 'id': str(UUID(int=999)),
                               'started_at': '2026-10-12T14:00:00+00:00'})
        second = self.service.list(limit=10, cursor=first['next_cursor'])
        self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})
        self.assertEqual(UUID(second['items'][0]['id']).int, 205)

    def test_cursor_rejects_filter_or_cluster_change_but_allows_page_size(self):
        first = self.service.list(limit=10, daemon_type='osd', query=' lịch sử ', quality='VALID')
        self.assertEqual(len(self.service.list(limit=20, cursor=first['next_cursor'], daemon_type='osd', query='lịch sử', quality='VALID')['items']), 20)
        with self.assertRaises(AsIsError) as error:
            self.service.list(cursor=first['next_cursor'], daemon_type='mon', query='lịch sử', quality='VALID')
        self.assertEqual(error.exception.code, 'INVALID_CURSOR')
        with self.assertRaises(AsIsError):
            self.service.list(cursor=first['next_cursor'], daemon_type='osd', query='lịch sử', quality='VALID', include_deleted=True)
        filters = {'cluster_id': 'lab', 'fsid': FSID}
        cursor = encode_cursor(self.repo.rows[0], filters)
        with self.assertRaises(InvalidCursor):
            decode_cursor(cursor, {**filters, 'fsid': 'other'})

    def test_cursor_rejects_malformed_timezone_and_identifier(self):
        for cursor in ('!', 'x' * 1025, '', base64.urlsafe_b64encode(b'[]').decode().rstrip('=')):
            with self.assertRaises(InvalidCursor):
                decode_cursor(cursor, {})
        valid = encode_cursor(self.repo.rows[0], {})
        decoded = json.loads(base64.urlsafe_b64decode(valid + '=' * (-len(valid) % 4)))
        for field, value in [('at', '2026-10-12T00:00:00'), ('id', 'not-a-uuid'), ('v', 99)]:
            body = {**decoded, field: value}
            bad = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip('=')
            with self.assertRaises(InvalidCursor):
                decode_cursor(bad, {})

    def test_server_search_quality_and_daemon_filters_precede_pagination(self):
        self.repo.rows[0].update(note='needle % _', quality='PARTIAL', daemon_keys=['osd.5'])
        filtered = self.service.list(query='needle % _', quality='PARTIAL', daemon_key='osd.5')
        self.assertEqual([r['id'] for r in filtered['items']], [self.repo.rows[0]['id']])
        self.assertFalse(filtered['has_more'])

    def test_repository_uses_parameterized_scope_and_tuple_boundary(self):
        fake_conn = MagicMock()
        fake_conn.execute.return_value.fetchall.return_value = []
        with patch('app.modules.as_is.repository.connection') as connection:
            connection.return_value.__enter__.return_value = fake_conn
            AsIsRepository().list(cluster_id='lab', fsid=FSID, query="%' OR true --", before=(datetime.now(timezone.utc), UUID(int=20)), limit=11)
        sql, params = fake_conn.execute.call_args.args
        self.assertIn('(started_at,id) <', sql)
        self.assertIn('cluster_id=%s AND fsid=%s', sql)
        self.assertNotIn("%' OR true --", sql)
        self.assertIn("%' OR true --", params)
        self.assertEqual(params[-1], 11)

    def test_api_default_page_ten_cursor_contract_and_deleted_view_export(self):
        app = FastAPI()
        app.include_router(router)
        row = self.repo.rows[0]
        row['deleted_at'] = '2026-10-12T15:00:00+00:00'
        with patch('app.modules.as_is.api._service', return_value=self.service), TestClient(app) as client:
            page = client.get('/api/v1/as-is/collections').json()
            self.assertEqual(page['limit'], 10)
            self.assertEqual(len(page['items']), 10)
            self.assertTrue(page['has_more'])
            response = client.get('/api/v1/as-is/collections', params={'cursor': page['next_cursor']})
            self.assertEqual(response.status_code, 200)
            for suffix in ('', '/export'):
                path = f"/api/v1/as-is/collections/{row['id']}{suffix}"
                self.assertEqual(client.get(path).status_code, 404)
                response = client.get(path, params={'include_deleted': 'true'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['deleted_at'], row['deleted_at'])
            self.assertEqual(client.get('/api/v1/as-is/collections?limit=201').status_code, 422)
            self.assertEqual(client.get('/api/v1/as-is/collections?quality=FAILED').status_code, 422)


if __name__ == '__main__':
    unittest.main()
