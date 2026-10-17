"""Classify inspected status contract and insights compatibility changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
findings = {
    "src/pybind/mgr/status/module.py": (
        "affect",
        "MGR-027;MGR-028",
        "MGR-027: fs status JSON mds_version changes from a string for one MDS version "
        "(and absent for zero versions) to a list of objects (or an empty list). "
        "MGR-028: During the documented asynchronous metadata gap, Quincy passes an "
        "empty defaultdict to get_metadata then asserts it is truthy; fs status or osd status "
        "can raise AssertionError where Pacific used a seeded fallback dict."
    ),
    "src/pybind/mgr/insights/health.py": (
        "trivial",
        "",
        "T07-insights-health-style: Endpoint changes are whitespace and formatting only; "
        "health slot timing, accumulation, persistence, and serialization expressions match."
    ),
    "src/pybind/mgr/insights/module.py": (
        "trivial",
        "",
        "T07-insights-crash-call: Adapts the internal crash-module call from command "
        "dispatch to do_json_report(hours); matching endpoint crash handlers still return "
        "the same (0, '', sorted JSON counts) tuple for valid integer hours. Other hunks "
        "are formatting only; no independent insights report change found."
    ),
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
for target, (impact, finding_id, reason) in findings.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = impact
    row["finding_id"] = finding_id
    row["impact_reason"] = reason
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
