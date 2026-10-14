import unittest
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings


def settings(**overrides):
    values = {
        # Docker runtime defaults are deliberately read-only. Tests that
        # exercise optional legacy validation must opt into their lab policy.
        "app_env": "test",
        "execution_environment": "lab",
        "console_read_only": False,
        "console_auth_username": "",
        "console_auth_password_hash": None,
        "console_auth_password_hash_file": None,
        "rgw_endpoint_url": "http://rgw.invalid",
        "rgw_access_key": "test-access",
        "rgw_secret_key": "test-secret",
        "rgw_allowed_buckets": "",
        "rgw_stream_prefix_root": "",
        "rgw_affected_pools": "",
        "rbd_allowed_pools": "",
        "rbd_allowed_namespaces": "",
        "ceph_expected_fsid": None,
        "performance_source": "application_only",
        "performance_prometheus_url": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class SettingsTests(unittest.TestCase):
    def test_scope_defaults_are_fail_closed(self):
        configured = settings()

        self.assertEqual(configured.rgw_allowed_bucket_set, frozenset())
        self.assertEqual(configured.rgw_stream_prefix_root, "")
        self.assertEqual(configured.rbd_allowed_pool_set, frozenset())
        self.assertIsNone(configured.ceph_expected_fsid)
        self.assertTrue(configured.capacity_observe_only)
        self.assertIsNone(configured.capacity_fixed_metadata_bytes_per_object)
        self.assertIsNone(configured.capacity_emergency_maintenance_bytes)
        self.assertTrue(configured.performance_enabled)
        self.assertEqual(configured.performance_source, "application_only")
        self.assertIsNone(configured.performance_prometheus_url)
        self.assertIn("application/pdf", configured.rbd_allowed_preview_mime_set)
        self.assertIn("image/png", configured.rbd_allowed_preview_mime_set)
        self.assertGreaterEqual(configured.rbd_file_upload_max_bytes, configured.rbd_file_preview_max_bytes)

    def test_csv_allowlists_are_trimmed_and_deduplicated(self):
        configured = settings(rgw_allowed_buckets=" lab-b,lab-a, lab-b ")

        self.assertEqual(configured.rgw_allowed_buckets, "lab-a,lab-b")
        self.assertEqual(configured.rgw_allowed_bucket_set, frozenset({"lab-a", "lab-b"}))

    def test_stream_prefix_is_normalized_to_boundary(self):
        configured = settings(rgw_stream_prefix_root="console-jobs/run")

        self.assertEqual(configured.rgw_stream_prefix_root, "console-jobs/run/")

    def test_wildcard_allowlist_is_rejected(self):
        with self.assertRaises(ValidationError):
            settings(rgw_allowed_buckets="*")

    def test_unsafe_stream_prefix_is_rejected(self):
        for value in ("/console-jobs", "console-jobs/../other", "console\\jobs"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                settings(rgw_stream_prefix_root=value)

    def test_capacity_threshold_order_is_validated(self):
        with self.assertRaises(ValidationError):
            settings(
                capacity_throttle_start_ratio=0.69,
                capacity_admission_stop_ratio=0.68,
            )

    def test_staleness_window_cannot_be_shorter_than_polling(self):
        with self.assertRaises(ValidationError):
            settings(
                capacity_collector_interval_seconds=5,
                capacity_metrics_max_age_seconds=2,
            )

    def test_performance_prometheus_requires_url_and_expected_fsid(self):
        with self.assertRaises(ValidationError):
            settings(performance_source="prometheus")
        with self.assertRaises(ValidationError):
            settings(
                performance_source="prometheus",
                performance_prometheus_url="http://prometheus.invalid:9283",
            )

    def test_performance_window_and_staleness_cover_collection_interval(self):
        with self.assertRaises(ValidationError):
            settings(
                performance_collector_interval_seconds=30,
                performance_current_window_seconds=15,
            )
        with self.assertRaises(ValidationError):
            settings(
                performance_collector_interval_seconds=30,
                performance_current_window_seconds=30,
                performance_stale_after_seconds=20,
            )

    def test_prometheus_credentials_cannot_be_embedded_in_url(self):
        with self.assertRaises(ValidationError):
            settings(
                ceph_expected_fsid="11111111-2222-3333-4444-555555555555",
                performance_source="prometheus",
                performance_prometheus_url="http://user:secret@prometheus.invalid:9283",
            )

    def test_upgrade_mutations_require_upgrade_feature(self):
        with self.assertRaises(ValidationError):
            settings(upgrade_mutations_enabled=True, feature_upgrade=False)

    def test_upgrade_feature_dependency_check_is_fail_closed(self):
        configured = settings(feature_upgrade=True, feature_legacy_rgw=False)

        with self.assertRaisesRegex(ValueError, "CLUSTER_ID"):
            configured.validate_feature_dependencies()

    def test_upgrade_only_configuration_does_not_require_rgw(self):
        configured = settings(
            feature_upgrade=True,
            feature_legacy_rgw=False,
            feature_legacy_rbd=False,
            cluster_id="lab-a",
            ceph_expected_fsid="11111111-2222-3333-4444-555555555555",
            ceph_executor_token="executor-token-with-at-least-thirty-two-characters",
            rgw_endpoint_url=None,
            rgw_access_key=None,
            rgw_secret_key=None,
        )

        configured.validate_feature_dependencies()

    def test_enabled_legacy_rbd_requires_executor_identity(self):
        configured = settings(
            feature_upgrade=False,
            feature_legacy_rgw=False,
            feature_legacy_rbd=True,
            ceph_expected_fsid=None,
            ceph_executor_token=None,
            rbd_executor_token=None,
        )

        with self.assertRaisesRegex(ValueError, "CEPH_EXPECTED_FSID"):
            configured.validate_feature_dependencies()

    def test_upgrade_allowlists_reject_wildcards(self):
        with self.assertRaises(ValidationError):
            settings(upgrade_allowed_osds="0,*")

    def test_upgrade_inventory_freshness_is_positive_and_bounded(self):
        self.assertEqual(settings().upgrade_inventory_max_age_seconds, 45)
        with self.assertRaises(ValidationError):
            settings(upgrade_inventory_max_age_seconds=0)
        with self.assertRaises(ValidationError):
            settings(upgrade_inventory_max_age_seconds=86401)

    def test_executor_token_file_overrides_inline_compatibility_token(self):
        with tempfile.TemporaryDirectory() as root:
            token_file = Path(root) / "executor-token"
            token_file.write_text("file-token-with-at-least-thirty-two-characters", encoding="utf-8")

            configured = settings(
                ceph_executor_token="inline-token-with-at-least-thirty-two-characters",
                ceph_executor_token_file=token_file,
            )

            self.assertEqual(
                configured.effective_executor_token.get_secret_value(),
                "file-token-with-at-least-thirty-two-characters",
            )


if __name__ == "__main__":
    unittest.main()
