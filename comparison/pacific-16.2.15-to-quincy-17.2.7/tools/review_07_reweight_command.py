"""Classify inspected MGR reweight command and DaemonServer interface diff."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/mgr/MgrCommands.h": "MGR-013: Live reweight-by-utilization command changes no_increasing descriptor from CephChoices to CephBool; mixed-version CLI parsing and operator automation may differ.",
    "src/mgr/DaemonServer.cc": "MGR-013: Target reads no_increasing using CephBool-compatible parser that accepts legacy --no-increasing string; this determines reweight behavior during mixed-version command delivery.",
}
trivial = {
    "src/mgr/DaemonServer.h": "T07-daemonserver-typing: Fully qualifies standard-library container and string types in declarations; no changed request or response contract.",
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
        row["finding_id"] = "MGR-013"
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
