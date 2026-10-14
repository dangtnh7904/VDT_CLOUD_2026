from __future__ import annotations

import unittest

from app.config import Settings
from app.modules.sessions.domain import CreateSessionCommand, SessionError
from app.modules.sessions.service import SessionService


FSID = "11111111-2222-3333-4444-555555555555"


class FakeObservations:
    def __init__(self, fsid=FSID):
        self.fsid = fsid

    def identity(self):
        return {"fsid": self.fsid, "observed_at": "2026-10-08T00:00:00Z"}

    def capabilities(self):
        return {
            "fsid": self.fsid,
            "collected_at": "2026-10-08T00:00:00Z",
            "executor_version": "1.0.0",
            "protocol_version": 1,
            "actions": [
                "ceph.fsid",
                "ceph.status",
                "ceph.osd_df",
                "ceph.osd_tree",
                "ceph.pool_ls_detail",
            ],
        }

    def inventory(self):
        raise AssertionError("session creation must not collect inventory")


class MemoryRepository:
    def __init__(self):
        self.rows = {}

    def create(self, **values):
        session_id = values["session_id"]
        command = values["command"]
        snapshot = values["snapshot"]
        row = {
            "id": str(session_id),
            "cluster_id": snapshot.cluster_id,
            "fsid": values["actual_fsid"],
            "config_snapshot_id": str(snapshot.id),
            "config_hash": snapshot.config_hash,
            "name": command.name,
            "workflows": list(command.workflow_types),
        }
        self.rows[session_id] = row
        return row

    def get(self, session_id):
        return self.rows.get(session_id)


def settings(**overrides):
    values = {
        "feature_legacy_rgw": False,
        "feature_legacy_rbd": False,
        "feature_upgrade": True,
        "feature_lab": False,
        "cluster_id": "lab-a",
        "cluster_profile_revision": "lab-a-v1",
        "ceph_expected_fsid": FSID,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class SessionServiceTests(unittest.TestCase):
    def test_production_only_session_does_not_require_qos_or_lab(self):
        repository = MemoryRepository()
        service = SessionService(settings(), FakeObservations(), repository)

        result = service.create(
            CreateSessionCommand("PA1 canary", ("UPGRADE_PRODUCTION",))
        )

        self.assertEqual(result["cluster_id"], "lab-a")
        self.assertEqual(result["fsid"], FSID)
        self.assertEqual(result["workflows"], ["UPGRADE_PRODUCTION"])
        self.assertEqual(len(result["config_hash"]), 64)

    def test_disabled_optional_workflow_is_rejected_without_blocking_production(self):
        service = SessionService(settings(), FakeObservations(), MemoryRepository())

        with self.assertRaisesRegex(SessionError, "QOS_OBSERVER"):
            service.create(
                CreateSessionCommand(
                    "invalid optional request",
                    ("UPGRADE_PRODUCTION", "QOS_OBSERVER"),
                )
            )

    def test_actual_fsid_mismatch_blocks_before_persistence(self):
        repository = MemoryRepository()
        service = SessionService(
            settings(),
            FakeObservations("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            repository,
        )

        with self.assertRaisesRegex(SessionError, "actual cluster FSID"):
            service.create(CreateSessionCommand("wrong cluster", ("UPGRADE_PRODUCTION",)))
        self.assertEqual(repository.rows, {})


if __name__ == "__main__":
    unittest.main()
