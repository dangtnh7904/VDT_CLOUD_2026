"""Classify inspected MGR progress and Prometheus endpoint changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
findings = {
    "src/pybind/mgr/progress/module.py": ("MGR-002", "PG recovery event generation is now gated by new allow_pg_recovery_event option, default false; existing enabled progress module no longer processes OSDMap recovery events by default."),
    "src/pybind/mgr/prometheus/module.py": ("MGR-003", "Exporter adds per-device-class capacity and blocklist metrics, changes scrape-time blocklist command and repaired-object metric update, and sets explicit server_addr default; dashboard/alert consumers and scrape availability need validation."),
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in findings} == set(findings)
for row in rows:
    if row["path"] in findings:
        assert not row["upgrade_impact"], row["path"]
        finding_id, reason = findings[row["path"]]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding_id
        row["impact_reason"] = f"{finding_id}: {reason}"
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
