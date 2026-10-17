"""Classify the new per-node ceph-exporter implementation."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
prefix = "src/exporter/"
affect = {
    prefix + "DaemonMetricCollector.cc": "MGR-021: New optional exporter polls local daemon admin sockets for perf dump/schema and config, filters by priority, adds process metrics from /proc, and publishes a cached text snapshot; this changes monitoring validation only when deployed/scraped.",
    prefix + "DaemonMetricCollector.h": "MGR-021: Defines the collector, metric builders and mutex-protected snapshot used by the new per-node metrics endpoint.",
    prefix + "ceph_exporter.cc": "MGR-021: New ceph-exporter executable parses socket directory, bind address, HTTP port, priority and collection period and starts collector plus HTTP thread.",
    prefix + "http_server.cc": "MGR-021: New HTTP server serves collector snapshot at /metrics; missing paths return 405 and bind failure exits the exporter process.",
    prefix + "http_server.h": "MGR-021: Declares the HTTP thread entry point called by the new exporter daemon.",
    prefix + "util.cc": "MGR-021: New file reader supplies daemon pid data and timing helper used in collector scrape/process metrics.",
    prefix + "util.h": "MGR-021: Declares file reader and timer used by collector when constructing the scrape snapshot.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in affect} == set(affect)
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-021"
        row["impact_reason"] = affect[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
