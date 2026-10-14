from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.config import Settings
from app.migrations.runner import migrate
from app.modules.cluster_metrics.repository import CollectionRepository
from app.modules.cluster_metrics.service import ClusterMetricsService
from app.modules.evidence_exports.models import ExportRequest
from app.modules.evidence_exports.service import EvidenceExportService
from test_cluster_metrics import FakeClient, FSID


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "set TEST_DATABASE_URL for export persistence tests")
class ExportRepositoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.conn = psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        schema = "export_test_" + uuid4().hex
        self.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        self.conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
        migrate(self.conn)
        self.settings = Settings(_env_file=None, feature_legacy_rgw=False, feature_legacy_rbd=False,
            cluster_id="lab-a",
            ceph_expected_fsid=FSID, evidence_root=Path(self.temp.name), upgrade_allowed_osds="0")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module in ("cluster_metrics", "evidence_exports", "sessions"):
            self.stack.enter_context(patch(f"app.modules.{module}.repository.connection", self.connection_factory))

    @contextmanager
    def connection_factory(self):
        yield self.conn

    def test_registered_collection_roundtrips_and_exports_verified_bytes(self):
        service = ClusterMetricsService(self.settings, CollectionRepository(), FakeClient())
        saved = service.create(scopes=["mon", "osd"], resource_ids=[], idempotency_key="persisted-observation-1")
        self.assertEqual(str(service.list()["items"][0]["id"]), saved["id"])
        self.assertEqual(service.get(UUID(saved["id"]))["resources"], saved["resources"])
        with patch("app.modules.cluster_metrics.api._service", return_value=service):
            for format in ("json", "csv", "md", "zip"):
                result = EvidenceExportService(self.settings).create(ExportRequest(source="cluster_collection", source_id=saved["id"], format=format))
                self.assertTrue(result.content)
                self.assertEqual(result.manifest["source_refs"][0]["sha256"], saved["artifact"]["sha256"])
        replay = service.create(scopes=["mon", "osd"], resource_ids=[], idempotency_key="persisted-observation-1")
        self.assertEqual(replay["id"], saved["id"])
        self.assertEqual(len(service.list()["items"]), 1)

