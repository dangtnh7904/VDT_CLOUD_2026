from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import unittest
import zipfile
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.modules.evidence_exports.api import router, _EXPORT_GATE
from app.modules.evidence_exports.models import ExportRequest
from app.modules.evidence_exports.rendering import ExportError, safe_projection
from app.modules.evidence_exports.service import EvidenceExportService, SourceSnapshot

FSID = "11111111-2222-3333-4444-555555555555"


class EvidenceExportTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
                                 cluster_id="lab", ceph_expected_fsid=FSID, upgrade_allowed_osds="0")
        self.source = {"name": "=SUM(1,2)", "value": None, "zero": 0, "negative": -2,
                       "password": "do-not-export", "uri": "filesystem:private.json",
                       "note": "Bearer abcdefgh12345678 https://user:secret@host/a?token=x"}
        self.original = copy.deepcopy(self.source)
        self.service = EvidenceExportService(self.settings,
            source_loader=lambda request, now: SourceSnapshot(self.source, {"samples": [self.source]},
                raw={"source": self.source}, metadata={"quality": "PARTIAL", "observed_at": "2026-10-01T00:00:00Z"}),
            now=lambda: datetime(2026, 10, 12, tzinfo=timezone.utc))

    def export(self, format):
        return self.service.create(ExportRequest(source="cluster_collection", source_id=uuid4(), format=format))

    def test_json_redacts_without_mutating_source_or_retimestamping_observations(self):
        result = self.export("json")
        body = json.loads(result.content)
        self.assertIsNone(body["data"]["value"])
        self.assertEqual(body["data"]["zero"], 0)
        self.assertEqual(body["manifest"]["observed_at"], "2026-10-01T00:00:00Z")
        self.assertEqual(body["manifest"]["quality"], "PARTIAL")
        self.assertNotIn(b"do-not-export", result.content)
        self.assertNotIn(b"filesystem:", result.content)
        self.assertNotIn(b"abcdef", result.content)
        self.assertNotIn(b"user:secret", result.content)
        self.assertEqual(self.source, self.original)
        self.assertEqual(result.sha256, hashlib.sha256(result.content).hexdigest())

    def test_csv_is_formula_safe_and_distinguishes_null_from_zero(self):
        result = self.export("csv")
        row = next(csv.DictReader(io.StringIO(result.content.decode())))
        self.assertEqual(row["name"], "'=SUM(1,2)")
        self.assertEqual(row["negative"], "-2")
        self.assertEqual(row["zero"], "0")
        self.assertEqual(row["value"], "")
        self.assertIn("value", json.loads(row["_null_fields"]))
        self.assertEqual(row["_quality"], "PARTIAL")

    def test_zip_checksums_cover_every_payload_and_manifest(self):
        result = self.export("zip")
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            names = set(archive.namelist())
            for name in ("data/summary.json", "raw-redacted/001.json"):
                member = archive.read(name)
                self.assertEqual(member.count(b"\n"), 1)
                self.assertIsInstance(json.loads(member), dict)
            self.assertEqual(names, {"manifest.json", "SHA256SUMS", "data/summary.json", "data/records.csv", "report.md", "raw-redacted/001.json"})
            for line in archive.read("SHA256SUMS").decode().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())
            manifest = json.loads(archive.read("manifest.json"))
            for entry in manifest["files"]:
                self.assertEqual(entry["sha256"], hashlib.sha256(archive.read(entry["path"])).hexdigest())
                self.assertEqual(entry["size_bytes"], len(archive.read(entry["path"])))

    def test_markdown_content_cannot_escape_its_code_fence(self):
        self.source["note"] = "```\n<script>not executable</script>\n```"
        result = self.export("md")
        self.assertIn(b"````json", result.content)
        self.assertTrue(result.content.endswith(b"````\n"))

    def test_schema_rejects_unbounded_queries_and_arbitrary_files(self):
        invalid = [
            {"source": "filesystem", "path": "/etc/passwd"},
            {"source": "cluster_collection", "source_id": "../../secret"},
            {"source": "cluster_collection", "source_id": str(uuid4()), "filters": {"resource_ids": ["0"]}},
            {"source": "performance", "filters": {"from": "2026-10-01T00:00:00Z", "to": "2026-10-03T00:00:00Z"}},
            {"source": "performance", "filters": {"from": "2026-10-01T00:00:00"}},
            {"source": "performance", "filters": {"metric_ids": ["shell.command"]}},
            {"source": "performance", "filters": {"step": 1}},
            {"source": "benchmark_run", "source_id": str(uuid4()), "filters": {"scope": "other"}},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ExportRequest.model_validate(payload)
        with self.assertRaises(ExportError) as caught:
            safe_projection([{}] * 20001)
        self.assertEqual(caught.exception.status_code, 413)
        with self.assertRaises(ExportError):
            safe_projection({"nan": float("nan")})

    def test_cluster_export_uses_type_and_id_not_ambiguous_numeric_ids(self):
        collection = {"cluster_id": "lab", "fsid": FSID, "resources": [
            {"scope_type": "osd", "id": "0"}, {"scope_type": "pool", "id": "0"}],
            "metrics": [{"metric_id": "osd.used_kb", "scope_type": "osd", "resource_id": "0", "value": None},
                        {"metric_id": "pool.pg_num", "scope_type": "pool", "resource_id": "0", "value": 32}]}
        service = EvidenceExportService(self.settings)
        with patch("app.modules.cluster_metrics.api._service", return_value=Mock(get=lambda _: collection)):
            result = service.create(ExportRequest(source="cluster_collection", source_id=uuid4(),
                filters={"scope_type": "osd", "resource_ids": ["0"]}))
        data = json.loads(result.content)["data"]
        self.assertEqual(len(data["resources"]), 1)
        self.assertEqual([row["metric_id"] for row in data["metrics"]], ["osd.used_kb"])

    def test_cross_cluster_cannot_export(self):
        service = EvidenceExportService(self.settings)
        with self.assertRaises(ExportError):
            service._assert_cluster({"cluster_id": "elsewhere", "fsid": FSID})

    def test_unconfigured_performance_download_has_no_synthetic_values(self):
        settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False)
        result = EvidenceExportService(settings).create(ExportRequest(source="performance", filters={"source": "ceph"}))
        data = json.loads(result.content)["data"]
        self.assertIsNone(data["iops"]["total"])
        self.assertIsNone(data["captured_at"])

    def test_http_download_headers_bounded_slots_and_sanitized_failures(self):
        app = FastAPI()
        app.include_router(router)
        request = {"source": "cluster_collection", "source_id": str(uuid4()), "format": "zip"}
        with TestClient(app) as client, patch("app.modules.evidence_exports.api._service", return_value=self.service):
            response = client.post("/api/v1/exports", json=request)
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment; filename=", response.headers["content-disposition"])
            self.assertEqual(response.headers["x-export-sha256"], hashlib.sha256(response.content).hexdigest())
            self.assertEqual(response.headers["cache-control"], "no-store")
            _EXPORT_GATE.acquire(); _EXPORT_GATE.acquire()
            try:
                self.assertEqual(client.post("/api/v1/exports", json=request).status_code, 429)
            finally:
                _EXPORT_GATE.release(); _EXPORT_GATE.release()
            with patch.object(self.service, "create", side_effect=RuntimeError("secret database_url")):
                failed = client.post("/api/v1/exports", json=request)
                self.assertEqual(failed.status_code, 503)
                self.assertNotIn("database_url", failed.text)
            self.assertEqual(client.post("/api/v1/exports", json=request).status_code, 200)


if __name__ == "__main__":
    unittest.main()
