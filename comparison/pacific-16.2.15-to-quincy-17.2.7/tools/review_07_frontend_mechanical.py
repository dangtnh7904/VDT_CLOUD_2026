"""Classify Dashboard source rows confined to reviewed mechanical commits."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def target_only(commit: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, "v16.2.15", check=False).returncode != 0
    assert git("merge-base", "--is-ancestor", commit, "v17.2.7", check=False).returncode == 0


bootstrap = "fec59bec03195559a0f2589a397d2642a4045b27"
aria = "5081dd7689d7551ad7d9d95fa0fde461db8db20c"
eslint = "7691aea5976f600a49117730fa1b3b19656f414a"
mechanical_commits = {bootstrap, aria, eslint}
for commit in mechanical_commits:
    target_only(commit)

assert git("show", "-s", "--format=%s", bootstrap).stdout.strip() == "mgr/dashboard: migrate to bootstrap 5"
assert "accessibility" in git("show", "-s", "--format=%s", aria).stdout.lower()
assert git("show", "-s", "--format=%s", eslint).stdout.strip() == "mgr/dashboard: tslint to eslint migration"

# These guards describe the inspected scope of the three commits. They prevent
# the allowlist from silently being reused for a commit with a different patch.
for commit in mechanical_commits:
    changed_files = [
        path
        for path in git("show", "--format=", "--name-only", commit).stdout.splitlines()
        if path.strip()
    ]
    assert changed_files
    assert all(
        path.startswith("src/pybind/mgr/dashboard/frontend/")
        or (commit == eslint and path in {"CodingStyle", "doc/dev/developer_guide/dash-devel.rst"})
        for path in changed_files
    )

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

prefix = "MGR-FRONTEND-MECHANICAL-04:"
frontend_prefix = "src/pybind/mgr/dashboard/frontend/"
selected: dict[str, set[str]] = {}
history = git(
    "log",
    "--format=@@@%H",
    "--name-only",
    "v16.2.15..v17.2.7",
    "--",
    frontend_prefix,
).stdout.splitlines()
path_commits: dict[str, set[str]] = {}
current_commit = ""
for line in history:
    if line.startswith("@@@"):
        current_commit = line[3:].strip()
    elif line.strip():
        assert current_commit
        path_commits.setdefault(line.strip(), set()).add(current_commit)

for row in rows:
    path = row["path"]
    if not path.startswith(frontend_prefix) or not path.endswith((".ts", ".html")):
        continue
    if row["upgrade_impact"] and not row["impact_reason"].startswith(prefix):
        continue
    commits = path_commits.get(path, set())
    if commits and commits <= mechanical_commits:
        selected[path] = commits

assert selected
assert all(commits <= mechanical_commits for commits in selected.values())
assert any(bootstrap in commits for commits in selected.values())
assert any(aria in commits for commits in selected.values())
assert any(eslint in commits for commits in selected.values())

reason = (
    prefix
    + " Every commit touching this endpoint between the compared tags belongs "
    "to the inspected Bootstrap 5 class migration, ARIA/tab/listitem "
    "accessibility migration, or TSLint-to-ESLint cleanup. API calls, state "
    "mutation, health values and rollout commands are unchanged."
)

newly_classified = 0
for row in rows:
    if row["path"] not in selected:
        continue
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial", row["path"]
        assert row["finding_id"] == "", row["path"]
        assert row["impact_reason"] == reason, row["path"]
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = reason
        newly_classified += 1

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
unclassified = sum(not row["upgrade_impact"] for row in rows)
assert affect >= 229 and trivial >= 296 and unclassified <= 201
print(f"Mechanical frontend endpoints in cluster: {len(selected)}")
print(f"Newly classified as trivial: {newly_classified}")
for path in sorted(selected):
    labels = []
    if bootstrap in selected[path]:
        labels.append("bootstrap")
    if aria in selected[path]:
        labels.append("aria")
    if eslint in selected[path]:
        labels.append("eslint")
    print(f"  {path} [{','.join(labels)}]")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
