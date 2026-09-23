import unittest

from pydantic import ValidationError

from app.config import Settings


def settings(**overrides):
    values = {
        "rgw_endpoint_url": "http://rgw.invalid",
        "rgw_access_key": "test-access",
        "rgw_secret_key": "test-secret",
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


if __name__ == "__main__":
    unittest.main()
