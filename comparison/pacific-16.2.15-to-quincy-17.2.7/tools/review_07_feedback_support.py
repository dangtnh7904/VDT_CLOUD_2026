"""Classify feedback entry point, empty style asset, and supporting tests."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
findings = {
    "src/pybind/mgr/dashboard/frontend/src/app/core/navigation/dashboard-help/dashboard-help.component.html": (
        "affect", "MGR-031",
        "MGR-031: Adds the Report an issue button to Dashboard Help, the user action "
        "that opens the optional feedback form; other changes affect accessibility/API "
        "Docs presentation but do not alter feedback submission."
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/core/navigation/dashboard-help/dashboard-help.component.ts": (
        "affect", "MGR-031",
        "MGR-031: openFeedbackModal creates FeedbackComponent only after the user "
        "selects Report an issue; no automatic issue submission is introduced here."
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/shared/feedback/feedback.component.scss": (
        "trivial", "",
        "T07-feedback-empty-style: New SCSS file is empty; no rendered style or upgrade behavior."
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/shared/feedback/feedback.component.spec.ts": (
        "trivial", "",
        "T07-feedback-ui-tests: New tests check modal creation, disabled form when the "
        "module is unavailable, and invalid-key errors; they do not change runtime or "
        "an executed upgrade acceptance gate."
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/shared/api/feedback.service.spec.ts": (
        "trivial", "",
        "T07-feedback-service-tests: New HTTP mocks verify GET key-existence and POST "
        "issue request shape; no production path or upgrade acceptance gate changes."
    ),
    "qa/tasks/mgr/dashboard/test_feedback.py": (
        "trivial", "",
        "T07-feedback-QA: New optional Dashboard QA tests enable feedback and exercise "
        "API-key CRUD plus invalid issue requests; corroborates MGR-031 but is not an "
        "upgrade recipe, rollout filter, or acceptance test used by this suite."
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

module = "src/pybind/mgr/dashboard/frontend/src/app/ceph/dashboard/dashboard.module.ts"
matching = [row for row in rows if row["path"] == module]
assert len(matching) == 1
row = matching[0]
assert row["upgrade_impact"] == "affect" and row["finding_id"] == "MGR-020"
row["finding_id"] = "MGR-020;MGR-031"
row["impact_reason"] += (
    " MGR-031: Also declares FeedbackComponent and imports reactive form support for "
    "the optional issue-report modal."
)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
