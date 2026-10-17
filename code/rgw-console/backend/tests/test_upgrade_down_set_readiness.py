from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config import Settings
from app.modules.upgrade_common.service import (
    DownSetInventoryEnvelope,
    UpgradeApplicationService,
)
from app.platform.config import build_config_snapshot


FSID = "11111111-2222-4333-8444-555555555555"


class FakeInventoryQuery:
    def __init__(self, collection):
        self.collection = collection
        self.calls = []

    def get_collection(self, collection_id):
        self.calls.append(collection_id)
        return self.collection


class FakeUpgradeRepository:
    def __init__(self, context):
        self.context = context

    def get_run_context(self, run_id):
        return self.context


class UpgradeDownSetReadinessTests(unittest.TestCase):
    def setUp(self):
        self.run_id = uuid4()
        self.session_id = uuid4()
        self.snapshot_id = uuid4()
        self.collection_id = uuid4()
        self.settings = Settings(
            _env_file=None,
            feature_legacy_rgw=False,
            feature_legacy_rbd=False,
            feature_upgrade=True,
            cluster_id="lab-a",
            ceph_expected_fsid=FSID,
            upgrade_allowed_osds="0,2",
            upgrade_inventory_max_age_seconds=45,
        )
        self.context = {
            "id": str(self.run_id),
            "cluster_id": "lab-a",
            "fsid": FSID,
            "session_id": str(self.session_id),
            "config_snapshot_id": str(self.snapshot_id),
            "config_hash": build_config_snapshot(self.settings).config_hash,
            "state": "CREATED",
            "plan_revision": 3,
            "resource_version": 5,
            "source_osds": [0],
            "destination_osds": [2],
            "parameters": {"max_simultaneous_down": 1},
        }

    def collection(self, **overrides):
        value = {
            "id": str(self.collection_id),
            "cluster_id": "lab-a",
            "fsid": FSID,
            "session_id": str(self.session_id),
            "config_snapshot_id": str(self.snapshot_id),
            "phase": "DURING",
            "state": "COMPLETE",
            "quality": "VALID",
            "artifact_sha256": "c" * 64,
            "requested_osd_ids": [0, 2],
            "collected_at": (
                datetime.now(timezone.utc) - timedelta(seconds=5)
            ).isoformat(),
            "osds": [
                {"osd_id": 0, "quality": "VALID", "up": True, "in": True},
                {"osd_id": 2, "quality": "VALID", "up": True, "in": True},
            ],
        }
        value.update(overrides)
        return value

    def envelope(self, **overrides):
        value = {
            "collection_id": self.collection_id,
            "target_osd_ids": (0,),
            "expected_state": "CREATED",
            "plan_revision": 3,
            "config_snapshot_id": self.snapshot_id,
            "resource_version": 5,
        }
        value.update(overrides)
        return DownSetInventoryEnvelope(**value)

    def service(self, collection=None):
        return UpgradeApplicationService(
            self.settings,
            FakeUpgradeRepository(self.context),
            inventory_query=FakeInventoryQuery(collection or self.collection()),
        )

    def test_fresh_persisted_snapshot_is_inventory_ready_but_mutation_blocked(self):
        result = self.service().assess_down_set_inventory(
            run_id=self.run_id,
            envelope=self.envelope(),
        )

        self.assertEqual(result["inventory_result"], "READY")
        self.assertEqual(result["mutation_readiness"], "BLOCKED")
        self.assertEqual(result["target_osd_ids"], [0])
        self.assertIn("PG_UP_ACTING_RECHECK_REQUIRED", result["limitations"])

    def test_stale_resource_version_returns_blocked_decision(self):
        result = self.service().assess_down_set_inventory(
            run_id=self.run_id,
            envelope=self.envelope(resource_version=4),
        )

        self.assertEqual(result["inventory_result"], "BLOCKED")
        self.assertEqual(result["reasons"], ["RESOURCE_VERSION_CHANGED"])

    def test_unknown_up_state_remains_inconclusive(self):
        collection = self.collection()
        collection["osds"][1]["up"] = None

        result = self.service(collection).assess_down_set_inventory(
            run_id=self.run_id,
            envelope=self.envelope(),
        )

        self.assertEqual(result["inventory_result"], "INCONCLUSIVE")
        self.assertEqual(result["reasons"], ["OSD_UP_IN_STATE_UNKNOWN"])


if __name__ == "__main__":
    unittest.main()
