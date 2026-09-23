from __future__ import annotations

import os
import unittest
import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.migrations.runner import (
    MigrationError,
    assert_schema_current,
    load_migrations,
    migrate,
)


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "set TEST_DATABASE_URL to run PostgreSQL migration tests")
class MigrationRunnerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        self.schema = f"migration_test_{uuid.uuid4().hex}"
        self.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn.execute(
            sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(self.schema))
        )

    def tearDown(self) -> None:
        self.conn.rollback()
        self.conn.close()

    def test_fresh_database_is_migrated_and_rerun_is_idempotent(self) -> None:
        first = migrate(self.conn)
        second = migrate(self.conn)

        self.assertEqual(first.applied_versions, (1, 2, 3, 4, 5, 6))
        self.assertEqual(first.stamped_versions, ())
        self.assertEqual(second.applied_versions, ())
        self.assertEqual(second.current_version, 6)
        self.assertEqual(assert_schema_current(self.conn), 6)
        self.assertEqual(
            self.conn.execute("SELECT count(*) AS count FROM schema_migrations").fetchone()[
                "count"
            ],
            6,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT desired_state FROM control_state WHERE id = true"
            ).fetchone()[
                "desired_state"
            ],
            "NORMAL",
        )

    def test_current_legacy_schema_is_stamped_and_data_is_preserved(self) -> None:
        baseline = load_migrations()[0]
        self.conn.execute(baseline.sql)
        self.conn.execute(
            """
            INSERT INTO stream_jobs (id, state, config, sent_count, failed_count, bytes_sent)
            VALUES (
              '11111111-1111-1111-1111-111111111111',
              'running',
              '{"client_id":"legacy"}'::jsonb,
              9,
              1,
              2048
            )
            """
        )
        self.conn.execute(
            """
            INSERT INTO operations (
              kind, success, bytes_count, latency_ms, bucket, object_key
            )
            VALUES ('PUT', true, 2048, 3.5, 'legacy-bucket', 'legacy-key')
            """
        )

        result = migrate(self.conn)

        self.assertEqual(result.stamped_versions, (1,))
        self.assertEqual(result.applied_versions, (2, 3, 4, 5, 6))
        job = self.conn.execute(
            "SELECT * FROM stream_jobs WHERE id = %s",
            ("11111111-1111-1111-1111-111111111111",),
        ).fetchone()
        operation = self.conn.execute(
            "SELECT * FROM operations WHERE bucket = 'legacy-bucket'"
        ).fetchone()
        self.assertEqual(job["job_type"], "legacy_put")
        self.assertEqual(job["sent_count"], 9)
        self.assertEqual(job["bytes_sent"], 2048)
        self.assertEqual(operation["bytes_count"], 2048)
        self.assertEqual(operation["target_type"], "RGW_OBJECT")
        self.assertEqual(operation["target_id"], "rgw:13:legacy-bucket:legacy-key")

    def test_unknown_partial_schema_is_rejected_without_guessing(self) -> None:
        self.conn.execute("CREATE TABLE operations (id BIGINT PRIMARY KEY)")

        with self.assertRaises(MigrationError):
            migrate(self.conn)

        self.assertIsNone(
            self.conn.execute("SELECT to_regclass('schema_migrations') AS name").fetchone()[
                "name"
            ]
        )


if __name__ == "__main__":
    unittest.main()
