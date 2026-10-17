"""Classify inspected balancer pool-list pruning behavior."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
target = "src/pybind/mgr/balancer/module.py"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert sum(row["path"] == target for row in rows) == 1
for row in rows:
    if row["path"] == target:
        assert not row["upgrade_impact"]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-026"
        row["impact_reason"] = (
            "MGR-026: When restricted balancer pool_ids include a deleted pool, "
            "Pacific pool ls joins integer IDs and raises TypeError; Quincy casts IDs to strings "
            "before pruning the persisted list. Other changed hunks are mainly Option/CLICommand "
            "and type refactors; no general balancing-algorithm claim."
        )
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
