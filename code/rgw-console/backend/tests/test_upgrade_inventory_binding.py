from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.config import Settings
from app.modules.upgrade_common.service import (
    InventoryBindingEnvelope,
    UpgradeApplicationError,
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
    def __init__(self, context, binding=None):
        self.context = context
        self.binding = binding
        self.bind_calls = []

    def get_run_context(self, run_id):
        return self.context

    def bind_inventory(self, **kwargs):
        self.bind_calls.append(kwargs)
        return {"id": str(uuid4()), "readiness_result": "READY", "replayed": False}

    def get_inventory_binding(self, **kwargs):
        return self.binding


class UpgradeInventoryBindingServiceTests(unittest.TestCase):
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
        config_hash = build_config_snapshot(self.settings).config_hash
        self.context = {
            "id": str(self.run_id),
            "cluster_id": "lab-a",
            "fsid": FSID,
            "session_id": str(self.session_id),
            "config_snapshot_id": str(self.snapshot_id),
            "config_hash": config_hash,
            "state": "CREATED",
            "plan_revision": 1,
            "resource_version": 1,
            "source_osds": [0],
            "destination_osds": [2],
        }

    def collection(self, *, age_seconds=5):
        return {
            "id": str(self.collection_id),
            "cluster_id": "lab-a",
            "fsid": FSID,
            "session_id": str(self.session_id),
            "config_snapshot_id": str(self.snapshot_id),
            "phase": "BEFORE",
            "state": "COMPLETE",
            "quality": "VALID",
            "artifact_sha256": "a" * 64,
            "collected_at": (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat(),
            "osds": [
                {"osd_id": 0, "quality": "VALID"},
                {"osd_id": 2, "quality": "VALID"},
            ],
        }

    def envelope(self):
        return InventoryBindingEnvelope(
            collection_id=self.collection_id,
            expected_state="CREATED",
            plan_revision=1,
            config_snapshot_id=self.snapshot_id,
            resource_version=1,
            reason="operator selected BEFORE baseline",
        )

    def test_ready_snapshot_is_forwarded_to_atomic_repository_binding(self):
        repository = FakeUpgradeRepository(self.context)
        service = UpgradeApplicationService(
            self.settings,
            repository,
            inventory_query=FakeInventoryQuery(self.collection()),
        )

        result = service.bind_inventory(
            run_id=self.run_id,
            envelope=self.envelope(),
            idempotency_key="bind-baseline-0001",
        )

        self.assertEqual(result["readiness_result"], "READY")
        self.assertEqual(len(repository.bind_calls), 1)
        self.assertEqual(repository.bind_calls[0]["decision"]["result"], "READY")

    def test_stale_snapshot_is_rejected_before_repository_write(self):
        repository = FakeUpgradeRepository(self.context)
        service = UpgradeApplicationService(
            self.settings,
            repository,
            inventory_query=FakeInventoryQuery(self.collection(age_seconds=46)),
        )

        with self.assertRaises(UpgradeApplicationError) as raised:
            service.bind_inventory(
                run_id=self.run_id,
                envelope=self.envelope(),
                idempotency_key="bind-baseline-0002",
            )

        self.assertEqual(raised.exception.code, "INVENTORY_BINDING_NOT_READY")
        self.assertEqual(raised.exception.observed_state["result"], "HOLD")
        self.assertEqual(repository.bind_calls, [])

    def test_unbound_run_is_inconclusive_not_ready(self):
        service = UpgradeApplicationService(
            self.settings,
            FakeUpgradeRepository(self.context),
            inventory_query=FakeInventoryQuery(self.collection()),
        )

        result = service.inventory_readiness(self.run_id)

        self.assertEqual(result["result"], "INCONCLUSIVE")
        self.assertIn("OSD_INFO_BASELINE_NOT_BOUND", result["reasons"])
        self.assertIsNone(result["binding"])


if __name__ == "__main__":
    unittest.main()
