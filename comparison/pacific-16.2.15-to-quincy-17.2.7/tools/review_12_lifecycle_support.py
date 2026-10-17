"""Verify general RGW lifecycle/notification QA and maintainer metadata rows."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


def is_ancestor(commit: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, tag],
        check=False,
    )
    assert result.returncode in (0, 1)
    return result.returncode == 0


def tree_paths(tag: str) -> set[str]:
    return set(
        subprocess.check_output(
            ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", tag],
            text=True,
            encoding="utf-8",
        ).splitlines()
    )


lifecycle_commit = "6c767cf140d637d2e7a743364fd1f10c9f1e90ec"
notify_commit = "3084db26d594fc1e805e63f1be0af12d5b4a0d1c"
maintainers_commit = "50e4f2b7025a38006bd5b41477c4936e036e7bd5"
for commit in (lifecycle_commit, notify_commit, maintainers_commit):
    assert not is_ancestor(commit, "v16.2.15")
    assert is_ancestor(commit, "v17.2.7")

base_paths = tree_paths("v16.2.15")
target_paths = tree_paths("v17.2.7")
lifecycle_paths = {
    "qa/suites/rgw/lifecycle/+",
    "qa/suites/rgw/lifecycle/.qa",
    "qa/suites/rgw/lifecycle/cluster.yaml",
    "qa/suites/rgw/lifecycle/overrides.yaml",
    "qa/suites/rgw/lifecycle/supported-random-distro$",
    "qa/suites/rgw/lifecycle/tasks/rgw_s3tests.yaml",
}
assert lifecycle_paths.isdisjoint(base_paths)
assert lifecycle_paths <= target_paths

task = show("v17.2.7", "qa/suites/rgw/lifecycle/tasks/rgw_s3tests.yaml")
assert "force-branch: ceph-quincy" in task
assert 'extra_attrs: ["lifecycle"]' in task
assert "rgw lc debug interval: 10" in task
assert "upgrade-task" not in task
assert "rgw-multisite" not in task
assert show("v17.2.7", "qa/suites/rgw/lifecycle/.qa").strip() == "../.qa"
assert (
    show("v17.2.7", "qa/suites/rgw/lifecycle/supported-random-distro$").strip()
    == ".qa/distros/supported-random-distro$"
)

notify = show("v17.2.7", "qa/suites/rgw/multisite/notify.yaml")
assert "disable notifications on one zone per cluster" in notify
assert "rgw data notify interval msec: 0" in notify
notify_message = subprocess.check_output(
    ["git", "-C", str(repo), "show", "-s", "--format=%B", notify_commit],
    text=True,
    encoding="utf-8",
)
assert "verify that tests don't rely on notifications to" in notify_message
assert "succeed" in notify_message

maintainers = show("v17.2.7", "src/rgw/MAINTAINERS.md")
assert maintainers.startswith("# RGW Maintainers")
assert "default assignee for related tracker issues and pull requests" in maintainers
assert "rgw orchestration, admin APIs" in maintainers


new_rows = {
    "qa/suites/rgw/lifecycle/+": (
        "trivial",
        "",
        "RGW-LIFECYCLE-QA-01: Empty suite facet marker for the new single-version lifecycle test; its R100 source is an unrelated empty upgrade marker selected only by rename heuristics.",
    ),
    "qa/suites/rgw/lifecycle/.qa": (
        "trivial",
        "",
        "RGW-LIFECYCLE-QA-01: Symlink exposes the standard QA facet tree to the new lifecycle suite; it does not define or execute a version upgrade.",
    ),
    "qa/suites/rgw/lifecycle/cluster.yaml": (
        "trivial",
        "",
        "RGW-LIFECYCLE-QA-01: Defines a normal one-RGW Beast test cluster with three OSDs and no old/new daemon roles or upgrade task.",
    ),
    "qa/suites/rgw/lifecycle/overrides.yaml": (
        "trivial",
        "",
        "RGW-LIFECYCLE-QA-01: Test-only KMS keys, lifecycle debug interval and storage classes support lifecycle s3tests; no mixed-version or upgrade acceptance path is added.",
    ),
    "qa/suites/rgw/lifecycle/supported-random-distro$": (
        "trivial",
        "",
        "RGW-LIFECYCLE-QA-01: Standard supported-random-distro symlink for the single-version lifecycle suite, with no upgrade-specific selection.",
    ),
    "qa/suites/rgw/lifecycle/tasks/rgw_s3tests.yaml": (
        "trivial",
        "",
        "RGW-LIFECYCLE-QA-01: Runs Quincy lifecycle-tagged s3tests with debug interval/storage classes but contains no upgrade-task, Pacific artifact, version skew or rollback gate.",
    ),
    "qa/suites/rgw/multisite/notify.yaml": (
        "trivial",
        "RGW-003",
        "RGW-003 support: General multisite QA disables async notifications on one zone to prove polling convergence; it corroborates interval-zero behavior but is not the dedicated Pacific-to-Quincy upgrade recipe.",
    ),
    "src/rgw/MAINTAINERS.md": (
        "trivial",
        "",
        "RGW-MAINTAINERS-01: Adds human ownership/default-assignee contacts only; it changes no build, daemon, configuration, persisted state or upgrade validation workflow.",
    ),
}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for path, (impact, finding, reason) in new_rows.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified lifecycle/notification QA and maintainer metadata: 8 trivial")
