"""Reclassify optional issue reporting after applying the upgrade-impact gate."""

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
    "src/pybind/mgr/dashboard/frontend/src/app/core/navigation/dashboard-help/dashboard-help.component.html",
    "src/pybind/mgr/dashboard/frontend/src/app/core/navigation/dashboard-help/dashboard-help.component.ts",
]
reason = (
    "T07-feedback-optional-feature: Quincy adds a Ceph Tracker issue reporter, "
    "Dashboard entry point and API-key store, but sending an issue requires an "
    "explicit user action and feedback-module enablement. No link to this upgrade's "
    "rollout, continuity, rollback, or acceptance gate is established. The frontend "
    "'objects' versus backend 'object' mismatch affects only this optional reporter."
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
    assert row["upgrade_impact"] == "affect" and row["finding_id"] == "MGR-031"
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = reason

module = "src/pybind/mgr/dashboard/frontend/src/app/ceph/dashboard/dashboard.module.ts"
matching = [row for row in rows if row["path"] == module]
assert len(matching) == 1
row = matching[0]
assert row["upgrade_impact"] == "affect" and row["finding_id"] == "MGR-020;MGR-031"
row["finding_id"] = "MGR-020"
row["impact_reason"] = row["impact_reason"].split(" MGR-031:", 1)[0]

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
