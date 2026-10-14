from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from app.modules.upgrade_common.domain import (
    BatchParameters,
    DryRunPlanner,
    Pa2EndState,
    Strategy,
    UpgradeBatchSpec,
    UpgradeDomainError,
    UpgradeRunSpec,
    UpgradeSafetyGate,
    evaluate_inventory_binding,
)
from app.platform.evidence import FilesystemArtifactStore


FSID = "11111111-2222-3333-4444-555555555555"
DIGEST = "sha256:" + "a" * 64


def parameters(**overrides):
    values = {
        "batch_size": 2,
        "drain_parallelism": 1,
        "max_simultaneous_down": 1,
        "return_parallelism": 1,
        "scrub_concurrency": 1,
        "promotion_parallelism": 1,
        "chain_parallelism": 1,
        "handoff_parallelism": 1,
        "max_pg_per_handoff_group": 32,
        "max_bytes_per_handoff_group": 1024 * 1024 * 1024,
    }
    values.update(overrides)
    return BatchParameters(**values)


def batch(**overrides):
    values = {
        "name": "canary",
        "source_osds": (0,),
        "destination_osds": (2,),
        "parameters": parameters(),
    }
    values.update(overrides)
    return UpgradeBatchSpec(**values)


def inventory(**overrides):
    value = {
        "fsid": FSID,
        "quality": "VALID",
        "health": "HEALTH_OK",
        "osdmap_epoch": 42,
        "osds": [
            {"osd_id": 0, "host": "host-a", "up": True, "in": True, "allowed": True},
            {"osd_id": 2, "host": "host-b", "up": True, "in": True, "allowed": True},
        ],
        "pools": [
            {"name": "rbd-lab", "type": "replicated", "size": 3, "min_size": 2, "allowed": True}
        ],
    }
    value.update(overrides)
    return value


def capabilities(state="SUPPORTED"):
    return {
        "capabilities": {
            name: state for name in DryRunPlanner.REQUIRED_LIVE_CAPABILITIES
        }
    }


def binding_context():
    return {
        "cluster_id": "lab-a",
        "fsid": FSID,
        "session_id": "11111111-1111-4111-8111-111111111111",
        "config_snapshot_id": "22222222-2222-4222-8222-222222222222",
        "source_osds": [0],
        "destination_osds": [2],
    }


def info_collection(now: datetime, **overrides):
    value = {
        "id": "33333333-3333-4333-8333-333333333333",
        "cluster_id": "lab-a",
        "fsid": FSID,
        "session_id": "11111111-1111-4111-8111-111111111111",
        "config_snapshot_id": "22222222-2222-4222-8222-222222222222",
        "phase": "BEFORE",
        "state": "COMPLETE",
        "quality": "VALID",
        "artifact_sha256": "a" * 64,
        "collected_at": now.isoformat(),
        "osds": [
            {"osd_id": 0, "quality": "VALID"},
            {"osd_id": 2, "quality": "VALID"},
        ],
    }
    value.update(overrides)
    return value


class UpgradeDomainTests(unittest.TestCase):
    def test_fresh_complete_before_snapshot_is_ready_for_plan_binding(self):
        now = datetime(2026, 10, 8, tzinfo=timezone.utc)

        decision = evaluate_inventory_binding(
            binding_context(),
            info_collection(now - timedelta(seconds=10)),
            now=now,
            max_age_seconds=45,
        )

        self.assertEqual(decision.result, "READY")
        self.assertEqual(decision.reasons, ())
        self.assertEqual(decision.observed["required_osd_ids"], [0, 2])

    def test_stale_bound_snapshot_becomes_hold(self):
        now = datetime(2026, 10, 8, tzinfo=timezone.utc)

        decision = evaluate_inventory_binding(
            binding_context(),
            info_collection(now - timedelta(seconds=46)),
            now=now,
            max_age_seconds=45,
        )

        self.assertEqual(decision.result, "HOLD")
        self.assertIn("INVENTORY_STALE", decision.reasons)

    def test_wrong_fsid_and_missing_plan_osd_fail_closed(self):
        now = datetime(2026, 10, 8, tzinfo=timezone.utc)
        collection = info_collection(
            now,
            fsid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            osds=[{"osd_id": 0, "quality": "VALID"}],
        )

        decision = evaluate_inventory_binding(
            binding_context(),
            collection,
            now=now,
            max_age_seconds=45,
        )

        self.assertEqual(decision.result, "BLOCKED")
        self.assertIn("FSID_MISMATCH", decision.reasons)
        self.assertIn("PLAN_OSD_SCOPE_MISSING", decision.reasons)

    def test_pa2_requires_explicit_end_state(self):
        with self.assertRaisesRegex(UpgradeDomainError, "explicit end state"):
            UpgradeRunSpec(Strategy.PA2, "17.2.7", DIGEST)

    def test_pa1_rejects_pa2_end_state(self):
        with self.assertRaisesRegex(UpgradeDomainError, "must not define"):
            UpgradeRunSpec(Strategy.PA1, "17.2.7", DIGEST, Pa2EndState.KEEP_ROTATED)

    def test_batch_rejects_source_destination_overlap(self):
        with self.assertRaisesRegex(UpgradeDomainError, "must not overlap"):
            batch(destination_osds=(0,))

    def test_dry_run_can_pass_while_live_execution_remains_blocked(self):
        plan = DryRunPlanner().build(
            batch(),
            UpgradeRunSpec(Strategy.PA1, "17.2.7", DIGEST),
            inventory=inventory(),
            capabilities=capabilities("UNSUPPORTED"),
            expected_fsid=FSID,
        )

        self.assertEqual(plan.dry_run_result, "PASS")
        self.assertEqual(plan.execution_readiness, "BLOCKED")
        self.assertTrue(plan.warnings)
        self.assertEqual(plan.steps[0]["would_mutate"], False)
        self.assertIn("NO_CLUSTER_MUTATION_IN_DRY_RUN", plan.invariants)

    def test_fsid_and_inventory_quality_fail_closed(self):
        plan = DryRunPlanner().build(
            batch(),
            UpgradeRunSpec(Strategy.PA1, "17.2.7", DIGEST),
            inventory=inventory(fsid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", quality="GAP"),
            capabilities=capabilities(),
            expected_fsid=FSID,
        )

        self.assertEqual(plan.dry_run_result, "BLOCKED")
        self.assertIn("FSID_MISMATCH", plan.blockers)
        self.assertIn("INVENTORY_INCONCLUSIVE", plan.blockers)

    def test_erasure_coded_pool_is_explicitly_unsupported(self):
        raw = inventory()
        raw["pools"][0]["type"] = "erasure"

        plan = DryRunPlanner().build(
            batch(),
            UpgradeRunSpec(Strategy.PA1, "17.2.7", DIGEST),
            inventory=raw,
            capabilities=capabilities(),
            expected_fsid=FSID,
        )

        self.assertIn("UNSUPPORTED_POOL_TYPE:rbd-lab", plan.blockers)

    def test_safety_gate_blocks_pool_without_failure_headroom(self):
        raw = inventory()
        raw["pools"][0]["min_size"] = 3

        decision = UpgradeSafetyGate().evaluate(
            batch(),
            inventory=raw,
            expected_fsid=FSID,
        )

        self.assertEqual(decision.result, "BLOCKED")
        self.assertIn("POOL_NO_FAILURE_HEADROOM:rbd-lab", decision.blockers)

    def test_pa2_plan_rotates_source_into_next_spare(self):
        plan = DryRunPlanner().build(
            batch(source_osds=(0, 1), destination_osds=(2,)),
            UpgradeRunSpec(
                Strategy.PA2,
                "17.2.7",
                DIGEST,
                Pa2EndState.RECONCILE,
            ),
            inventory=inventory(
                osds=[
                    {"osd_id": 0, "host": "host-a", "up": True, "in": True, "allowed": True},
                    {"osd_id": 1, "host": "host-c", "up": True, "in": True, "allowed": True},
                    {"osd_id": 2, "host": "host-b", "up": True, "in": True, "allowed": True},
                ]
            ),
            capabilities=capabilities(),
            expected_fsid=FSID,
        )

        resources = [step["resource"] for step in plan.steps]
        self.assertIn("osd.0->osd.2", resources)
        self.assertIn("osd.1->osd.0", resources)
        self.assertIn("RECONCILE_TO_POLICY", resources)


class ArtifactStoreTests(unittest.TestCase):
    def test_json_artifact_is_append_only_hashed_and_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            store = FilesystemArtifactStore(Path(root), max_artifact_bytes=1024)
            artifact = store.put_json(
                {"result": "NOT_EXERCISED"},
                cluster_id="lab-a",
                session_id=UUID("11111111-1111-4111-8111-111111111111"),
                run_id=UUID("22222222-2222-4222-8222-222222222222"),
            )

            self.assertEqual(len(artifact.sha256), 64)
            self.assertTrue(artifact.uri.startswith("filesystem:lab-a/"))
            self.assertEqual(len(list(Path(root).rglob("*.json"))), 1)
            self.assertEqual(
                store.read_json(
                    artifact.uri,
                    expected_sha256=artifact.sha256,
                    expected_size_bytes=artifact.size_bytes,
                ),
                {"result": "NOT_EXERCISED"},
            )

    def test_oversized_artifact_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as root:
            store = FilesystemArtifactStore(Path(root), max_artifact_bytes=8)

            with self.assertRaisesRegex(ValueError, "exceeds"):
                store.put_json(
                    {"payload": "too large"},
                    cluster_id="lab-a",
                    session_id=UUID("11111111-1111-4111-8111-111111111111"),
                    run_id=UUID("22222222-2222-4222-8222-222222222222"),
                )
            self.assertEqual(list(Path(root).rglob("*.json")), [])

    def test_read_rejects_tampered_or_escaped_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            store = FilesystemArtifactStore(Path(root), max_artifact_bytes=1024)
            artifact = store.put_json(
                {"result": "READY"},
                cluster_id="lab-a",
                session_id=UUID("11111111-1111-4111-8111-111111111111"),
                run_id=UUID("22222222-2222-4222-8222-222222222222"),
            )
            target = Path(root) / artifact.uri.removeprefix("filesystem:")
            target.write_bytes(target.read_bytes().replace(b"READY", b"ERROR"))

            with self.assertRaisesRegex(ValueError, "SHA-256"):
                store.read_json(
                    artifact.uri,
                    expected_sha256=artifact.sha256,
                    expected_size_bytes=artifact.size_bytes,
                )
            with self.assertRaisesRegex(ValueError, "escaped"):
                store.read_json(
                    "filesystem:../../outside.json",
                    expected_sha256="0" * 64,
                    expected_size_bytes=0,
                )


if __name__ == "__main__":
    unittest.main()
