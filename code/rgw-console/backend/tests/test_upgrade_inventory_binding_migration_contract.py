from __future__ import annotations

import unittest
from importlib import resources


class UpgradeInventoryBindingMigrationContractTests(unittest.TestCase):
    def test_binding_is_append_only_evidence_linked_to_plan_revision(self):
        sql = resources.files("app.migrations.versions").joinpath(
            "0017_upgrade_inventory_bindings.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE upgrade_inventory_bindings", sql)
        self.assertIn("collection_id UUID NOT NULL REFERENCES osd_inventory_collections", sql)
        self.assertIn("run_id UUID NOT NULL REFERENCES upgrade_runs", sql)
        self.assertIn("plan_revision BIGINT NOT NULL", sql)
        self.assertIn("artifact_sha256 TEXT NOT NULL", sql)
        self.assertIn("readiness_result = 'READY'", sql)
        self.assertIn("ADD COLUMN osd_inventory_binding_id UUID", sql)
        self.assertNotIn("ON DELETE CASCADE", sql)


if __name__ == "__main__":
    unittest.main()
