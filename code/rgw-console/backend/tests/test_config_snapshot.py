from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.platform.config import build_config_snapshot, resolve_settings


class ConfigSnapshotTests(unittest.TestCase):
    def base_settings(self, **overrides):
        values = {
            "feature_legacy_rgw": False,
            "feature_legacy_rbd": False,
            "feature_upgrade": True,
            "ceph_executor_token": "a-secret-token-that-is-at-least-32-characters",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    def test_non_secret_profile_is_resolved_below_explicit_values(self):
        with tempfile.TemporaryDirectory() as root:
            profile = Path(root) / "lab.yaml"
            profile.write_text(
                "\n".join(
                    [
                        "cluster_id: profile-cluster",
                        "cluster_profile_revision: profile-v1",
                        "ceph_expected_fsid: 11111111-2222-3333-4444-555555555555",
                        "upgrade_allowed_osds: '1,2'",
                    ]
                ),
                encoding="utf-8",
            )
            settings = self.base_settings(
                cluster_config_path=profile,
                cluster_id="environment-cluster",
            )

            resolved = resolve_settings(settings)

            self.assertEqual(resolved.cluster_id, "environment-cluster")
            self.assertEqual(resolved.cluster_profile_revision, "profile-v1")
            self.assertEqual(resolved.upgrade_allowed_osd_set, frozenset({"1", "2"}))

    def test_snapshot_is_deterministic_and_redacts_secrets(self):
        settings = self.base_settings(
            cluster_id="lab-a",
            ceph_expected_fsid="11111111-2222-3333-4444-555555555555",
            rgw_secret_key="do-not-persist",
            database_url="postgresql://user:password@database/db",
        )

        first = build_config_snapshot(settings)
        second = build_config_snapshot(settings)
        encoded = json.dumps(first.payload)

        self.assertEqual(first.config_hash, second.config_hash)
        self.assertNotIn("do-not-persist", encoded)
        self.assertNotIn("user:password", encoded)
        self.assertIn("[REDACTED]", encoded)

    def test_profile_rejects_secret_fields(self):
        with tempfile.TemporaryDirectory() as root:
            profile = Path(root) / "bad.yaml"
            profile.write_text("ceph_executor_token: secret", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported fields|must not contain"):
                resolve_settings(self.base_settings(cluster_config_path=profile))


if __name__ == "__main__":
    unittest.main()
