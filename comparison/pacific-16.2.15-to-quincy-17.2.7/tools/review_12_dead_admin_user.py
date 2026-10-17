"""Verify that Quincy only removes orphaned RGW admin-user source files."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def is_ancestor(commit: str, tag: str) -> bool:
    result = git("merge-base", "--is-ancestor", commit, tag, check=False)
    assert result.returncode in (0, 1)
    return result.returncode == 0


def tree_paths(tag: str) -> set[str]:
    return set(git("ls-tree", "-r", "--name-only", tag).stdout.splitlines())


base_paths = tree_paths("v16.2.15")
target_paths = tree_paths("v17.2.7")
orphan_paths = {
    "src/rgw/rgw_admin_user.cc",
    "src/rgw/rgw_admin_user.h",
}
assert orphan_paths <= base_paths
assert orphan_paths.isdisjoint(target_paths)

# The library, public header and test that once consumed this shim were already
# removed before Pacific. Quincy subsequently deletes only the two leftovers.
consumer_removal = "c89b59428e66ae6d89d1fd27a4280045c57251cb"
orphan_removal = "832c10dfe82ea79b0c327e39ad794f4fa869aa4e"
assert is_ancestor(consumer_removal, "v16.2.15")
assert is_ancestor(consumer_removal, "v17.2.7")
assert not is_ancestor(orphan_removal, "v16.2.15")
assert is_ancestor(orphan_removal, "v17.2.7")

consumer_stat = git("show", "--format=%B", "--stat", consumer_removal).stdout
for path in (
    "src/include/rgw/librgw_admin_user.h",
    "src/rgw/librgw_admin_user.cc",
    "src/test/test_librgw_admin_user.cc",
):
    assert path in consumer_stat
assert "remove unused librgw_admin_user" in consumer_stat

orphan_message = git("show", "-s", "--format=%B", orphan_removal).stdout
assert "drop unused rgw_admin_user.{h,cc}" in orphan_message

# The leftover implementation includes the already-removed public header and
# declares two C entry points plus RGWLibAdmin. No build/package file or any
# other endpoint source references those files or symbols.
base_cc = git("show", "v16.2.15:src/rgw/rgw_admin_user.cc").stdout
base_header = git("show", "v16.2.15:src/rgw/rgw_admin_user.h").stdout
assert '#include "include/rgw/librgw_admin_user.h"' in base_cc
assert "int rgw_admin_create_user(" in base_cc
assert "int rgw_admin_user_info(" in base_cc
assert "class RGWLibAdmin" in base_header
assert "src/include/rgw/librgw_admin_user.h" not in base_paths

needles = (
    "rgw_admin_user.cc",
    "rgw_admin_user.h",
    "rgw_admin_create_user",
    "rgw_admin_user_info",
    "RGWLibAdmin",
    "librgw_admin_user",
)
for tag in ("v16.2.15", "v17.2.7"):
    for needle in needles:
        result = git(
            "grep",
            "-n",
            needle,
            tag,
            "--",
            ":!src/rgw/rgw_admin_user.cc",
            ":!src/rgw/rgw_admin_user.h",
            check=False,
        )
        assert result.returncode == 1, (tag, needle, result.stdout)


new_rows = {
    "src/rgw/rgw_admin_user.cc": (
        "trivial",
        "",
        "RGW-DEAD-ADMIN-USER-01: Quincy deletes an orphan implementation that Pacific does not build, package, export or call; its public librgw_admin_user header, library and sole test/consumer had already been removed before v16.2.15.",
    ),
    "src/rgw/rgw_admin_user.h": (
        "trivial",
        "",
        "RGW-DEAD-ADMIN-USER-01: Quincy deletes the leftover RGWLibAdmin declaration together with its unbuilt implementation; no source outside these orphan files references the class at either endpoint.",
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

print("Classified orphan RGW admin-user sources: 2 trivial")
