"""Classify the remaining Dashboard block/RBD component endpoints."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"
prefix = "src/pybind/mgr/dashboard/frontend/src/app/ceph/block/"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, relative: str) -> str:
    return git("show", f"{tag}:{prefix}{relative}").stdout


def target_only(commit: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, "v16.2.15", check=False).returncode != 0
    assert git("merge-base", "--is-ancestor", commit, "v17.2.7", check=False).returncode == 0


for commit in (
    "83f15e764421960a4fc1a2db99b22b8f76fff9f2",
    "ad3b4d3c30009d8bd5bcfa97d5607a1dd759d79b",
    "3ca9ca7e215562912daf00ca3cca40dbc5d560b5",
    "503c58b3f8417316ed279a573f553031dc9a97ea",
    "9c636cb8668816a697237ff8ea06ec883557336c",
):
    target_only(commit)

base_overview = show("v16.2.15", "mirroring/overview/overview.component.ts")
target_overview = show("v17.2.7", "mirroring/overview/overview.component.ts")
assert "disable: () => this.peersExist" in base_overview
assert "disable: () => false" in target_overview

base_form = show("v16.2.15", "rbd-form/rbd-form.component.ts")
target_form = show("v17.2.7", "rbd-form/rbd-form.component.ts")
assert "peerConfigured" not in base_form
assert "peerConfigured = false" in target_form
assert "getPeerForPool(poolName)" in target_form
assert "mirroring: new FormControl(false)" in base_form
assert "mirroring: new FormControl('')" in target_form
target_form_html = show("v17.2.7", "rbd-form/rbd-form.component.html")
assert '[attr.disabled]="(peerConfigured === false) ? true : null"' in target_form_html

base_list = show("v16.2.15", "rbd-list/rbd-list.component.ts")
target_list = show("v17.2.7", "rbd-list/rbd-list.component.ts")
assert "Next Scheduled Snapshot" not in base_list
assert "Next Scheduled Snapshot" in target_list
assert "this.selection.first().mirror_mode === 'Disabled'" not in base_list
assert "this.selection.first().mirror_mode === 'Disabled'" in target_list
assert "error.preventDefault();" not in base_list
assert "error.preventDefault();" in target_list
target_list_html = show("v17.2.7", "rbd-list/rbd-list.component.html")
assert "#scheduleTpl" in target_list_html
assert "<cd-usage-bar" in target_list_html

base_snap_form = show("v16.2.15", "rbd-snapshot-form/rbd-snapshot-form-modal.component.ts")
target_snap_form = show("v17.2.7", "rbd-snapshot-form/rbd-snapshot-form-modal.component.ts")
assert "getPeerForPool" not in base_snap_form
assert "getPeerForPool(this.poolName)" in target_snap_form
assert "clearValidators()" in target_snap_form
target_snap_html = show("v17.2.7", "rbd-snapshot-form/rbd-snapshot-form-modal.component.html")
assert '[attr.disabled]="!(peerConfigured.length > 0) ? true : null"' in target_snap_html

base_actions = show("v16.2.15", "rbd-snapshot-list/rbd-snapshot-actions.model.ts")
target_actions = show("v17.2.7", "rbd-snapshot-list/rbd-snapshot-actions.model.ts")
assert "getProtectDisableDesc" not in base_actions
assert "getProtectDisableDesc" in target_actions
assert "The layering feature needs to be enabled on parent image" in target_actions

target_snap_list = show("v17.2.7", "rbd-snapshot-list/rbd-snapshot-list.component.ts")
assert target_snap_list.count("primary: boolean") == 1
assert target_snap_list.count("primary") == 1

affect_paths = {
    "mirroring/overview/overview.component.ts",
    "rbd-form/rbd-form.component.html",
    "rbd-form/rbd-form.component.ts",
    "rbd-list/rbd-list.component.html",
    "rbd-list/rbd-list.component.ts",
    "rbd-snapshot-form/rbd-snapshot-form-modal.component.html",
    "rbd-snapshot-form/rbd-snapshot-form-modal.component.ts",
    "rbd-snapshot-list/rbd-snapshot-actions.model.ts",
}
trivial_paths = {
    "iscsi-target-form/iscsi-target-form.component.html",
    "iscsi-target-form/iscsi-target-form.component.ts",
    "iscsi-target-image-settings-modal/iscsi-target-image-settings-modal.component.html",
    "mirroring/overview/overview.component.html",
    "mirroring/pool-edit-mode-modal/pool-edit-mode-modal.component.html",
    "rbd-details/rbd-details.component.html",
    "rbd-form/rbd-feature.interface.ts",
    "rbd-namespace-form/rbd-namespace-form-modal.component.html",
    "rbd-performance/rbd-performance.component.html",
    "rbd-snapshot-list/rbd-snapshot-list.component.ts",
}
assert len(affect_paths) == 8
assert len(trivial_paths) == 10
assert not affect_paths & trivial_paths

affect_reason = (
    "MGR-055: Dashboard changes RBD mirroring controls and acceptance signals: "
    "peer presence now gates schedules/mirror snapshots, import-token action "
    "availability changes, list columns split usage/next snapshot, promote/demote "
    "is blocked when mirroring is disabled, and snapshot protection validates "
    "layering. Active-MGR version can therefore change the visible/actionable UI."
)
trivial_reason = (
    "MGR-FRONTEND-RBD-SUPPORT-05: Endpoint diff is confined to Bootstrap/nav/form "
    "markup, labels/helpers, lint comments or an unused primary input. It adds no "
    "RBD/RGW/iSCSI service call, state mutation or independent rollout signal; "
    "the functional RBD control changes are isolated in MGR-055."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}

for relative in affect_paths:
    path = prefix + relative
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect", path
        assert row["finding_id"] == "MGR-055", path
        assert row["impact_reason"] == affect_reason, path
    else:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-055"
        row["impact_reason"] = affect_reason

for relative in trivial_paths:
    path = prefix + relative
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial", path
        assert row["finding_id"] == "", path
        assert row["impact_reason"] == trivial_reason, path
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial_reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
unclassified = sum(not row["upgrade_impact"] for row in rows)
assert affect >= 237 and trivial >= 334 and unclassified <= 155
print("Classified Dashboard block/RBD controls: 8 affect, 10 trivial")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
