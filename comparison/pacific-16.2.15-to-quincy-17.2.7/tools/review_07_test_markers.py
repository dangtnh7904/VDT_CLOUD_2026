"""Classify inspected removed utility test and empty Rook test marker."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
reasons = {
    "src/pybind/mgr/tests/test_mgr_util.py": (
        "T07-mgr-util-test-delete: Removes the old parametrized formatter test. "
        "Its cases cover 90m, 190m, 3h, 3d and 3y, not the 24-48h duration in "
        "MGR-029; this test is not an executed upgrade gate."
    ),
    "src/pybind/mgr/rook/tests/__init__.py": (
        "T07-rook-test-marker: Adds a zero-byte Python test-package marker. "
        "The MGR tox general pytest profile excludes the Rook test tree; this "
        "marker adds no runtime Rook behavior or upgrade acceptance step."
    ),
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
for target, reason in reasons.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "trivial"
    row["impact_reason"] = reason
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
