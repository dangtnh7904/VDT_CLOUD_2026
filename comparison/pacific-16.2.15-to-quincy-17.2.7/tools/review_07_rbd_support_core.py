"""Classify verified RBD support command-permission and callback differences."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
findings = {
    "src/pybind/mgr/rbd_support/module.py": (
        "affect", "MGR-033",
        "MGR-033: rbd task cancel command descriptor changes from perm r in Pacific "
        "to CLIWriteCommand/perm w in Quincy; clients with only MGR read permission "
        "can lose the ability to cancel an RBD task during rollout. Other command "
        "decorator conversions largely preserve the endpoint call path."
    ),
    "src/pybind/mgr/rbd_support/mirror_snapshot_schedule.py": (
        "affect", "MGR-034",
        "MGR-034: On an async mirror-image-get-info failure, the RBD Python callback "
        "still provides an info dict. Pacific checks only info is None and can use "
        "its primary field; Quincy checks completion return value < 0 and closes "
        "the image before snapshot creation. Other mirror-mode/snapshot checks "
        "follow their binding return semantics."
    ),
    "src/pybind/mgr/rbd_support/common.py": (
        "trivial", "",
        "T07-rbd-common-types: Adds type hints and aliases around unchanged "
        "authorization, pool-key parsing and RBD-pool lookup expressions."
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
