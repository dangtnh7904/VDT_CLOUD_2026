from __future__ import annotations

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings as application_settings
from app.services import capacity_guard
from app.services.capacity_guard import CapacityRejected, decide, require_admission, snapshot_response


def policy(*, fsid: str, observe_only: bool = False):
    return SimpleNamespace(
        ceph_expected_fsid=fsid,
        rgw_affected_pool_set=frozenset({"rgw.data"}),
        capacity_observe_only=observe_only,
        capacity_hard_ceiling_ratio=0.70,
        capacity_admission_stop_ratio=0.68,
        capacity_throttle_start_ratio=0.67,
        capacity_resume_ratio=0.67,
        capacity_metrics_max_age_seconds=60,
        capacity_raw_overhead_factor=1.0,
        capacity_fixed_metadata_bytes_per_object=0,
        capacity_safety_margin_ratio_per_osd=0.0,
        capacity_safety_margin_min_bytes_per_osd=0,
        capacity_emergency_maintenance_bytes=64,
        capacity_pause_on_degraded_or_remapped=True,
        capacity_fail_closed_on_osdmap_change=True,
        capacity_operation_lease_seconds=30,
        rbd_executor_url="http://executor:3001",
        rbd_executor_token="x" * 32,
        rbd_allowed_pool_set=frozenset({"rbd-lab"}),
    )


def telemetry(fsid: str, *, used: int = 650, total: int = 1000):
    snapshot = {
        "id": 1,
        "fsid": fsid,
        "osdmap_epoch": 42,
        "captured_at": datetime.now(timezone.utc),
        "fresh": True,
        "cluster_health_summary": {},
    }
    osds = [
        {
            "osd_id": 0,
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": total - used,
            "used_ratio": used / total,
            "is_up": True,
            "is_in": True,
            "host": "host-a",
            "device_class": "hdd",
            "scope_metadata": {
                "eligible_pools": ["rgw.data"],
                "pool_ids": {"rgw.data": 7},
                "capacity_scope_complete": True,
            },
        }
    ]
    return {"desired_state": "NORMAL", "reason": None}, snapshot, osds


class _EpochConnection:
    def execute(self, *_args, **_kwargs):
        return SimpleNamespace(fetchall=lambda: [{"osdmap_epoch": 42}])


class _SnapshotConnection:
    def execute(self, statement, *_args, **_kwargs):
        if "coalesce(sum" in statement:
            return SimpleNamespace(fetchone=lambda: {"pending": 0, "commitment": 0})
        return SimpleNamespace(fetchone=lambda: None)

    def commit(self):
        return None


class CapacityTelemetryResponseTests(unittest.TestCase):
    def test_no_snapshot_distinguishes_configuration_state(self):
        configured = policy(fsid=str(uuid4()))
        with (
            patch.object(capacity_guard, "get_settings", return_value=configured),
            patch.object(
                capacity_guard,
                "_load_control_and_snapshot",
                return_value=({"desired_state": "NORMAL", "reason": None}, None, []),
            ),
        ):
            response = snapshot_response()
        self.assertEqual(response["telemetry"]["status"], "NO_SNAPSHOT")

        configured.rbd_executor_token = None
        with (
            patch.object(capacity_guard, "get_settings", return_value=configured),
            patch.object(
                capacity_guard,
                "_load_control_and_snapshot",
                return_value=({"desired_state": "NORMAL", "reason": None}, None, []),
            ),
        ):
            response = snapshot_response()
        self.assertEqual(response["telemetry"]["status"], "NOT_CONFIGURED")

    def test_stale_and_executor_error_are_explicit(self):
        settings = policy(fsid=str(uuid4()))
        base = {
            "id": 1,
            "fsid": settings.ceph_expected_fsid,
            "osdmap_epoch": 42,
            "captured_at": datetime.now(timezone.utc) - timedelta(minutes=2),
            "last_success_at": datetime.now(timezone.utc) - timedelta(minutes=2),
            "fresh": True,
            "cluster_health_summary": {},
        }
        connection = _SnapshotConnection()
        with (
            patch.object(capacity_guard, "get_settings", return_value=settings),
            patch.object(
                capacity_guard,
                "_load_control_and_snapshot",
                return_value=({"desired_state": "NORMAL", "reason": None}, base, []),
            ),
            patch.object(capacity_guard, "connection", return_value=nullcontext(connection)),
        ):
            response = snapshot_response()
        self.assertEqual(response["telemetry"]["status"], "STALE")

        failed = {**base, "fresh": False, "cluster_health_summary": {"collector_error_code": "EXECUTOR_UNAVAILABLE"}}
        with (
            patch.object(capacity_guard, "get_settings", return_value=settings),
            patch.object(
                capacity_guard,
                "_load_control_and_snapshot",
                return_value=({"desired_state": "NORMAL", "reason": None}, failed, []),
            ),
            patch.object(capacity_guard, "connection", return_value=nullcontext(connection)),
        ):
            response = snapshot_response()
        self.assertEqual(response["telemetry"]["status"], "EXECUTOR_UNAVAILABLE")


class CapacityDecisionTests(unittest.TestCase):
    def test_projected_per_osd_threshold_blocks_in_enforcement(self):
        fsid = str(uuid4())
        with (
            patch.object(capacity_guard, "get_settings", return_value=policy(fsid=fsid)),
            patch.object(capacity_guard, "_load_control_and_snapshot", return_value=telemetry(fsid)),
        ):
            result = decide(
                "PUT",
                30,
                persist=False,
                affected_pools=["rgw.data"],
                _db_conn=_EpochConnection(),
            )

        self.assertEqual(result.decision, "BLOCK")
        self.assertEqual(result.state, "PAUSED_CAPACITY")
        self.assertAlmostEqual(result.projected_ratios["0"], 0.68)

    def test_observe_only_records_same_risk_but_admits(self):
        fsid = str(uuid4())
        with (
            patch.object(
                capacity_guard,
                "get_settings",
                return_value=policy(fsid=fsid, observe_only=True),
            ),
            patch.object(capacity_guard, "_load_control_and_snapshot", return_value=telemetry(fsid)),
        ):
            result = decide(
                "PUT",
                30,
                persist=False,
                affected_pools=["rgw.data"],
                _db_conn=_EpochConnection(),
            )

        self.assertEqual(result.decision, "ADMIT")
        self.assertEqual(result.state, "PAUSED_CAPACITY")
        self.assertIn("observe-only override", result.reason)

    def test_mismatched_cluster_identity_fails_closed(self):
        expected = str(uuid4())
        observed = str(uuid4())
        with (
            patch.object(capacity_guard, "get_settings", return_value=policy(fsid=expected)),
            patch.object(
                capacity_guard,
                "_load_control_and_snapshot",
                return_value=telemetry(observed),
            ),
        ):
            result = decide(
                "PUT",
                1,
                persist=False,
                affected_pools=["rgw.data"],
                _db_conn=_EpochConnection(),
            )

        self.assertEqual(result.decision, "BLOCK")
        self.assertEqual(result.state, "BLOCKED_UNKNOWN_CAPACITY")

    def test_rbd_format_requires_fresh_health_even_in_observe_only_mode(self):
        fsid = str(uuid4())
        control, snapshot, osds = telemetry(fsid)
        snapshot["fresh"] = False
        with (
            patch.object(
                capacity_guard,
                "get_settings",
                return_value=policy(fsid=fsid, observe_only=True),
            ),
            patch.object(
                capacity_guard,
                "_load_control_and_snapshot",
                return_value=(control, snapshot, osds),
            ),
        ):
            result = decide(
                "RBD_FORMAT",
                0,
                persist=False,
                affected_pools=["rgw.data"],
                _db_conn=_EpochConnection(),
            )

        self.assertEqual(result.decision, "BLOCK")
        self.assertEqual(result.state, "BLOCKED_TELEMETRY")


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DATABASE_URL, "set TEST_DATABASE_URL to run capacity concurrency tests")
class CapacityConcurrencyIntegrationTests(unittest.TestCase):
    def setUp(self):
        if TEST_DATABASE_URL != application_settings().database_url:
            self.skipTest("TEST_DATABASE_URL must match DATABASE_URL for pooled guard integration")
        self.fsid = str(uuid4())
        self.requests = [str(uuid4()), str(uuid4())]
        self.settings = policy(fsid=self.fsid)
        with psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row) as conn:
            snapshot = conn.execute(
                """
                INSERT INTO capacity_snapshots (
                  fsid,osdmap_epoch,captured_at,collector_version,fresh,cluster_health_summary
                ) VALUES (%s,42,now(),'integration-test',true,%s::jsonb)
                RETURNING id,captured_at
                """,
                (self.fsid, '{"status":"HEALTH_OK","capacity_scope_complete":true}'),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO capacity_osds (
                  snapshot_id,osd_id,total_bytes,used_bytes,available_bytes,used_ratio,
                  is_up,is_in,host,device_class,scope_metadata
                ) VALUES (%s,0,1000,650,350,0.65,true,true,'host-a','hdd',%s::jsonb)
                """,
                (
                    snapshot["id"],
                    '{"eligible_pools":["rgw.data"],"pool_ids":{"rgw.data":7},"capacity_scope_complete":true}',
                ),
            )
        self.snapshot_telemetry = (
            {"desired_state": "NORMAL", "reason": None},
            {
                "id": snapshot["id"],
                "fsid": self.fsid,
                "osdmap_epoch": 42,
                "captured_at": snapshot["captured_at"],
                "fresh": True,
                "cluster_health_summary": {
                    "status": "HEALTH_OK",
                    "capacity_scope_complete": True,
                },
            },
            [
                {
                    "osd_id": 0,
                    "total_bytes": 1000,
                    "used_bytes": 650,
                    "available_bytes": 350,
                    "used_ratio": 0.65,
                    "is_up": True,
                    "is_in": True,
                    "host": "host-a",
                    "device_class": "hdd",
                    "scope_metadata": {
                        "eligible_pools": ["rgw.data"],
                        "pool_ids": {"rgw.data": 7},
                        "capacity_scope_complete": True,
                    },
                }
            ],
        )

    def tearDown(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            conn.execute(
                """
                DELETE FROM capacity_reservation_allocations
                 WHERE reservation_id IN (
                   SELECT id FROM capacity_reservations
                    WHERE decision_id IN (
                      SELECT id FROM capacity_decisions WHERE request_id=ANY(%s)
                    )
                 )
                """,
                (self.requests,),
            )
            conn.execute(
                """DELETE FROM capacity_reservations WHERE decision_id IN (
                       SELECT id FROM capacity_decisions WHERE request_id=ANY(%s)
                     )""",
                (self.requests,),
            )
            conn.execute("DELETE FROM capacity_decisions WHERE request_id=ANY(%s)", (self.requests,))
            conn.execute("DELETE FROM capacity_snapshots WHERE fsid=%s", (self.fsid,))

    def test_fsid_lock_and_pending_allocations_prevent_overbooking(self):
        def attempt(request_id: str):
            try:
                return require_admission(
                    "PUT",
                    20,
                    request_id=request_id,
                    affected_pools=["rgw.data"],
                )
            except CapacityRejected as exc:
                return exc

        with (
            patch.object(capacity_guard, "get_settings", return_value=self.settings),
            patch.object(
                capacity_guard,
                "_load_control_and_snapshot",
                return_value=self.snapshot_telemetry,
            ),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(attempt, self.requests))

        admitted = [item for item in outcomes if not isinstance(item, CapacityRejected)]
        blocked = [item for item in outcomes if isinstance(item, CapacityRejected)]
        diagnostics = [
            item.decision.to_dict() if isinstance(item, CapacityRejected) else item.to_dict()
            for item in outcomes
        ]
        self.assertEqual(len(admitted), 1, diagnostics)
        self.assertEqual(len(blocked), 1, diagnostics)
        self.assertIsNotNone(admitted[0].reservation_id)
        self.assertEqual(blocked[0].decision.state, "PAUSED_CAPACITY")

        with psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row) as conn:
            reservation_count = conn.execute(
                """SELECT count(*) AS count FROM capacity_reservations
                     WHERE decision_id IN (
                       SELECT id FROM capacity_decisions WHERE request_id=ANY(%s)
                     )""",
                (self.requests,),
            ).fetchone()["count"]
        self.assertEqual(reservation_count, 1)


if __name__ == "__main__":
    unittest.main()
