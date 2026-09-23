import os
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row


os.environ.setdefault("RGW_ENDPOINT_URL", "http://127.0.0.1:8080")
os.environ.setdefault("RGW_ACCESS_KEY", "unit-test")
os.environ.setdefault("RGW_SECRET_KEY", "unit-test")

from app.services.performance import (  # noqa: E402
    PerformanceTelemetryError,
    counter_sample,
    collect_application_sample,
    maintain_samples,
    parse_prometheus_counters,
    latest_sample,
    serialize_sample,
    store_sample,
)


FSID = "11111111-2222-3333-4444-555555555555"
CAPTURED = datetime(2026, 1, 1, 0, 0, 15, tzinfo=timezone.utc)
METRIC_NAMES = {
    "read_ops": "ceph_osd_op_r",
    "write_ops": "ceph_osd_op_w",
    "read_bytes": "ceph_osd_op_r_out_bytes",
    "write_bytes": "ceph_osd_op_w_in_bytes",
}


def prometheus_payload() -> str:
    rows = ["# TYPE ceph_osd_op_r counter"]
    for osd, base in ((0, 100), (1, 200)):
        rows.extend(
            [
                f'ceph_osd_op_r{{ceph_daemon="osd.{osd}"}} {base}',
                f'ceph_osd_op_w{{ceph_daemon="osd.{osd}"}} {base + 10}',
                f'ceph_osd_op_r_out_bytes{{ceph_daemon="osd.{osd}"}} {base * 1024}',
                f'ceph_osd_op_w_in_bytes{{ceph_daemon="osd.{osd}"}} {base * 2048}',
            ]
        )
    return "\n".join(rows)


class PrometheusParserTests(unittest.TestCase):
    def test_extracts_osd_counters_and_selected_metric_names(self):
        counters, names = parse_prometheus_counters(prometheus_payload())

        self.assertEqual(names, METRIC_NAMES)
        self.assertEqual(counters["0"]["read_ops"], 100)
        self.assertEqual(counters["1"]["write_bytes"], 200 * 2048)

    def test_falls_back_to_pacific_total_byte_counter_names(self):
        payload = prometheus_payload().replace("op_r_out_bytes", "op_out_bytes").replace(
            "op_w_in_bytes", "op_in_bytes"
        )

        counters, names = parse_prometheus_counters(payload)

        self.assertEqual(names["read_bytes"], "ceph_osd_op_out_bytes")
        self.assertEqual(names["write_bytes"], "ceph_osd_op_in_bytes")
        self.assertEqual(len(counters), 2)

    def test_duplicate_daemon_series_is_rejected_instead_of_double_counted(self):
        duplicate = prometheus_payload() + '\nceph_osd_op_r{ceph_daemon="osd.0"} 999\n'

        with self.assertRaisesRegex(PerformanceTelemetryError, "duplicate"):
            parse_prometheus_counters(duplicate)


class CounterRateTests(unittest.TestCase):
    def sample(self, current, previous, previous_time=None):
        return counter_sample(
            fsid=FSID,
            scope_type="cluster",
            scope_id=FSID,
            captured_at=CAPTURED,
            counters=current,
            previous_counters=previous,
            previous_captured_at=previous_time,
            metric_names=METRIC_NAMES,
        )

    def test_computes_read_write_and_total_rate_over_actual_elapsed_time(self):
        previous = {"read_ops": 100, "write_ops": 50, "read_bytes": 1000, "write_bytes": 2000}
        current = {"read_ops": 130, "write_ops": 65, "read_bytes": 25360, "write_bytes": 14240}

        sample = self.sample(current, previous, CAPTURED - timedelta(seconds=15))

        self.assertEqual(sample.read_iops, 2)
        self.assertEqual(sample.write_iops, 1)
        self.assertEqual(sample.total_iops, 3)
        self.assertEqual(sample.read_bytes_per_second, 1624)
        self.assertEqual(sample.write_bytes_per_second, 816)
        self.assertEqual(sample.total_bytes_per_second, 2440)
        self.assertFalse(sample.partial)

    def test_first_sample_is_partial_warmup_not_zero(self):
        current = {"read_ops": 1, "write_ops": 2, "read_bytes": 3, "write_bytes": 4}

        sample = self.sample(current, None)

        self.assertTrue(sample.partial)
        self.assertIsNone(sample.total_iops)
        self.assertEqual(sample.metadata["reasons"], ["WARMING_UP"])

    def test_counter_reset_is_flagged_without_negative_spike(self):
        previous = {"read_ops": 100, "write_ops": 50, "read_bytes": 1000, "write_bytes": 2000}
        current = {"read_ops": 1, "write_ops": 60, "read_bytes": 1100, "write_bytes": 2200}

        sample = self.sample(current, previous, CAPTURED - timedelta(seconds=15))

        self.assertTrue(sample.reset_detected)
        self.assertTrue(sample.partial)
        self.assertIsNone(sample.total_iops)
        self.assertEqual(sample.metadata["reasons"], ["COUNTER_RESET"])


class SerializationTests(unittest.TestCase):
    def test_stale_sample_is_explicit_and_raw_counters_are_not_exposed(self):
        row = {
            "source": "ceph",
            "sample_kind": "raw",
            "scope_type": "cluster",
            "scope_id": FSID,
            "captured_at": CAPTURED,
            "window_seconds": 15,
            "fresh": True,
            "reset_detected": False,
            "partial": False,
            "read_iops": 1.0,
            "write_iops": 2.0,
            "total_iops": 3.0,
            "read_bytes_per_second": 10.0,
            "write_bytes_per_second": 20.0,
            "total_bytes_per_second": 30.0,
            "read_latency_ms": None,
            "write_latency_ms": None,
            "average_latency_ms": None,
            "p50_latency_ms": None,
            "p95_latency_ms": None,
            "p99_latency_ms": None,
            "success_count": None,
            "error_count": None,
            "metadata": {"raw_counters": {"read_ops": 10}, "semantics": "ceph_client_io"},
        }

        payload = serialize_sample(row, now=CAPTURED + timedelta(seconds=60))

        self.assertEqual(payload["state"], "STALE")
        self.assertFalse(payload["fresh"])
        self.assertIn("STALE_SAMPLE", payload["reasons"])
        self.assertNotIn("raw_counters", payload["context"])

    def test_historical_sample_keeps_capture_validity_even_when_old(self):
        row = {
            "source": "application",
            "sample_kind": "raw",
            "scope_type": "cluster",
            "scope_id": "console",
            "captured_at": CAPTURED,
            "window_seconds": 15,
            "fresh": True,
            "reset_detected": False,
            "partial": False,
            "read_iops": 1.0,
            "write_iops": 2.0,
            "total_iops": 3.0,
            "read_bytes_per_second": 10.0,
            "write_bytes_per_second": 20.0,
            "total_bytes_per_second": 30.0,
            "read_latency_ms": None,
            "write_latency_ms": None,
            "average_latency_ms": 2.0,
            "p50_latency_ms": 1.0,
            "p95_latency_ms": 3.0,
            "p99_latency_ms": 4.0,
            "success_count": 1,
            "error_count": 0,
            "metadata": {},
        }

        payload = serialize_sample(
            row,
            now=CAPTURED + timedelta(days=1),
            enforce_current_freshness=False,
        )

        self.assertEqual(payload["state"], "FRESH")
        self.assertTrue(payload["fresh"])
        self.assertNotIn("STALE_SAMPLE", payload["reasons"])

    def test_unsupported_scope_is_unavailable_not_inferred(self):
        payload = latest_sample("ceph", "pool", "rbd-lab")

        self.assertEqual(payload["state"], "UNAVAILABLE")
        self.assertEqual(payload["reasons"], ["UNSUPPORTED_SCOPE"])
        self.assertIsNone(payload["iops"]["total"])


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "set TEST_DATABASE_URL to run PostgreSQL performance tests",
)
class PerformancePersistenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row)
        self.conn.execute("SELECT 1")

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def test_application_window_matches_operation_count_and_bytes(self):
        captured = datetime.now(timezone.utc)
        rows = (
            ("PUT", True, 300, 3.0, "write-key"),
            ("GET", False, 150, 6.0, "read-key"),
        )
        for kind, success, byte_count, latency, key in rows:
            self.conn.execute(
                """
                INSERT INTO operations (
                  kind, success, bytes_count, latency_ms, bucket, object_key,
                  target_type, target_id, created_at
                ) VALUES (%s, %s, %s, %s, 'performance-test', %s,
                          'RGW_OBJECT', %s, %s)
                """,
                (
                    kind,
                    success,
                    byte_count,
                    latency,
                    key,
                    f"performance-test:{uuid.uuid4()}",
                    captured - timedelta(seconds=5),
                ),
            )

        sample = collect_application_sample(captured_at=captured, db_conn=self.conn)

        self.assertAlmostEqual(sample.read_iops, 1 / sample.window_seconds)
        self.assertAlmostEqual(sample.write_iops, 1 / sample.window_seconds)
        self.assertAlmostEqual(sample.total_bytes_per_second, 450 / sample.window_seconds)
        self.assertEqual(sample.success_count, 1)
        self.assertEqual(sample.error_count, 1)
        self.assertAlmostEqual(sample.average_latency_ms, 4.5)

    def test_raw_sample_is_persisted_and_rolled_up(self):
        captured = datetime.now(timezone.utc) - timedelta(minutes=2)
        sample = counter_sample(
            fsid=str(uuid.uuid4()),
            scope_type="cluster",
            scope_id="integration-test",
            captured_at=captured,
            counters={"read_ops": 130, "write_ops": 65, "read_bytes": 25360, "write_bytes": 14240},
            previous_counters={"read_ops": 100, "write_ops": 50, "read_bytes": 1000, "write_bytes": 2000},
            previous_captured_at=captured - timedelta(seconds=15),
            metric_names=METRIC_NAMES,
        )
        sample = replace(sample, source="application")

        sample_id = store_sample(sample, db_conn=self.conn)
        maintenance = maintain_samples(catch_up=True, db_conn=self.conn)

        stored = self.conn.execute(
            "SELECT * FROM performance_samples WHERE id=%s", (sample_id,)
        ).fetchone()
        rollup = self.conn.execute(
            """
            SELECT * FROM performance_samples
            WHERE fsid=%s AND sample_kind='rollup_1m'
              AND source='application' AND scope_id='integration-test'
            """,
            (sample.fsid,),
        ).fetchone()
        self.assertEqual(stored["sample_kind"], "raw")
        self.assertEqual(stored["total_iops"], 3)
        self.assertIsNotNone(rollup)
        self.assertGreaterEqual(maintenance["rollups_written"], 1)


if __name__ == "__main__":
    unittest.main()
