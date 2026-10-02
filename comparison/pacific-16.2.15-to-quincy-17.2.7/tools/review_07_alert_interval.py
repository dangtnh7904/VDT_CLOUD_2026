"""Classify the alerts polling interval fallback in the endpoint diff."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = [row for row in rows if row["path"] == "src/pybind/mgr/alerts/module.py"]
assert len(selected) == 1 and not selected[0]["upgrade_impact"]
row = selected[0]
row["upgrade_impact"] = "affect"
row["finding_id"] = "MGR-005"
row["impact_reason"] = "MGR-005: Alerts polling wait uses interval or 60 in target versus interval directly in base; a configured zero/false interval changes health-email polling and MGR CPU behavior after activation."
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
