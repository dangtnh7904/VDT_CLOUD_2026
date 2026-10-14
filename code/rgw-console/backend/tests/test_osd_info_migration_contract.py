from __future__ import annotations

import unittest
from importlib import resources


class OsdInfoMigrationContractTests(unittest.TestCase):
    def test_schema_keeps_raw_artifact_collection_and_indexed_osds_separate(self):
        sql = resources.files("app.migrations.versions").joinpath(
            "0016_osd_info_collector.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE osd_inventory_collections", sql)
        self.assertIn("CREATE TABLE osd_inventory_records", sql)
        self.assertIn("evidence_artifact_id UUID UNIQUE", sql)
        self.assertIn("requested_osd_ids INTEGER[] NOT NULL", sql)
        self.assertIn("quality IN ('VALID', 'PARTIAL', 'INCONCLUSIVE')", sql)
        self.assertIn("total_bytes BIGINT", sql)
        self.assertIn("primary_count INTEGER", sql)
        self.assertNotIn("DEFAULT 0", sql)


if __name__ == "__main__":
    unittest.main()
