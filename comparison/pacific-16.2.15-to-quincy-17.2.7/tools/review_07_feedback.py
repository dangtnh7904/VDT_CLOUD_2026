"""Classify the new optional Ceph Tracker feedback path."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
targets = [
    "src/pybind/mgr/feedback/__init__.py",
    "src/pybind/mgr/feedback/model.py",
    "src/pybind/mgr/feedback/module.py",
    "src/pybind/mgr/feedback/service.py",
    "src/pybind/mgr/dashboard/controllers/feedback.py",
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/shared/feedback/feedback.component.html",
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/shared/feedback/feedback.component.ts",
    "src/pybind/mgr/dashboard/frontend/src/app/shared/api/feedback.service.ts",
]
reason = (
    "MGR-031: Quincy adds an optional feedback MGR module and Dashboard path. "
    "When enabled and a user explicitly submits an issue, subject/description and "
    "the selected Ceph Tracker API key are sent by HTTPS to tracker.ceph.com; the key "
    "can be persisted in MGR store. The Dashboard 'objects' project value has no "
    "matching Feedback.Project enum member ('object'), so that selection can fail. "
    "No background or automatic issue submission found."
)
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
for target in targets:
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "MGR-031"
    row["impact_reason"] = reason
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
