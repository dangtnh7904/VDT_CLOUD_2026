"""Classify inspected Dashboard CRUSH-rule API version and supporting test."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/pybind/mgr/dashboard/controllers/crush_rule.py": "MGR-019: Dashboard CRUSH-rule list/get endpoints move to API v2; v1 callers receive HTTP 415 under version gate, and supporting test no longer requires old rule fields.",
}
trivial = {
    "qa/tasks/mgr/dashboard/test_crush_rule.py": "T07-crush-rule-api-test: Dashboard API test now requests v2 and stops requiring removed schema fields; corroborates MGR-019 but is not an upgrade acceptance recipe or runtime behavior.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = set(affect) | set(trivial)
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-019"
        row["impact_reason"] = affect[name]
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
