from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.config import Settings
from app.modules.osd_info_collector.domain import (
    CollectionPhase,
    OsdInfoError,
    Quality,
    validate_collection,
)
from app.modules.osd_info_collector.service import OsdInfoService
from app.modules.osd_info_collector.repository import PostgresOsdInfoRepository
from app.platform.evidence import FilesystemArtifactStore


FSID = "11111111-2222-4333-8444-555555555555"


def payload(*, osd_id: int = 0) -> dict:
    return {
        "schema_version": 1,
        "kind": "CEPH_OSD_BASELINE",
        "collector_version": "1.0.2",
        "collection_id": str(uuid4()),
        "collected_at": "2026-10-08T00:00:00Z",
        "cluster_fsid": FSID,
        "quality": "VALID",
        "errors": [],
        "osd_count": 1,
        "cluster_evidence": {},
        "osds": [
            {
                "schema_version": 1,
                "quality": "VALID",
                "warnings": [],
                "errors": [],
                "identity": {
                    "osd_id": osd_id,
                    "name": f"osd.{osd_id}",
                    "osd_fsid": "osd-fsid-0",
                    "hostname": "host-a",
                    "crush_location": {"rack": "rack-a", "host": "host-a"},
                    "device_class": "hdd",
                },
                "version": {
                    "ceph_version": "ceph version 17.2.7",
                    "ceph_version_short": "quincy",
                    "container_image": "quay.io/ceph/ceph:v17.2.7",
                    "container_image_id": "sha256:" + "a" * 64,
                },
                "network": {
                    "public_ip": "10.0.0.10",
                    "public_ips": ["10.0.0.10"],
                    "cluster_ip": "10.1.0.10",
                    "cluster_ips": ["10.1.0.10"],
                },
                "devices": {
                    "data": {"path": "/dev/dm-0", "physical_devices": ["/dev/sdb"], "size_bytes": 1000},
                    "db": {"path": "/dev/nvme0n1p2", "physical_devices": ["/dev/nvme0n1"], "size_bytes": 100},
                    "wal": {"path": None, "physical_devices": [], "size_bytes": None},
                    "device_ids": ["ATA_disk_SERIAL"],
                },
                "capacity": {
                    "total_bytes": 1000,
                    "used_bytes": 250,
                    "available_bytes": 750,
                    "used_percent": 25.0,
                },
                "state": {
                    "up": True,
                    "in": True,
                    "status": "up",
                    "crush_weight": 1.0,
                    "reweight": 1.0,
                    "primary_affinity": 1.0,
                },
                "placement_groups": {"count": 8, "primary_count": 3},
                "evidence": {"config_effective": {"exit_code": 0, "data": {"osd_memory_target": "1G"}}},
            }
        ],
    }


class FakeCollector:
    def __init__(self, result: dict):
        self.result = result
        self.calls = []

    def collect(self, osd_ids):
        self.calls.append(osd_ids)
        return self.result


class FakeRepository:
    def __init__(self):
        self.collection_id = uuid4()
        self.claims = []
        self.failures = []

    def claim(self, **kwargs):
        self.claims.append(kwargs)
        return self.collection_id, None

    def finish(self, collection_id, *, validated, artifact):
        return {
            "id": str(collection_id),
            "quality": validated.quality.value,
            "artifact_sha256": artifact.sha256,
            "osd_count": len(validated.records),
            "replayed": False,
        }

    def fail(self, collection_id, **kwargs):
        self.failures.append((collection_id, kwargs))


class FakeReadRepository:
    def __init__(self, collection, osd=None):
        self.collection = collection
        self.osd = osd or {}

    def get(self, collection_id):
        return self.collection

    def get_osd(self, collection_id, osd_id):
        return self.osd


class FakeComparisonRepository:
    def __init__(self, collections):
        self.collections = collections

    def get(self, collection_id):
        return self.collections[collection_id]


class FakeRows:
    def __init__(self, *, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, collection):
        self.collection = collection
        self.record_insert = None
        self.collection_update = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def transaction(self):
        return self

    def execute(self, query, params=()):
        normalized = " ".join(str(query).split())
        if "SELECT * FROM osd_inventory_collections" in normalized:
            return FakeRows(row=self.collection)
        if "SELECT c.*, a.uri AS evidence_uri" in normalized:
            return FakeRows(row=self.collection)
        if "SELECT osd_id, quality, warnings" in normalized:
            return FakeRows(rows=[])
        if "INSERT INTO osd_inventory_records" in normalized:
            self.record_insert = (str(query), params)
        if "UPDATE osd_inventory_collections" in normalized:
            self.collection_update = (str(query), params)
        return FakeRows()


class OsdInfoDomainTests(unittest.TestCase):
    def test_full_collector_record_indexes_planning_fields(self):
        result = validate_collection(payload(), expected_fsid=FSID, requested_osd_ids=(0,))

        self.assertEqual(result.quality, Quality.VALID)
        self.assertEqual(result.records[0]["data_device_path"], "/dev/dm-0")
        self.assertEqual(result.records[0]["physical_devices"], ["/dev/sdb"])
        self.assertEqual(result.records[0]["crush_location"]["rack"], "rack-a")
        self.assertEqual(result.records[0]["device_class"], "hdd")
        self.assertEqual(result.records[0]["public_ips"], ["10.0.0.10"])
        self.assertEqual(result.records[0]["cluster_ips"], ["10.1.0.10"])
        self.assertEqual(result.records[0]["db_device_path"], "/dev/nvme0n1p2")
        self.assertEqual(result.records[0]["db_physical_devices"], ["/dev/nvme0n1"])
        self.assertEqual(result.records[0]["device_ids"], ["ATA_disk_SERIAL"])
        self.assertEqual(result.records[0]["container_image_id"], "sha256:" + "a" * 64)
        self.assertEqual(result.records[0]["primary_count"], 3)

    def test_cluster_planning_context_is_normalized_and_preserves_zero(self):
        raw = payload()
        raw["cluster_evidence"] = {
            "status": {"exit_code": 0, "data": {
                "health": {"status": "HEALTH_WARN", "checks": {"RECENT_CRASH": {}}},
                "osdmap": {"epoch": 0, "num_osds": 3, "num_up_osds": 2, "num_in_osds": 3},
                "pgmap": {"num_pgs": 0},
            }},
            "pg_stat": {"exit_code": 0, "data": {"num_pgs": 0}},
            "osd_dump": {"exit_code": 0, "data": {"epoch": 9, "flags": "noout,norebalance"}},
            "pool_ls_detail": {"exit_code": 0, "data": [{
                "pool": 2, "pool_name": "volumes", "type": 1, "size": 3,
                "min_size": 2, "pg_num": 32, "pgp_num": 32, "crush_rule": 0,
            }]},
            "versions": {"exit_code": 0, "data": {"osd": {"ceph version 17.2.7": 3}}},
        }

        result = validate_collection(raw, expected_fsid=FSID, requested_osd_ids=(0,))
        summary = result.cluster_summary

        self.assertEqual(summary["health_status"], "HEALTH_WARN")
        self.assertEqual(summary["osdmap_epoch"], 0)
        self.assertEqual(summary["cluster_pg_count"], 0)
        self.assertEqual(summary["cluster_flags"], ["noout", "norebalance"])
        self.assertEqual(summary["pool_summaries"][0]["pool_name"], "volumes")
        self.assertEqual(summary["pool_summaries"][0]["min_size"], 2)
        self.assertEqual(summary["version_summary"]["osd"]["ceph version 17.2.7"], 3)

    def test_missing_core_field_stays_none_and_becomes_inconclusive(self):
        raw = payload()
        raw["osds"][0]["capacity"]["used_bytes"] = None

        result = validate_collection(raw, expected_fsid=FSID, requested_osd_ids=(0,))

        self.assertEqual(result.quality, Quality.INCONCLUSIVE)
        self.assertIsNone(result.records[0]["used_bytes"])
        self.assertIn("CORE_PLANNING_FIELD_MISSING", result.records[0]["warnings"])

    def test_pacific_pool_id_and_pg_placement_aliases(self):
        raw = payload()
        raw["cluster_evidence"]["pool_ls_detail"] = {"exit_code": 0, "data": [
            {"pool_id": 13, "pool_name": "bench_pa2", "pg_num": 1, "pg_placement_num": 1},
        ]}
        result = validate_collection(raw, expected_fsid=FSID, requested_osd_ids=(0,))
        row = result.cluster_summary["pool_summaries"][0]
        self.assertEqual(row["pool_id"], 13)
        self.assertEqual(row["pgp_num"], 1)


    def test_missing_device_is_partial_and_never_invented(self):
        raw = payload()
        raw["osds"][0]["devices"]["data"] = {"path": None, "physical_devices": []}

        result = validate_collection(raw, expected_fsid=FSID, requested_osd_ids=(0,))

        self.assertEqual(result.quality, Quality.PARTIAL)
        self.assertIsNone(result.records[0]["data_device_path"])
        self.assertEqual(result.records[0]["physical_devices"], [])

    def test_lvm_path_without_reported_physical_device_is_partial(self):
        raw = payload()
        raw["osds"][0]["devices"]["data"]["physical_devices"] = []

        result = validate_collection(raw, expected_fsid=FSID, requested_osd_ids=(0,))

        self.assertEqual(result.quality, Quality.PARTIAL)
        self.assertEqual(result.records[0]["data_device_path"], "/dev/dm-0")
        self.assertEqual(result.records[0]["physical_devices"], [])

    def test_missing_topology_is_partial_and_never_invented(self):
        raw = payload()
        raw["osds"][0]["identity"]["crush_location"] = {}
        raw["osds"][0]["identity"]["device_class"] = None

        result = validate_collection(raw, expected_fsid=FSID, requested_osd_ids=(0,))

        self.assertEqual(result.quality, Quality.PARTIAL)
        self.assertEqual(result.records[0]["crush_location"], {})
        self.assertIsNone(result.records[0]["device_class"])
        self.assertIn("CRUSH_LOCATION_NOT_REPORTED", result.records[0]["warnings"])
        self.assertIn("DEVICE_CLASS_NOT_REPORTED", result.records[0]["warnings"])

    def test_fsid_mismatch_is_rejected(self):
        with self.assertRaises(OsdInfoError) as raised:
            validate_collection(
                payload(),
                expected_fsid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                requested_osd_ids=(0,),
            )
        self.assertEqual(raised.exception.code, "FSID_MISMATCH")


class OsdInfoServiceTests(unittest.TestCase):
    def settings(self, root: str) -> Settings:
        return Settings(
            _env_file=None,
            feature_legacy_rgw=False,
            feature_legacy_rbd=False,
            feature_upgrade=True,
            cluster_id="lab-a",
            ceph_expected_fsid=FSID,
            upgrade_allowed_osds="0,4",
            evidence_root=Path(root),
        )

    def test_all_means_every_allowlisted_osd_and_writes_hashed_artifact(self):
        raw = payload()
        raw["osds"].append({**raw["osds"][0], "identity": {**raw["osds"][0]["identity"], "osd_id": 4, "name": "osd.4", "osd_fsid": "osd-fsid-4"}})
        raw["osd_count"] = 2
        collector = FakeCollector(raw)
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as root:
            result = OsdInfoService(self.settings(root), repository, collector).create(
                session_id=uuid4(),
                phase=CollectionPhase.BEFORE,
                requested_osd_ids=None,
                idempotency_key="collect-before-001",
            )

        self.assertEqual(collector.calls, [(0, 4)])
        self.assertEqual(result["osd_count"], 2)
        self.assertEqual(len(result["artifact_sha256"]), 64)

    def test_outside_allowlist_is_blocked_before_repository_or_collector(self):
        collector = FakeCollector(payload())
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as root:
            service = OsdInfoService(self.settings(root), repository, collector)
            with self.assertRaises(OsdInfoError) as raised:
                service.create(
                    session_id=uuid4(),
                    phase=CollectionPhase.MANUAL,
                    requested_osd_ids=(9,),
                    idempotency_key="collect-manual-001",
                )

        self.assertEqual(raised.exception.code, "SCOPE_NOT_ALLOWED")
        self.assertEqual(repository.claims, [])
        self.assertEqual(collector.calls, [])

    def test_cluster_evidence_is_integrity_checked_and_response_redacted(self):
        raw = payload()
        raw["cluster_evidence"] = {
            "config_dump": {
                "data": [
                    {"name": "osd_memory_target", "value": "1G"},
                    {"name": "rgw_secret_key", "value": "clear-text-secret"},
                ]
            },
            "status": {"command": ["ceph", "--conf", "/etc/ceph/ceph.conf", "status"]},
        }
        collection_id = uuid4()
        session_id = uuid4()
        with tempfile.TemporaryDirectory() as root:
            settings = self.settings(root)
            artifact = FilesystemArtifactStore(
                Path(root), max_artifact_bytes=settings.evidence_max_artifact_bytes
            ).put_json(
                raw,
                cluster_id="lab-a",
                session_id=session_id,
                run_id=collection_id,
            )
            repository = FakeReadRepository({
                "id": str(collection_id),
                "state": "COMPLETE",
                "phase": "BEFORE",
                "quality": "VALID",
                "collector_version": "1.0.2",
                "collected_at": "2026-10-08T00:00:00Z",
                "fsid": FSID,
                "requested_osd_ids": [0],
                "evidence_uri": artifact.uri,
                "artifact_sha256": artifact.sha256,
                "evidence_size_bytes": artifact.size_bytes,
            })

            result = OsdInfoService(settings, repository, None).get_evidence(collection_id)

        rows = result["cluster_evidence"]["config_dump"]["data"]
        self.assertTrue(result["artifact"]["verified"])
        self.assertEqual(rows[0]["value"], "1G")
        self.assertEqual(rows[1]["value"], "[REDACTED]")
        self.assertEqual(result["cluster_evidence"]["status"]["command"][2], "[REDACTED]")

    def test_cluster_evidence_rejects_tampered_artifact(self):
        raw = payload()
        collection_id = uuid4()
        session_id = uuid4()
        with tempfile.TemporaryDirectory() as root:
            settings = self.settings(root)
            artifact = FilesystemArtifactStore(
                Path(root), max_artifact_bytes=settings.evidence_max_artifact_bytes
            ).put_json(raw, cluster_id="lab-a", session_id=session_id, run_id=collection_id)
            target = Path(root) / artifact.uri.removeprefix("filesystem:")
            target.write_bytes(target.read_bytes().replace(b"VALID", b"BROKE", 1))
            repository = FakeReadRepository({
                "state": "COMPLETE", "phase": "BEFORE", "quality": "VALID",
                "collector_version": "1.0.2", "collected_at": "2026-10-08T00:00:00Z",
                "fsid": FSID, "requested_osd_ids": [0], "evidence_uri": artifact.uri,
                "artifact_sha256": artifact.sha256, "evidence_size_bytes": artifact.size_bytes,
            })

            with self.assertRaises(OsdInfoError) as raised:
                OsdInfoService(settings, repository, None).get_evidence(collection_id)

        self.assertEqual(raised.exception.code, "EVIDENCE_ARTIFACT_INVALID")

    def test_per_osd_payload_is_redacted_on_read(self):
        repository = FakeReadRepository({}, osd={
            "osd_id": 0,
            "payload": {
                "password": "clear-text",
                "evidence": {"argv": ["ceph", "--keyring", "/etc/ceph/keyring", "status"]},
            },
        })
        with tempfile.TemporaryDirectory() as root:
            result = OsdInfoService(self.settings(root), repository, None).get_osd(uuid4(), 0)

        self.assertEqual(result["payload"]["password"], "[REDACTED]")
        self.assertEqual(result["payload"]["evidence"]["argv"][2], "[REDACTED]")

    def test_config_comparison_reads_two_verified_artifacts(self):
        before_id = uuid4()
        after_id = uuid4()
        session_id = uuid4()
        with tempfile.TemporaryDirectory() as root:
            settings = self.settings(root)
            store = FilesystemArtifactStore(
                Path(root), max_artifact_bytes=settings.evidence_max_artifact_bytes
            )
            raw_before = payload()
            raw_after = payload()
            raw_before["cluster_evidence"] = {
                "config_dump": {"exit_code": 0, "data": {"osd_pool_default_size": "3"}}
            }
            raw_after["cluster_evidence"] = {
                "config_dump": {"exit_code": 0, "data": {"osd_pool_default_size": "2"}}
            }
            for raw in (raw_before, raw_after):
                raw["osds"][0]["evidence"]["config_effective"]["exit_code"] = 0
            before_artifact = store.put_json(
                raw_before, cluster_id="lab-a", session_id=session_id, run_id=before_id
            )
            after_artifact = store.put_json(
                raw_after, cluster_id="lab-a", session_id=session_id, run_id=after_id
            )

            def row(collection_id, phase, artifact):
                return {
                    "id": str(collection_id), "cluster_id": "lab-a", "state": "COMPLETE",
                    "phase": phase, "quality": "VALID", "collector_version": "1.0.2",
                    "collected_at": "2026-10-08T00:00:00Z", "fsid": FSID,
                    "session_id": str(session_id), "config_snapshot_id": str(uuid4()),
                    "requested_osd_ids": [0], "osds": [{"osd_id": 0, "quality": "VALID"}],
                    "evidence_uri": artifact.uri, "artifact_sha256": artifact.sha256,
                    "evidence_size_bytes": artifact.size_bytes,
                }

            config_snapshot_id = str(uuid4())
            before_row = row(before_id, "BEFORE", before_artifact)
            after_row = row(after_id, "AFTER_STABLE", after_artifact)
            before_row["config_snapshot_id"] = config_snapshot_id
            after_row["config_snapshot_id"] = config_snapshot_id
            repository = FakeComparisonRepository({before_id: before_row, after_id: after_row})
            result = OsdInfoService(settings, repository, None).compare_evidence(
                before_id=before_id, after_id=after_id
            )

        self.assertEqual(result["comparison_status"], "COMPARABLE")
        self.assertEqual(result["cluster_config"]["changed_count"], 1)


class OsdInfoRepositoryShapeTests(unittest.TestCase):
    def test_topology_record_insert_has_one_value_for_every_placeholder(self):
        collection_id = uuid4()
        action_job_id = uuid4()
        session_id = uuid4()
        artifact_id = uuid4()
        collection = {
            "id": collection_id,
            "action_job_id": action_job_id,
            "cluster_id": "lab-a",
            "fsid": FSID,
            "session_id": session_id,
            "phase": "BEFORE",
            "state": "RUNNING",
        }
        fake_connection = FakeConnection(collection)
        validated = validate_collection(payload(), expected_fsid=FSID, requested_osd_ids=(0,))
        artifact = SimpleNamespace(
            id=artifact_id,
            uri="filesystem:lab-a/artifact.json",
            sha256="d" * 64,
            size_bytes=1234,
            mime_type="application/json",
        )

        with patch(
            "app.modules.osd_info_collector.repository.connection",
            return_value=fake_connection,
        ):
            PostgresOsdInfoRepository().finish(
                collection_id,
                validated=validated,
                artifact=artifact,
            )

        self.assertIsNotNone(fake_connection.record_insert)
        query, params = fake_connection.record_insert
        self.assertEqual(query.count("%s"), len(params))
        self.assertEqual(len(params), 40)
        self.assertEqual(params[8], "hdd")
        self.assertEqual(params[16], "/dev/nvme0n1p2")
        self.assertEqual(params[38], "sha256:" + "a" * 64)
        self.assertIsNotNone(fake_connection.collection_update)
        update_query, update_params = fake_connection.collection_update
        self.assertEqual(update_query.count("%s"), len(update_params))
        self.assertEqual(len(update_params), 17)


if __name__ == "__main__":
    unittest.main()
