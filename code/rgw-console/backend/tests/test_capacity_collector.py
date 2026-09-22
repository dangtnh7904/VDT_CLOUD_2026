import os
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


os.environ.setdefault("RGW_ENDPOINT_URL", "http://127.0.0.1:8080")
os.environ.setdefault("RGW_ACCESS_KEY", "unit-test")
os.environ.setdefault("RGW_SECRET_KEY", "unit-test")

from app.services.capacity_collector import (  # noqa: E402
    CapacityTelemetryError,
    collect_capacity_once,
    evaluate_settlement_evidence,
    parse_ceph_inventory,
    store_capacity_inventory,
)


FSID = "11111111-2222-3333-4444-555555555555"


def status(epoch=42, *, pg_state="active+clean", health_status="HEALTH_OK", checks=None):
    return {
        "fsid": FSID,
        "health": {"status": health_status, "checks": checks or {}},
        "osdmap": {
            "epoch": epoch,
            "num_osds": 3,
            "num_up_osds": 3,
            "num_in_osds": 3,
            "num_remapped_pgs": 0,
        },
        "pgmap": {"pgs_by_state": [{"state_name": pg_state, "count": 32}]},
    }


def osd_df():
    nodes = []
    for osd_id, used in enumerate((100, 200, 300)):
        nodes.append(
            {
                "id": osd_id,
                "name": f"osd.{osd_id}",
                "type": "osd",
                "kb": 1000,
                "kb_used": used,
                "kb_avail": 1000 - used,
                "utilization": used / 10,
                "status": "up",
                "reweight": 1.0,
                "device_class": "ssd" if osd_id == 2 else "hdd",
            }
        )
    return {"nodes": nodes, "stray": []}


def osd_tree():
    return {
        "nodes": [
            {"id": -1, "name": "default", "type": "root", "children": [-3, -5, -7]},
            {"id": -3, "name": "host-a", "type": "host", "children": [0]},
            {"id": -5, "name": "host-b", "type": "host", "children": [1]},
            {"id": -7, "name": "host-c", "type": "host", "children": [2]},
            {
                "id": 0,
                "name": "osd.0",
                "type": "osd",
                "status": "up",
                "reweight": 1.0,
                "device_class": "hdd",
            },
            {
                "id": 1,
                "name": "osd.1",
                "type": "osd",
                "status": "up",
                "reweight": 1.0,
                "device_class": "hdd",
            },
            {
                "id": 2,
                "name": "osd.2",
                "type": "osd",
                "status": "up",
                "reweight": 1.0,
                "device_class": "ssd",
            },
        ],
        "stray": [],
    }


def pools():
    return [
        {
            "pool": 7,
            "pool_name": "rgw.data",
            "type": 1,
            "type_name": "replicated",
            "size": 3,
            "min_size": 2,
            "crush_rule": 0,
        },
        {
            "pool": 8,
            "pool_name": "ssd.data",
            "type": 1,
            "type_name": "replicated",
            "size": 1,
            "min_size": 1,
            "crush_rule": 1,
        },
    ]


def rules():
    return [
        {
            "rule_id": 0,
            "rule_name": "replicated_rule",
            "type": 1,
            "steps": [
                {"op": "take", "item": -1, "item_name": "default"},
                {"op": "chooseleaf_firstn", "num": 0, "type": "host"},
                {"op": "emit"},
            ],
        },
        {
            "rule_id": 1,
            "rule_name": "ssd_rule",
            "type": 1,
            "steps": [
                {"op": "take", "item": -1, "item_name": "default~ssd"},
                {"op": "chooseleaf_firstn", "num": 0, "type": "host"},
                {"op": "emit"},
            ],
        },
    ]


def parse(*, affected=("rgw.data",), before=None, after=None, df=None):
    return parse_ceph_inventory(
        fsid=FSID,
        status_before=before or status(),
        status_after=after or status(),
        osd_df=df or osd_df(),
        osd_tree=osd_tree(),
        pool_details=pools(),
        crush_rules=rules(),
        affected_pools=affected,
        captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class CapacityParserTests(unittest.TestCase):
    def test_parses_pacific_osd_bytes_hosts_and_replicated_scope(self):
        inventory = parse()

        self.assertTrue(inventory.fresh)
        self.assertEqual(inventory.osdmap_epoch, 42)
        self.assertEqual([row.host for row in inventory.osds], ["host-a", "host-b", "host-c"])
        self.assertEqual(inventory.osds[0].total_bytes, 1000 * 1024)
        self.assertEqual(inventory.osds[2].used_bytes, 300 * 1024)
        self.assertAlmostEqual(inventory.osds[2].used_ratio, 0.3)
        for row in inventory.osds:
            self.assertEqual(row.scope_metadata["eligible_pools"], ["rgw.data"])
            self.assertEqual(row.scope_metadata["pool_ids"], {"rgw.data": 7})
            self.assertEqual(row.scope_metadata["pool_replication_sizes"], {"rgw.data": 3})
            self.assertTrue(row.scope_metadata["capacity_scope_complete"])
        self.assertTrue(inventory.cluster_health_summary["capacity_scope_complete"])

    def test_device_class_rule_excludes_other_osds(self):
        inventory = parse(affected=("ssd.data",))

        self.assertEqual(inventory.osds[0].scope_metadata["eligible_pools"], [])
        self.assertEqual(inventory.osds[1].scope_metadata["eligible_pools"], [])
        self.assertEqual(inventory.osds[2].scope_metadata["eligible_pools"], ["ssd.data"])

    def test_unknown_pool_is_visible_but_scope_stays_fail_closed(self):
        inventory = parse(affected=("missing.pool",))

        self.assertTrue(inventory.fresh)
        self.assertFalse(inventory.cluster_health_summary["capacity_scope_complete"])
        self.assertEqual(
            inventory.cluster_health_summary["scope_errors"],
            [{"pool": "missing.pool", "code": "UNKNOWN_POOL"}],
        )
        self.assertTrue(
            all(not row.scope_metadata["capacity_scope_complete"] for row in inventory.osds)
        )

    def test_erasure_coded_pool_is_not_accepted_as_mvp_scope(self):
        ec_pools = pools()
        ec_pools[0]["type"] = 3
        ec_pools[0]["type_name"] = "erasure"
        inventory = parse_ceph_inventory(
            fsid=FSID,
            status_before=status(),
            status_after=status(),
            osd_df=osd_df(),
            osd_tree=osd_tree(),
            pool_details=ec_pools,
            crush_rules=rules(),
            affected_pools={"rgw.data"},
        )

        self.assertFalse(inventory.cluster_health_summary["capacity_scope_complete"])
        self.assertEqual(
            inventory.cluster_health_summary["scope_errors"][0]["code"],
            "UNSUPPORTED_POOL_TYPE",
        )

    def test_epoch_change_during_collection_is_rejected(self):
        with self.assertRaisesRegex(CapacityTelemetryError, "epoch changed"):
            parse(before=status(42), after=status(43))

    def test_missing_or_inconsistent_capacity_is_rejected_not_zero_filled(self):
        missing = osd_df()
        del missing["nodes"][0]["kb_used"]
        with self.assertRaises(CapacityTelemetryError):
            parse(df=missing)

        inconsistent = osd_df()
        inconsistent["nodes"][0]["kb_avail"] = 950
        with self.assertRaisesRegex(CapacityTelemetryError, "inconsistent"):
            parse(df=inconsistent)

    def test_status_counts_must_match_per_osd_rows(self):
        after = status()
        after["osdmap"]["num_up_osds"] = 2
        with self.assertRaisesRegex(CapacityTelemetryError, "counts differ"):
            parse(after=after)

    def test_pg_recovery_and_full_health_are_preserved_as_blocking_flags(self):
        after = status(
            pg_state="active+undersized+degraded+remapped+backfilling",
            health_status="HEALTH_WARN",
            checks={"OSD_BACKFILLFULL": {"severity": "HEALTH_WARN"}},
        )
        inventory = parse(after=after)

        summary = inventory.cluster_health_summary
        self.assertTrue(summary["degraded"])
        self.assertTrue(summary["remapped"])
        self.assertTrue(summary["backfilling"])
        self.assertTrue(summary["backfillfull"])
        self.assertTrue(all(row.scope_metadata["backfillfull"] for row in inventory.osds))


class FakeAgent:
    expected_fsid = FSID

    def __init__(self, timestamp):
        self.timestamp = timestamp
        self.calls = []
        self._status_calls = 0

    def _result(self, action, data):
        self.calls.append(action)
        return {
            "fsid": FSID,
            "action": action,
            "data": deepcopy(data),
            "collected_at": self.timestamp.isoformat(),
        }

    def ceph_status(self):
        self._status_calls += 1
        return self._result("ceph.status", status())

    def ceph_osd_df(self):
        return self._result("ceph.osd_df", osd_df())

    def ceph_osd_tree(self):
        return self._result("ceph.osd_tree", osd_tree())

    def ceph_pool_ls_detail(self):
        return self._result("ceph.pool_ls_detail", pools())

    def ceph_crush_rule_dump(self):
        return self._result("ceph.crush_rule_dump", rules())


class CollectorOrchestrationTests(unittest.TestCase):
    def test_collector_uses_only_read_only_inventory_actions(self):
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        agent = FakeAgent(timestamp)
        stored = []
        times = iter((timestamp, timestamp + timedelta(seconds=1)))
        settings = SimpleNamespace(
            ceph_expected_fsid=FSID,
            rgw_affected_pool_set=frozenset({"rgw.data"}),
            rbd_allowed_pool_set=frozenset(),
            capacity_metrics_max_age_seconds=5,
        )

        with patch("app.services.capacity_collector.get_settings", return_value=settings):
            result = collect_capacity_once(
                client=agent,
                store=lambda inventory: stored.append(inventory) or {"snapshot_id": 9},
                now=lambda: next(times),
            )

        self.assertEqual(result, {"snapshot_id": 9})
        self.assertEqual(
            agent.calls,
            [
                "ceph.status",
                "ceph.osd_df",
                "ceph.osd_tree",
                "ceph.pool_ls_detail",
                "ceph.crush_rule_dump",
                "ceph.status",
            ],
        )
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0].fresh)

    def test_stale_agent_timestamps_create_invalid_not_zero_sample(self):
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        agent = FakeAgent(timestamp - timedelta(seconds=30))
        stored = []
        times = iter((timestamp, timestamp + timedelta(seconds=1)))
        settings = SimpleNamespace(
            ceph_expected_fsid=FSID,
            rgw_affected_pool_set=frozenset({"rgw.data"}),
            rbd_allowed_pool_set=frozenset(),
            capacity_metrics_max_age_seconds=5,
        )

        with patch("app.services.capacity_collector.get_settings", return_value=settings):
            collect_capacity_once(
                client=agent,
                store=lambda inventory: stored.append(inventory) or {},
                now=lambda: next(times),
            )

        self.assertFalse(stored[0].fresh)
        self.assertEqual(stored[0].cluster_health_summary["collector_error_code"], "STALE_OR_FUTURE_AGENT_TELEMETRY")
        self.assertEqual(len(stored[0].osds), 3)


class SettlementEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.settled = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.now = self.settled + timedelta(seconds=20)
        self.reservation = {
            "fsid": FSID,
            "osdmap_epoch": 42,
            "settled_at": self.settled,
        }
        self.samples = [
            {
                "fsid": FSID,
                "osdmap_epoch": 42,
                "captured_at": self.now - timedelta(seconds=offset),
                "fresh": True,
                "scope_complete": True,
                "health_safe": True,
            }
            for offset in (1, 3, 5)
        ]

    def evaluate(self, samples=None):
        return evaluate_settlement_evidence(
            self.reservation,
            self.samples if samples is None else samples,
            now=self.now,
            required_samples=3,
            minimum_seconds=10,
            maximum_age_seconds=5,
        )

    def test_releases_only_after_fresh_consecutive_stable_scope_samples(self):
        sufficient, reason = self.evaluate()
        self.assertTrue(sufficient, reason)

    def test_insufficient_invalid_or_changed_epoch_evidence_keeps_charge(self):
        self.assertFalse(self.evaluate(self.samples[:2])[0])
        for field, value in (
            ("fresh", False),
            ("scope_complete", False),
            ("health_safe", False),
            ("osdmap_epoch", 43),
        ):
            samples = deepcopy(self.samples)
            samples[1][field] = value
            with self.subTest(field=field):
                self.assertFalse(self.evaluate(samples)[0])

    def test_stale_latest_sample_or_short_window_keeps_charge(self):
        stale = deepcopy(self.samples)
        for sample in stale:
            sample["captured_at"] -= timedelta(seconds=10)
        self.assertFalse(self.evaluate(stale)[0])

        early_now = self.settled + timedelta(seconds=5)
        sufficient, _ = evaluate_settlement_evidence(
            self.reservation,
            self.samples,
            now=early_now,
            required_samples=3,
            minimum_seconds=10,
            maximum_age_seconds=5,
        )
        self.assertFalse(sufficient)


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "set TEST_DATABASE_URL to run PostgreSQL collector persistence tests",
)
class CapacityPersistenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row)
        # Start an outer transaction. store_capacity_inventory uses a nested
        # transaction/savepoint, and tearDown rolls the complete test fixture back.
        self.conn.execute("SELECT 1")

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def test_inventory_and_per_osd_rows_are_stored_atomically(self):
        inventory = replace(
            parse(),
            fsid=str(uuid4()),
            captured_at=datetime.now(timezone.utc),
        )

        result = store_capacity_inventory(inventory, db_conn=self.conn)

        snapshot = self.conn.execute(
            "SELECT * FROM capacity_snapshots WHERE id=%s",
            (result["snapshot_id"],),
        ).fetchone()
        rows = self.conn.execute(
            "SELECT * FROM capacity_osds WHERE snapshot_id=%s ORDER BY osd_id",
            (result["snapshot_id"],),
        ).fetchall()
        self.assertEqual(snapshot["fsid"], inventory.fsid)
        self.assertTrue(snapshot["fresh"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["scope_metadata"]["pool_ids"], {"rgw.data": 7})
        self.assertEqual(result["osd_count"], 3)


if __name__ == "__main__":
    unittest.main()
