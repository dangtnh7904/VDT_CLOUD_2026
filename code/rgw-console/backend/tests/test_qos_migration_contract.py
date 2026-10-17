from pathlib import Path
import unittest


class QosMigrationContractTests(unittest.TestCase):
    def test_qos_schema_keeps_runs_segments_metrics_and_attempts_separate(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "migrations"
            / "versions"
            / "0015_qos_observer.sql"
        ).read_text(encoding="utf-8")

        for table in (
            "qos_runs",
            "qos_segments",
            "qos_metric_windows",
            "qos_benchmark_attempts",
        ):
            with self.subTest(table=table):
                self.assertIn(f"CREATE TABLE {table}", migration)

        self.assertIn("SERVICE_ONLY", migration)
        self.assertIn("NOT_COMPARABLE", migration)
        self.assertIn("RUNNER_FAILED", migration)
        self.assertNotIn("operation_result", migration)


if __name__ == "__main__":
    unittest.main()
