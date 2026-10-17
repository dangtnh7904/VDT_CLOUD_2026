from __future__ import annotations

import unittest

from app.config import Settings
from app.modules.cluster_profiles.domain import ClusterReadError
from app.modules.cluster_profiles.normalization import normalize_inventory
from app.modules.cluster_profiles.service import ClusterProfileService


FSID = "11111111-2222-3333-4444-555555555555"


class FakeObservations:
    def capabilities(self):
        return {
            "fsid": FSID,
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

    def identity(self):
        return {"fsid": FSID, "observed_at": "2026-10-08T00:00:00Z"}

    def inventory(self):
        return inventory_fixture()


def configured_settings(**overrides):
    values = {
        "feature_legacy_rgw": False,
        "feature_legacy_rbd": False,
        "feature_upgrade": True,
        "cluster_id": "lab-a",
        "ceph_expected_fsid": FSID,
        "upgrade_allowed_osds": "0",
        "upgrade_allowed_hosts": "host-a",
        "upgrade_allowed_pools": "rbd-lab",
        "upgrade_allowed_device_classes": "hdd",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def inventory_fixture():
    status = {
        "health": {"status": "HEALTH_OK"},
        "osdmap": {"osdmap": {"epoch": 42, "num_osds": 1, "num_up_osds": 1, "num_in_osds": 1}},
    }
    return {
        "fsid": FSID,
        "observed_at": "2026-10-08T00:00:00Z",
        "versions": {"osd": {"ceph version 17.2.7": 1}},
        "capacity": {
            "status_before": status,
            "status_after": status,
            "osd_df": {
                "nodes": [
                    {
                        "id": 0,
                        "device_class": "hdd",
                        "kb": 1000,
                        "kb_used": 100,
                        "kb_avail": 900,
                        "utilization": 10,
                        "pgs": 8,
                        "reweight": 1,
                    }
                ]
            },
            "osd_tree": {
                "nodes": [
                    {"id": -1, "name": "default", "type": "root", "children": [-2]},
                    {"id": -2, "name": "host-a", "type": "host", "children": [0]},
                    {"id": 0, "name": "osd.0", "type": "osd", "status": "up", "device_class": "hdd"},
                ]
            },
            "pool_details": [
                {"pool": 1, "pool_name": "rbd-lab", "type": 1, "size": 3, "min_size": 2, "pg_num": 8, "crush_rule": 0}
            ],
            "crush_rules": [],
        },
    }


class ClusterProfileServiceTests(unittest.TestCase):
    def test_pacific_pool_id_alias_preserves_real_identity(self):
        raw = inventory_fixture()
        row = raw["capacity"]["pool_details"][0]
        row["pool_id"] = row.pop("pool")
        result = normalize_inventory(raw, cluster_id="lab-a",
            allowed_osds=frozenset({"0"}), allowed_hosts=frozenset({"host-a"}),
            allowed_pools=frozenset({"rbd-lab"}), allowed_device_classes=frozenset({"hdd"}))
        self.assertEqual(result["pools"][0]["pool_id"], 1)
        self.assertTrue(result["pools"][0]["allowed"])

    def test_capability_matrix_does_not_infer_unsupported_upgrade_actions(self):
        result = ClusterProfileService(configured_settings(), FakeObservations()).capabilities()

        self.assertEqual(result["capabilities"]["query_osd_inventory"], "SUPPORTED")
        self.assertEqual(result["capabilities"]["collect_osd_info"], "UNSUPPORTED")
        self.assertEqual(result["capabilities"]["query_osd_image_digest"], "UNSUPPORTED")
        self.assertEqual(result["capabilities"]["cephadm_redeploy_target_image"], "UNSUPPORTED")

    def test_inventory_is_canonical_and_scope_is_explicit(self):
        result = ClusterProfileService(configured_settings(), FakeObservations()).inventory()

        self.assertEqual(result["quality"], "VALID")
        self.assertEqual(result["osdmap_epoch"], 42)
        self.assertTrue(result["osds"][0]["allowed"])
        self.assertTrue(result["pools"][0]["allowed"])
        self.assertEqual(result["osds"][0]["available_kb"], 900)

    def test_epoch_change_is_inconclusive_not_silently_accepted(self):
        raw = inventory_fixture()
        raw["capacity"]["status_after"] = {
            **raw["capacity"]["status_after"],
            "osdmap": {"osdmap": {"epoch": 43}},
        }

        result = normalize_inventory(
            raw,
            cluster_id="lab-a",
            allowed_osds=frozenset({"0"}),
            allowed_hosts=frozenset({"host-a"}),
            allowed_pools=frozenset({"rbd-lab"}),
            allowed_device_classes=frozenset({"hdd"}),
        )

        self.assertEqual(result["quality"], "INCONCLUSIVE")
        self.assertIn("OSDMAP_CHANGED_DURING_COLLECTION", result["limitations"])

    def test_inventory_is_independent_of_upgrade_workspace(self):
        service = ClusterProfileService(
            configured_settings(feature_upgrade=False),
            FakeObservations(),
        )

        self.assertEqual(service.inventory()["fsid"], FSID)
        self.assertNotIn("FEATURE_UPGRADE_DISABLED", service.profile()["blockers"])


if __name__ == "__main__":
    unittest.main()
