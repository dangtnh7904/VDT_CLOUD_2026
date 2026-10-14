from __future__ import annotations

import unittest

from app.modules.osd_info_collector.comparison import compare_collections


FSID = "11111111-2222-4333-8444-555555555555"


def collection(*, collection_id: str, phase: str, osds=None, **overrides):
    value = {
        "id": collection_id,
        "cluster_id": "lab-a",
        "fsid": FSID,
        "session_id": "11111111-1111-4111-8111-111111111111",
        "config_snapshot_id": "22222222-2222-4222-8222-222222222222",
        "phase": phase,
        "state": "COMPLETE",
        "quality": "VALID",
        "artifact_sha256": "a" * 64,
        "collected_at": "2026-10-09T00:00:00+00:00",
        "osds": osds or [
            {
                "osd_id": 0,
                "quality": "VALID",
                "hostname": "host-a",
                "crush_location": {"root": "default", "rack": "rack-a", "host": "host-a"},
                "device_class": "hdd",
                "public_ips": ["10.0.0.10"],
                "cluster_ip": "10.1.0.10",
                "cluster_ips": ["10.1.0.10"],
                "used_bytes": 100,
                "pg_count": 8,
                "up": True,
                "in": True,
                "physical_devices": ["/dev/sdb"],
                "db_device_path": "/dev/nvme0n1p2",
                "db_physical_devices": ["/dev/nvme0n1"],
                "device_ids": ["ATA_disk_SERIAL"],
                "container_image_id": "sha256:" + "a" * 64,
            }
        ],
    }
    value.update(overrides)
    return value


class OsdInfoComparisonTests(unittest.TestCase):
    def test_comparable_snapshots_preserve_raw_field_changes(self):
        before = collection(collection_id="before", phase="BEFORE")
        after = collection(
            collection_id="after",
            phase="AFTER_STABLE",
            osds=[{
                **before["osds"][0],
                "used_bytes": 125,
                "pg_count": 9,
                "physical_devices": ["/dev/sdb"],
            }],
        )

        result = compare_collections(before, after)

        self.assertEqual(result["comparison_status"], "COMPARABLE")
        self.assertEqual(result["changed_osd_count"], 1)
        fields = {item["field"] for item in result["changes"][0]["fields"]}
        self.assertEqual(fields, {"used_bytes", "pg_count"})

    def test_scope_mismatch_is_not_comparable_but_raw_overlap_remains(self):
        before = collection(collection_id="before", phase="BEFORE")
        after = collection(
            collection_id="after",
            phase="AFTER_START",
            osds=[
                {**before["osds"][0], "used_bytes": 110},
                {**before["osds"][0], "osd_id": 2, "hostname": "host-b"},
            ],
        )

        result = compare_collections(before, after)

        self.assertEqual(result["comparison_status"], "NOT_COMPARABLE")
        self.assertIn("OSD_SCOPE_MISMATCH", result["reasons"])
        self.assertEqual(result["scope"]["added_osd_ids"], [2])
        self.assertEqual(result["changed_osd_count"], 1)

    def test_missing_quality_is_inconclusive_and_null_is_not_zero(self):
        before = collection(collection_id="before", phase="BEFORE")
        after = collection(
            collection_id="after",
            phase="AFTER_STABLE",
            quality="PARTIAL",
            osds=[{**before["osds"][0], "quality": "PARTIAL", "used_bytes": None}],
        )

        result = compare_collections(before, after)

        self.assertEqual(result["comparison_status"], "INCONCLUSIVE")
        change = next(item for item in result["changes"][0]["fields"] if item["field"] == "used_bytes")
        self.assertEqual(change, {"field": "used_bytes", "before": 100, "after": None})

    def test_topology_image_and_device_changes_are_compared(self):
        before = collection(collection_id="before", phase="BEFORE")
        after = collection(
            collection_id="after",
            phase="AFTER_STABLE",
            osds=[{
                **before["osds"][0],
                "device_class": "ssd",
                "db_device_path": "/dev/nvme1n1p2",
                "container_image_id": "sha256:" + "b" * 64,
            }],
        )

        result = compare_collections(before, after)

        fields = {item["field"] for item in result["changes"][0]["fields"]}
        self.assertEqual(
            fields,
            {"device_class", "db_device_path", "container_image_id"},
        )

    def test_address_and_device_list_order_is_not_a_change(self):
        before = collection(collection_id="before", phase="BEFORE")
        before["osds"][0]["public_ips"] = ["10.0.0.11", "10.0.0.10"]
        before["osds"][0]["physical_devices"] = ["/dev/sdc", "/dev/sdb"]
        after = collection(
            collection_id="after",
            phase="AFTER_STABLE",
            osds=[{
                **before["osds"][0],
                "public_ips": ["10.0.0.10", "10.0.0.11"],
                "physical_devices": ["/dev/sdb", "/dev/sdc"],
            }],
        )

        result = compare_collections(before, after)

        self.assertEqual(result["changed_osd_count"], 0)


if __name__ == "__main__":
    unittest.main()
