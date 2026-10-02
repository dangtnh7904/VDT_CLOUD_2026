import os
import unittest
from unittest.mock import patch


os.environ.setdefault("RGW_ENDPOINT_URL", "http://127.0.0.1:8080")
os.environ.setdefault("RGW_ACCESS_KEY", "unit-test")
os.environ.setdefault("RGW_SECRET_KEY", "unit-test")

from app.performance_collector import collect_and_maintain_once  # noqa: E402


class PerformanceCollectorTests(unittest.TestCase):
    @patch("app.performance_collector.logger")
    @patch("app.performance_collector.maintain_samples")
    @patch("app.performance_collector.collect_performance_once")
    def test_maintenance_runs_when_ceph_collection_fails(
        self, collect, maintain, logger
    ):
        collect.side_effect = ConnectionError("Prometheus unavailable")
        maintain.return_value = {"rollups_written": 1}

        collect_and_maintain_once()

        maintain.assert_called_once_with()
        logger.exception.assert_called_once_with("performance collection failed")


if __name__ == "__main__":
    unittest.main()
