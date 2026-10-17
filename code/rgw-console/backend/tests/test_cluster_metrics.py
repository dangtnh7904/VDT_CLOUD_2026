from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.modules.cluster_metrics.api import router
from app.modules.cluster_metrics.normalization import normalize, samples
from app.modules.cluster_metrics.service import ACTIONS, ClusterMetricsService, CollectionError
from app.services.executor_client import ExecutorClientError


FSID = "11111111-2222-3333-4444-555555555555"


class MemoryRepository:
    def __init__(self):
        self.rows = {}

    def get(self, collection_id, **identity):
        row = self.rows.get(collection_id)
        return row if row and all(row[key] == value for key, value in identity.items()) else None

    def list(self, **kwargs):
        return []

    def save(self, collection_id, *, artifact, payload, request_hash, actor):
        self.rows.setdefault(collection_id, {"cluster_id": payload["cluster_id"], "fsid": payload["fsid"],
            "uri": artifact.uri, "sha256": artifact.sha256, "size_bytes": artifact.size_bytes,
            "metadata": {"request_hash": request_hash, "actor": actor}})


class FakeClient:
    def __init__(self):
        self.calls = []
        self.fsid = FSID
        self.fail = set()

    def capabilities(self):
        return {"fsid": self.fsid, "actions": list({action for group in ACTIONS.values() for action in group})}

    def ceph_fsid(self):
        return {"fsid": self.fsid}

    def request(self, action, **kwargs):
        self.calls.append(action)
        if action in self.fail:
            raise ExecutorClientError("COMMAND_FAILED", "private secret error output")
        data = {
            "ceph.mon_dump": {"epoch": 3, "mons": [{"name": "a", "rank": 0}, {"name": "b", "rank": 1}]},
            "ceph.quorum_status": {"quorum": [0], "election_epoch": 7},
            "ceph.mgr_dump": {"active_name": "mgr-a", "available": True, "standbys": [{"name": "mgr-b"}]},
            "ceph.mgr_modules": {"enabled_modules": ["prometheus"]},
            "ceph.osd_df": {"nodes": [{"id": 0, "kb_used": 20}, {"id": 1, "kb_used": 40}]},
            "ceph.osd_tree": {"nodes": []},
            "ceph.host_ls": [{"hostname": "host-a"}, {"hostname": "not-allowed"}],
            "ceph.pool_ls_detail": [{"pool": 1, "pool_name": "rbd-lab"}, {"pool": 2, "pool_name": "private-pool"}],
            "ceph.df": {"stats": {}, "pools": []},
        }.get(action, {})
        return {"fsid": self.fsid, "data": data, "collected_at": "2026-10-12T00:00:00+00:00"}


class ClusterMetricsTests(unittest.TestCase):
    def test_pacific_pool_id_alias_joins_capacity_without_inventing_identity(self):
        result = normalize("pool", {
            "ceph.pool_ls_detail": {"data": [{"pool_id": 13, "pool_name": "bench_pa2", "pg_num": 1}]},
            "ceph.df": {"data": {"pools": [{"id": 13, "stats": {"bytes_used": 42}}]}},
        })
        self.assertEqual(result[0]["id"], "13")
        self.assertEqual(result[0]["capacity"], {"bytes_used": 42})

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
            cluster_id="lab", ceph_expected_fsid=FSID, evidence_root=Path(self.directory.name),
            upgrade_allowed_osds="0", upgrade_allowed_hosts="host-a", upgrade_allowed_pools="rbd-lab")
        self.repo = MemoryRepository()
        self.client = FakeClient()
        self.service = ClusterMetricsService(self.settings, self.repo, self.client)

    def collect(self, scopes=None, resource_ids=None, key="test-request-1"):
        return self.service.create(scopes=scopes or ["mon"], resource_ids=resource_ids or [], idempotency_key=key)

    def test_snapshot_is_durable_scoped_verified_and_replay_does_not_collect_again(self):
        result = self.collect(["osd", "host", "pool"])
        self.assertEqual({row["id"] for row in result["resources"]}, {"0", "host-a", "1"})
        self.assertNotIn("private-pool", str(result))
        self.assertNotIn("not-allowed", str(result))
        self.assertNotIn("filesystem:", str(result))
        self.assertTrue(result["artifact"]["verified"])
        call_count = len(self.client.calls)
        self.assertEqual(self.collect(["osd", "host", "pool"])["id"], result["id"])
        self.assertEqual(len(self.client.calls), call_count)
        with self.assertRaisesRegex(CollectionError, "different collection"):
            self.collect(["mon"])

    def test_single_resource_missing_metrics_are_null_not_zero(self):
        result = self.collect(["mon"], ["b"])
        self.assertEqual(len(result["resources"]), 1)
        self.assertIs(result["resources"][0]["in_quorum"], False)
        self.client.fail.add("ceph.quorum_status")
        partial = self.collect(["mon"], ["b"], "other-request")
        self.assertEqual(partial["quality"], "PARTIAL")
        self.assertIsNone(partial["resources"][0]["in_quorum"])
        self.assertEqual(partial["metrics"][0]["quality"], "UNSUPPORTED")
        self.assertNotIn("private secret", str(partial))

    def test_wrong_fsid_fails_before_commands_or_persistence(self):
        self.client.fsid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with self.assertRaisesRegex(CollectionError, "different cluster"):
            self.collect()
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.repo.rows, {})

    def test_revoked_resource_allowlist_blocks_historical_collection(self):
        result = self.collect(["osd"])
        restricted = self.settings.model_copy(update={"upgrade_allowed_osds": "1"})
        with self.assertRaisesRegex(CollectionError, "no longer allowed"):
            ClusterMetricsService(restricted, self.repo, self.client).get(UUID(result["id"]))

    def test_tampered_artifact_and_cross_cluster_lookup_fail(self):
        result = self.collect()
        artifact = next(Path(self.directory.name).rglob("*.json"))
        artifact.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(CollectionError, "integrity"):
            self.service.get(UUID(result["id"]))
        other = self.settings.model_copy(update={"cluster_id": "other"})
        with self.assertRaisesRegex(CollectionError, "not found"):
            ClusterMetricsService(other, self.repo, self.client).get(UUID(result["id"]))

    def test_snapshot_metrics_are_not_synthetic_time_series(self):
        state = normalize("mgr", {"ceph.mgr_dump": {"data": {"active_name": "a", "standbys": [{"name": "b"}]}}})
        sample = samples({"resources": state, "id": "c", "observed_at": "source-time"})
        self.assertTrue(all(row["value"] is None for row in sample))
        self.assertTrue(all(row["observed_at"] == "source-time" for row in sample))

    def test_unconfigured_read_view_is_offline_safe_and_collection_is_blocked(self):
        settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False)
        service = ClusterMetricsService(settings, self.repo, self.client)
        self.assertEqual(service.resources()["reasons"], ["CLUSTER_NOT_CONFIGURED"])
        with self.assertRaisesRegex(CollectionError, "Configure"):
            service.create(scopes=["mon"], resource_ids=[], idempotency_key="request-id")
        self.assertFalse(self.client.calls)

    def test_api_rejects_arbitrary_action_path_and_extra_parameters(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            for payload in ({"scopes": ["shell"]}, {"scopes": ["mon"], "command": "whoami"},
                            {"scopes": ["host"], "resource_ids": ["../../secret"]}):
                response = client.post("/api/v1/cluster/collections", json=payload, headers={"Idempotency-Key": "request-key"})
                self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
