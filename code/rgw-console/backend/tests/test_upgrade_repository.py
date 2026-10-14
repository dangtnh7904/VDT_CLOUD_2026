from __future__ import annotations

import os
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.config import Settings
from app.migrations.runner import migrate
from app.modules.sessions.domain import CreateSessionCommand
from app.modules.sessions.repository import PostgresSessionRepository
from app.modules.upgrade_common.domain import (
    BatchParameters,
    Strategy,
    UpgradeBatchSpec,
    UpgradeRunSpec,
)
from app.modules.upgrade_common.repository import PostgresUpgradeRepository
from app.platform.config import build_config_snapshot
from app.platform.evidence import StoredArtifact


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
FSID = "11111111-2222-3333-4444-555555555555"


@unittest.skipUnless(DATABASE_URL, "set TEST_DATABASE_URL to run upgrade repository tests")
class UpgradeRepositoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        self.schema = f"upgrade_repository_test_{uuid.uuid4().hex}"
        self.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(self.schema)))
        migrate(self.conn)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    @contextmanager
    def test_connection(self):
        yield self.conn

    def test_idempotent_dry_run_persists_evidence_plan_and_timeline_atomically(self):
        settings = Settings(
            _env_file=None,
            feature_legacy_rgw=False,
            feature_legacy_rbd=False,
            feature_upgrade=True,
            cluster_id="lab-a",
            cluster_profile_revision="lab-a-v1",
            ceph_expected_fsid=FSID,
            upgrade_allowed_osds="0,2",
            upgrade_allowed_hosts="host-a,host-b",
            upgrade_allowed_pools="rbd-lab",
        )
        snapshot = build_config_snapshot(settings)
        session_id = uuid.uuid4()
        session_repository = PostgresSessionRepository()
        upgrade_repository = PostgresUpgradeRepository()
        capabilities = {
            "fsid": FSID,
            "observed_at": "2026-10-08T00:00:00Z",
            "source": {"executor_version": "1.0.0", "protocol_version": 1},
            "capabilities": {
                "query_cluster_identity": "SUPPORTED",
                "query_osd_inventory": "SUPPORTED",
                "query_pg_up_acting_primary": "UNSUPPORTED",
            },
        }

        with patch(
            "app.modules.sessions.repository.connection",
            self.test_connection,
        ), patch(
            "app.modules.upgrade_common.repository.connection",
            self.test_connection,
        ):
            session = session_repository.create(
                session_id=session_id,
                command=CreateSessionCommand("dry-run", ("UPGRADE_PRODUCTION",)),
                snapshot=snapshot,
                actual_fsid=FSID,
                execution_environment="lab",
                capabilities=capabilities,
            )
            batch_spec = UpgradeBatchSpec(
                name="canary",
                source_osds=(0,),
                destination_osds=(2,),
                parameters=BatchParameters(
                    batch_size=1,
                    drain_parallelism=1,
                    max_simultaneous_down=1,
                    return_parallelism=1,
                    scrub_concurrency=1,
                    promotion_parallelism=1,
                    chain_parallelism=1,
                    handoff_parallelism=1,
                    max_pg_per_handoff_group=32,
                    max_bytes_per_handoff_group=1024,
                ),
            )
            batch = upgrade_repository.create_batch(
                session_id=session_id,
                spec=batch_spec,
                idempotency_key="batch-key-0001",
                fingerprint="a" * 64,
                expected_cluster_id="lab-a",
                expected_fsid=FSID,
                expected_config_hash=snapshot.config_hash,
            )
            replay = upgrade_repository.create_batch(
                session_id=session_id,
                spec=batch_spec,
                idempotency_key="batch-key-0001",
                fingerprint="a" * 64,
                expected_cluster_id="lab-a",
                expected_fsid=FSID,
                expected_config_hash=snapshot.config_hash,
            )
            self.assertTrue(replay["replayed"])

            run = upgrade_repository.create_run(
                batch_id=batch["id"],
                spec=UpgradeRunSpec(
                    Strategy.PA1,
                    "17.2.7",
                    "sha256:" + "b" * 64,
                ),
                idempotency_key="run-key-0001",
                fingerprint="c" * 64,
                expected_cluster_id="lab-a",
                expected_fsid=FSID,
                expected_config_hash=snapshot.config_hash,
            )
            context = upgrade_repository.get_run_context(run["id"])
            job_id, replay_result = upgrade_repository.claim_preflight(
                run_id=run["id"],
                idempotency_key="preflight-key-0001",
                fingerprint="d" * 64,
                expected_state="CREATED",
                plan_revision=1,
                resource_version=1,
                config_snapshot_id=uuid.UUID(str(session["config_snapshot_id"])),
                reason="integration dry-run",
            )
            self.assertIsNone(replay_result)
            result = upgrade_repository.finish_preflight(
                job_id=job_id,
                context=context,
                inventory={
                    "fsid": FSID,
                    "observed_at": "2026-10-08T00:00:00Z",
                    "osdmap_epoch": 42,
                    "quality": "VALID",
                },
                capabilities=capabilities,
                plan={
                    "dry_run_result": "PASS",
                    "execution_readiness": "BLOCKED",
                    "blockers": [],
                    "warnings": ["LIVE_CAPABILITY_NOT_READY"],
                    "steps": [
                        {
                            "sequence": 1,
                            "action": "capture_baseline",
                            "resource": "batch",
                            "would_mutate": False,
                            "preconditions": [],
                        },
                        {
                            "sequence": 2,
                            "action": "drain",
                            "resource": "osd.0->osd.2",
                            "would_mutate": True,
                            "preconditions": ["LEASE_OWNED"],
                        },
                    ],
                },
                artifact=StoredArtifact(
                    id=uuid.uuid4(),
                    uri="filesystem:test/evidence.json",
                    sha256="e" * 64,
                    size_bytes=128,
                    mime_type="application/json",
                ),
                plan_hash="f" * 64,
                reason="integration dry-run",
            )

            persisted = upgrade_repository.get_run_context(run["id"])

        self.assertEqual(result["state"], "DRY_RUN_READY")
        self.assertEqual(result["operation_result"], "NOT_EXERCISED")
        self.assertEqual(persisted["dry_run_plan"]["dry_run_result"], "PASS")
        self.assertEqual(persisted["dry_run_plan"]["steps"][1]["action"], "drain")
        self.assertEqual(persisted["plan_hash"], "f" * 64)
        self.assertIsNotNone(persisted["placement_plan_id"])
        self.assertEqual(
            self.conn.execute("SELECT count(*) AS count FROM evidence_artifacts").fetchone()["count"],
            1,
        )
        self.assertEqual(
            self.conn.execute("SELECT count(*) AS count FROM placement_plans").fetchone()["count"],
            1,
        )
        self.assertEqual(
            self.conn.execute("SELECT count(*) AS count FROM run_changes").fetchone()["count"],
            1,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT count(*) AS count FROM outbox_events WHERE run_id = %s",
                (run["id"],),
            ).fetchone()["count"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
