"""Classify frontend endpoints confined to reviewed accessibility/markup commits."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"
frontend_prefix = "src/pybind/mgr/dashboard/frontend/"


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


reviewed = {
    "fec59bec03195559a0f2589a397d2642a4045b27",  # Bootstrap 5 markup
    "5081dd7689d7551ad7d9d95fa0fde461db8db20c",  # tab/listitem ARIA
    "7691aea5976f600a49117730fa1b3b19656f414a",  # TSLint -> ESLint
    "fa6fb0087cf6733c6b70bcd38a408978e9ab14de",  # duplicate i18n ids
    "9ddf0536d7ed9382603a00a707eefa9f629d3d6f",  # validation icon layout
    "c1ac59db32a0738ef05d7af2756f0777d20f28a3",  # Grafana accessibility
    "7e5e38b1252cd8eae89bce3c26bedeca5ee8a3c8",  # health-page accessibility
    "8c1605604f327b77f3677737dacdeb4dc4e8a3f6",  # progress-bar accessibility
    "f3fa79a256516ee4a4c755edd038cea82a489572",  # navigation accessibility
    "0f15976139efcbf5ef039a05f9e9a8f6b3587bda",  # button accessibility
    "a6e395243584a34d758266798d0a7620f8a45449",  # login accessibility
    "9649b75731c9c7f55346ae7f3c766ff3c529a333",  # color contrast
}
for commit in reviewed:
    target_only(commit)

subjects = {
    commit: git("show", "-s", "--format=%s", commit).stdout.strip().lower()
    for commit in reviewed
}
assert "bootstrap 5" in subjects["fec59bec03195559a0f2589a397d2642a4045b27"]
assert "eslint" in subjects["7691aea5976f600a49117730fa1b3b19656f414a"]
for commit in reviewed - {
    "fec59bec03195559a0f2589a397d2642a4045b27",
    "7691aea5976f600a49117730fa1b3b19656f414a",
    "fa6fb0087cf6733c6b70bcd38a408978e9ab14de",
    "9ddf0536d7ed9382603a00a707eefa9f629d3d6f",
}:
    assert "accessib" in subjects[commit]

# Check additions in the reviewed commits do not introduce a backend mutation
# call. The selected rows are later required to have no other endpoint commit.
for commit in reviewed:
    patch = git("show", "--format=", commit).stdout
    additions = "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ).lower()
    for forbidden in (
        ".post(",
        ".put(",
        ".delete(",
        "httpclient",
        "taskwrapperservice",
        "rbdservice.create",
        "rbdservice.update",
        "rgwservice.create",
    ):
        assert forbidden not in additions, (commit, forbidden)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

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

reason_prefix = "MGR-FRONTEND-A11Y-SUPPORT-06:"
selected: dict[str, set[str]] = {}
for row in rows:
    path = row["path"]
    if not path.startswith(frontend_prefix) or not path.endswith((".ts", ".html")):
        continue
    if row["upgrade_impact"] and not row["impact_reason"].startswith(reason_prefix):
        continue
    commits = path_commits.get(path, set())
    if commits and commits <= reviewed:
        selected[path] = commits

assert selected
assert all(commits <= reviewed for commits in selected.values())
reason = (
    reason_prefix
    + " Every commit touching this endpoint between the tags is in the inspected "
    "Bootstrap/ESLint or accessibility/ARIA/i18n/icon/color markup allowlist. "
    "No backend mutation call, health value, inventory source or rollout command "
    "is introduced by these endpoint patches."
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
assert affect >= 237 and trivial >= 334 and unclassified <= 155
print(f"Accessibility/markup endpoints in cluster: {len(selected)}")
print(f"Newly classified as trivial: {newly_classified}")
for path in sorted(selected):
    print(f"  {path}")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
