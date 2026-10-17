"""Classify screened iSCSI refactor and RBD mirroring status changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
base = "src/pybind/mgr/dashboard/"
decisions = {
    "controllers/iscsi.py": (
        "trivial", "",
        "T07-iscsi-refactor: Commit 7ea1200fb5c extracts overview, delete, "
        "create and validation loops into helpers while preserving gateway/"
        "disk/client/group order and conditions; RequestException mapping moves "
        "unchanged to handle_request_error. No new upgrade execution path."
    ),
    "services/exception.py": (
        "trivial", "",
        "T07-iscsi-refactor: New handle_request_error copies the prior "
        "RequestException JSON message/DashboardException mapping from "
        "IscsiTarget._create; only that controller calls it."
    ),
    "tests/test_iscsi.py": (
        "trivial", "",
        "T07-iscsi-unit: Adds mocked validation, overview, creation and error "
        "cases for the refactor; no executed upgrade recipe or independent "
        "acceptance gate is changed."
    ),
    "controllers/rbd_mirroring.py": (
        "affect", "MGR-048",
        "T07-rbd-mirror-health: Dashboard pool health changes from daemon "
        "image warning/error counts plus leader presence to librbd "
        "mirror_image_status_summary and daemon callouts; enabled pool with "
        "empty summary/no daemon can show OK. Per-image mirror mode now opens "
        "each image for status response."
    ),
    "tests/test_rbd_mirroring.py": (
        "trivial", "",
        "T07-rbd-mirror-unit: Mock tests cover new pool-health aggregation "
        "and changed summary warning count for MGR-048; no independent "
        "upgrade acceptance recipe."
    ),
    "frontend/src/app/ceph/block/mirroring/image-list/image-list.component.html": (
        "affect", "MGR-048",
        "T07-rbd-mirror-view: Syncing-image entries-behind-primary now "
        "shows a dash for snapshot mode and the value for journal mode, "
        "changing Dashboard mirroring validation signal."
    ),
    "frontend/src/app/ceph/block/mirroring/image-list/image-list.component.ts": (
        "affect", "MGR-048",
        "T07-rbd-mirror-view: Binds mode-sensitive entries-behind-primary "
        "template to the syncing-image column, using mirror_mode newly "
        "returned by MGR-048 backend."
    ),
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for relative, (impact, finding, reason) in decisions.items():
    target = base + relative
    matches = [row for row in rows if row["path"] == target]
    assert len(matches) == 1, target
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], target
    row["upgrade_impact"] = impact
    row["finding_id"] = finding
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
