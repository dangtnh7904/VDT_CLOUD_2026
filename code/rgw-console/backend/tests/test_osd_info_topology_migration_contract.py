from __future__ import annotations

import unittest
from importlib import resources


class OsdInfoTopologyMigrationContractTests(unittest.TestCase):
    def test_topology_and_device_fields_are_additive_and_null_preserving(self):
        sql = resources.files("app.migrations.versions").joinpath(
            "0018_osd_inventory_topology_fields.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("ALTER TABLE osd_inventory_records", sql)
        for field in (
            "crush_location JSONB",
            "device_class TEXT",
            "public_ips JSONB",
            "cluster_ips JSONB",
            "db_device_path TEXT",
            "db_physical_devices JSONB",
            "wal_device_path TEXT",
            "wal_physical_devices JSONB",
            "device_ids JSONB",
            "container_image TEXT",
            "container_image_id TEXT",
        ):
            with self.subTest(field=field):
                self.assertIn(field, sql)
        self.assertNotIn("DEFAULT 0", sql)
        self.assertIn("jsonb_typeof(crush_location) = 'object'", sql)
        self.assertIn("jsonb_typeof(device_ids) = 'array'", sql)


if __name__ == "__main__":
    unittest.main()
