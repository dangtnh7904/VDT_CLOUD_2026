from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.migrations.runner import migrate, load_migrations
from app.modules.as_is.repository import AsIsRepository
from app.modules.as_is.service import digest


DATABASE_URL = os.environ.get('TEST_DATABASE_URL')
FSID = '11111111-2222-3333-4444-555555555555'
OTHER_FSID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'


@unittest.skipUnless(DATABASE_URL, 'set TEST_DATABASE_URL for As-is repository persistence tests')
class AsIsRepositoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        # The entire schema, migrations and fixture rows belong to one outer
        # transaction. Repository transactions are savepoints, not commits.
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.schema = 'as_is_repository_test_' + uuid4().hex
        self.conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.conn.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(self.schema)))
        migrate(self.conn)
        self.assertEqual(self.conn.execute('SELECT max(version) AS version FROM schema_migrations').fetchone()['version'], load_migrations()[-1].version)
        self.patcher = patch('app.modules.as_is.repository.connection', self.connection_factory)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.repo = AsIsRepository()
        self.identity = {'cluster_id': 'lab', 'fsid': FSID}

    @contextmanager
    def connection_factory(self):
        yield self.conn

    def payload(self, number=1, **changes):
        started = datetime(2026, 10, 12, 13, tzinfo=timezone.utc).isoformat()
        return {'id': str(UUID(int=number)), **self.identity, 'phase': 'BEFORE', 'note': 'Thu thập hiện trạng',
            'actor': 'test-operator', 'started_at': started, 'completed_at': started,
            'quality': 'VALID', 'requested_daemon_keys': ['osd.2'], 'requested_daemon_types': ['osd'],
            'daemons': [{'key': 'osd.2', 'type': 'osd', 'id': '2', 'fields': {'weight': 0.5}}],
            'system': {'hosts': [], 'pools': []}, **changes}

    def save(self, payload):
        self.repo.save(payload, sha256=digest(payload), request_hash=digest({'id': payload['id']}), actor=payload['actor'])
        return self.repo.get(UUID(payload['id']), **self.identity)

    def test_save_get_roundtrip_and_conflicting_replay_leave_payload_hash_unchanged(self):
        payload = self.payload(note='Tiếng Việt — không mất Unicode')
        saved = self.save(payload)
        self.assertEqual(saved['payload'], payload)
        self.assertEqual(saved['sha256'], digest(payload))
        self.assertEqual(saved['daemon_keys'], ['osd.2'])
        self.assertEqual(saved['daemon_types'], ['osd'])
        self.save({**payload, 'note': 'Không được ghi đè'})
        current = self.repo.get(UUID(payload['id']), **self.identity)
        self.assertEqual(current['payload'], payload)
        self.assertEqual(current['sha256'], saved['sha256'])
        events = self.conn.execute('SELECT event_type,sha256 FROM as_is_collection_events').fetchall()
        self.assertEqual(events, [{'event_type': 'CREATED', 'sha256': saved['sha256']}])

    def test_keyset_reaches_more_than_200_rows_with_identical_timestamps(self):
        for number in range(1, 216):
            self.save(self.payload(number))
        before, identifiers = None, []
        while True:
            rows = self.repo.list(**self.identity, before=before, limit=10)
            if not rows:
                break
            identifiers.extend(row['id'] for row in rows)
            before = datetime.fromisoformat(rows[-1]['started_at']), UUID(rows[-1]['id'])
        self.assertEqual(identifiers, [str(UUID(int=number)) for number in range(215, 0, -1)])
        self.assertEqual(len(set(identifiers)), 215)

    def test_server_filters_and_cluster_fsid_scopes_are_applied_in_postgres(self):
        self.save(self.payload(1, note='needle %_ tiếng Việt', quality='PARTIAL', phase='AFTER', requested_daemon_keys=['osd.5']))
        self.save(self.payload(2))
        self.save(self.payload(3, cluster_id='other'))
        self.save(self.payload(4, fsid=OTHER_FSID))
        local = timezone(timedelta(hours=7))
        matches = self.repo.list(**self.identity, daemon_type='osd', daemon_key='osd.5', phase='AFTER', quality='PARTIAL', query='needle %_',
            start=datetime(2026, 10, 12, tzinfo=local), end=datetime(2026, 10, 13, tzinfo=local), limit=10)
        self.assertEqual([row['id'] for row in matches], [str(UUID(int=1))])
        self.assertEqual(self.repo.list(**self.identity, query="%' OR true --"), [])
        self.assertEqual(len(self.repo.list(**self.identity)), 2)
        self.assertIsNone(self.repo.get(UUID(int=3), **self.identity))
        self.assertIsNone(self.repo.get(UUID(int=4), **self.identity))
        self.assertIsNone(self.repo.set_deleted(UUID(int=4), **self.identity, deleted=True, actor='test'))
        self.assertEqual(self.repo.get(UUID(int=4), cluster_id='lab', fsid=OTHER_FSID)['deleted_at'], None)

    def test_soft_delete_restore_filters_and_events_keep_identical_sha(self):
        payload = self.payload()
        saved = self.save(payload)
        for _ in range(2):
            deleted = self.repo.set_deleted(UUID(payload['id']), **self.identity, deleted=True, actor='delete-operator')
            self.assertIsNotNone(deleted['deleted_at'])
            self.assertEqual(deleted['payload'], payload)
            self.assertEqual(deleted['sha256'], saved['sha256'])
        self.assertIsNone(self.repo.get(UUID(payload['id']), **self.identity))
        self.assertEqual(self.repo.list(**self.identity), [])
        self.assertEqual(len(self.repo.list(**self.identity, include_deleted=True)), 1)
        self.assertEqual(self.repo.get(UUID(payload['id']), **self.identity, include_deleted=True)['deleted_by'], 'delete-operator')
        for _ in range(2):
            restored = self.repo.set_deleted(UUID(payload['id']), **self.identity, deleted=False, actor='restore-operator')
            self.assertIsNone(restored['deleted_at'])
            self.assertIsNone(restored['deleted_by'])
            self.assertEqual(restored['sha256'], saved['sha256'])
            self.assertEqual(restored['payload'], payload)
        events = self.conn.execute('SELECT event_type,actor,sha256 FROM as_is_collection_events ORDER BY id').fetchall()
        self.assertEqual([event['event_type'] for event in events], ['CREATED', 'DELETED', 'RESTORED'])
        self.assertTrue(all(event['sha256'] == saved['sha256'] for event in events))
        self.assertEqual([event['actor'] for event in events], ['test-operator', 'delete-operator', 'restore-operator'])

    def test_outer_transaction_rollback_removes_only_its_temporary_schema(self):
        self.save(self.payload())
        self.conn.rollback()
        self.assertIsNone(self.conn.execute('SELECT nspname FROM pg_namespace WHERE nspname=%s', (self.schema,)).fetchone())
        self.assertEqual(self.conn.execute('SELECT current_schema() AS name').fetchone()['name'], 'public')


if __name__ == '__main__':
    unittest.main()
