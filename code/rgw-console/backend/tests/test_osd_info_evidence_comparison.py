from __future__ import annotations

import unittest

from app.modules.osd_info_collector.evidence_comparison import compare_config_evidence


FSID = "11111111-2222-4333-8444-555555555555"


def collection(collection_id: str, phase: str) -> dict:
    return {
        "id": collection_id,
        "cluster_id": "lab-a",
        "fsid": FSID,
        "session_id": "11111111-1111-4111-8111-111111111111",
        "config_snapshot_id": "22222222-2222-4222-8222-222222222222",
        "phase": phase,
        "state": "COMPLETE",
        "quality": "VALID",
        "artifact_sha256": "a" * 64,
        "collected_at": "2026-10-09T00:00:00Z",
        "osds": [{"osd_id": 0, "quality": "VALID"}],
    }


def artifact(*, cluster_rows=None, effective=None, config_exit_code=0) -> dict:
    return {
        "cluster_evidence": {
            "config_dump": {
                "exit_code": config_exit_code,
                "data": cluster_rows if cluster_rows is not None else [],
            }
        },
        "osds": [{
            "identity": {"osd_id": 0},
            "evidence": {
                "config_effective": {
                    "exit_code": 0,
                    "data": effective if effective is not None else {},
                }
            },
        }],
    }


class OsdInfoEvidenceComparisonTests(unittest.TestCase):
    def test_cluster_and_effective_config_changes_are_reported(self):
        before = artifact(
            cluster_rows=[{"who": "global", "name": "osd_pool_default_size", "value": "3"}],
            effective={"osd_memory_target": "1G"},
        )
        after = artifact(
            cluster_rows=[{"who": "global", "name": "osd_pool_default_size", "value": "2"}],
            effective={"osd_memory_target": "2G", "osd_op_queue": "mclock_scheduler"},
        )

        result = compare_config_evidence(
            collection("before", "BEFORE"), collection("after", "AFTER_STABLE"), before, after
        )

        self.assertEqual(result["comparison_status"], "COMPARABLE")
        self.assertEqual(result["cluster_config"]["changed_count"], 1)
        self.assertEqual(result["osds"][0]["changed_count"], 2)
        self.assertEqual(result["summary"]["osd_changed_option_count"], 2)

    def test_config_row_order_is_not_a_change(self):
        rows = [
            {"who": "global", "name": "b", "value": "2"},
            {"who": "global", "name": "a", "value": "1"},
        ]
        before = artifact(cluster_rows=rows, effective={"b": "2", "a": "1"})
        after = artifact(cluster_rows=list(reversed(rows)), effective={"a": "1", "b": "2"})

        result = compare_config_evidence(
            collection("before", "BEFORE"), collection("after", "AFTER_START"), before, after
        )

        self.assertEqual(result["cluster_config"]["changed_count"], 0)
        self.assertEqual(result["osds"][0]["changed_count"], 0)

    def test_sensitive_change_is_detected_without_returning_values(self):
        before = artifact(cluster_rows=[{"who": "client.rgw", "name": "rgw_secret_key", "value": "old"}])
        after = artifact(cluster_rows=[{"who": "client.rgw", "name": "rgw_secret_key", "value": "new"}])

        result = compare_config_evidence(
            collection("before", "BEFORE"), collection("after", "AFTER_STABLE"), before, after
        )

        change = result["cluster_config"]["changed"][0]
        self.assertEqual(change["before"]["value"], "[REDACTED]")
        self.assertEqual(change["after"]["value"], "[REDACTED]")
        self.assertNotIn("old", str(result))
        self.assertNotIn("new", str(result))

    def test_missing_command_evidence_is_inconclusive(self):
        before = artifact(config_exit_code=5)
        after = artifact()

        result = compare_config_evidence(
            collection("before", "BEFORE"), collection("after", "AFTER_START"), before, after
        )

        self.assertEqual(result["comparison_status"], "INCONCLUSIVE")
        self.assertIn("CLUSTER_CONFIG_UNAVAILABLE:BEFORE", result["reasons"])


if __name__ == "__main__":
    unittest.main()
