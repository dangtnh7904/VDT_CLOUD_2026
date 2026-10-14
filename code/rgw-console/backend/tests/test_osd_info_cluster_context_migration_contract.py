from __future__ import annotations

import unittest
from importlib import resources


class OsdInfoClusterContextMigrationContractTests(unittest.TestCase):
    def test_cluster_context_fields_are_additive_and_null_preserving(self):
        sql = resources.files("app.migrations.versions").joinpath(
            "0019_osd_inventory_cluster_context.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("ALTER TABLE osd_inventory_collections", sql)
        for field in (
            "health_status TEXT",
            "health_checks JSONB",
            "osdmap_epoch BIGINT",
            "cluster_flags JSONB",
            "pool_summaries JSONB",
            "version_summary JSONB",
            "cluster_pg_count INTEGER",
            "cluster_osd_count INTEGER",
        ):
            with self.subTest(field=field):
                self.assertIn(field, sql)
        self.assertNotIn("DEFAULT 0", sql)
        self.assertIn("jsonb_typeof(pool_summaries) = 'array'", sql)
        self.assertIn("osdmap_epoch IS NULL OR osdmap_epoch >= 0", sql)


if __name__ == "__main__":
    unittest.main()
