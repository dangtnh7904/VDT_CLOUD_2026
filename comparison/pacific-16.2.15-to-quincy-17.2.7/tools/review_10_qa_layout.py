"""Classify owner-10 RBD/KRBD QA layout and suite-only deltas."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "10-rados-rbd-clients.csv"
md_path = root / "10-rados-rbd-clients.md"
readme_path = root / "README.md"
plan_path = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, path: str) -> str:
    return git("show", f"{tag}:{path}").stdout


def exists(tag: str, path: str) -> bool:
    return git("cat-file", "-e", f"{tag}:{path}", check=False).returncode == 0


def replace_known(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old in text:
        assert text.count(old) == expected
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected


paths = {
    "qa/rbd/conf/+",
    "qa/rbd/conf/disable-pool-app.yaml",
    "qa/suites/krbd/basic/conf.yaml",
    "qa/suites/krbd/fsx/conf.yaml",
    "qa/suites/krbd/ms_modeless/conf.yaml",
    "qa/suites/krbd/rbd-nomount/conf.yaml",
    "qa/suites/krbd/rbd/conf.yaml",
    "qa/suites/krbd/singleton-msgr-failures/conf.yaml",
    "qa/suites/krbd/thrash/conf.yaml",
    "qa/suites/krbd/unmap/conf.yaml",
    "qa/suites/krbd/wac/sysfs/conf.yaml",
    "qa/suites/krbd/wac/wac/conf.yaml",
    "qa/suites/rbd/basic/conf",
    "qa/suites/rbd/basic/tasks/rbd_api_tests_old_format.yaml",
    "qa/suites/rbd/cli/conf",
    "qa/suites/rbd/cli_v1/conf",
    "qa/suites/rbd/encryption/conf",
    "qa/suites/rbd/encryption/features/readbalance.yaml",
    "qa/suites/rbd/immutable-object-cache/conf",
    "qa/suites/rbd/librbd/conf",
    "qa/suites/rbd/librbd/config/.qa",
    "qa/suites/rbd/librbd/extra-conf/.qa",
    "qa/suites/rbd/librbd/extra-conf/copy-on-read.yaml",
    "qa/suites/rbd/librbd/extra-conf/none.yaml",
    "qa/suites/rbd/librbd/extra-conf/permit-partial-discard.yaml",
    "qa/suites/rbd/librbd/workloads/c_api_tests.yaml",
    "qa/suites/rbd/librbd/workloads/c_api_tests_with_defaults.yaml",
    "qa/suites/rbd/librbd/workloads/c_api_tests_with_journaling.yaml",
    "qa/suites/rbd/maintenance/conf",
    "qa/suites/rbd/migration/conf",
    "qa/suites/rbd/mirror-thrash/conf",
    "qa/suites/rbd/mirror/conf",
    "qa/suites/rbd/nbd/conf",
    "qa/suites/rbd/pwl-cache/home/conf",
    "qa/suites/rbd/pwl-cache/tmpfs/conf",
    "qa/suites/rbd/qemu/conf",
    "qa/suites/rbd/qemu/features/readbalance.yaml",
    "qa/suites/rbd/singleton-bluestore/conf",
    "qa/suites/rbd/singleton-bluestore/all/issue-20295.yaml",
    "qa/suites/rbd/singleton/all/mon-command-help.yaml",
    "qa/suites/rbd/singleton/all/rbd_mirror.yaml",
    "qa/suites/rbd/singleton/all/rbd_tasks.yaml",
    "qa/suites/rbd/singleton/conf",
    "qa/suites/rbd/thrash/conf",
    "qa/suites/rbd/thrash/workloads/rbd_api_tests.yaml",
    "qa/suites/rbd/thrash/workloads/rbd_api_tests_copy_on_read.yaml",
    "qa/suites/rbd/thrash/workloads/rbd_api_tests_journaling.yaml",
    "qa/suites/rbd/thrash/workloads/rbd_api_tests_no_locking.yaml",
    "qa/suites/rbd/valgrind/conf",
    "qa/suites/rbd/valgrind/workloads/c_api_tests.yaml",
    "qa/suites/rbd/valgrind/workloads/c_api_tests_with_defaults.yaml",
    "qa/suites/rbd/valgrind/workloads/c_api_tests_with_journaling.yaml",
    "qa/suites/rbd/valgrind/workloads/rbd_mirror.yaml",
}
assert len(paths) == 53

# Verify every classified row is an endpoint delta, then verify the actual
# suite-only patterns rather than inferring from the qa/ prefix.
touched = set(git("diff", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths)).stdout.splitlines())
renamed_source = "qa/suites/rbd/librbd/config/.qa"
assert touched == paths - {renamed_source}
assert exists("v16.2.15", renamed_source)
assert not exists("v17.2.7", renamed_source)
assert show("v17.2.7", "qa/rbd/conf/disable-pool-app.yaml").strip().endswith(
    "mon warn on pool no app: false")
assert show("v17.2.7", "qa/suites/rbd/basic/conf").strip() == ".qa/rbd/conf"
assert "POOL_APP_NOT_ENABLED" in show(
    "v16.2.15", "qa/suites/rbd/librbd/workloads/c_api_tests.yaml")
assert "POOL_APP_NOT_ENABLED" not in show(
    "v17.2.7", "qa/suites/rbd/librbd/workloads/c_api_tests.yaml")
assert "src/test/cli-integration/rbd/mon-command-help.t" in show(
    "v17.2.7", "qa/suites/rbd/singleton/all/mon-command-help.yaml")
assert exists("v16.2.15", "qa/suites/rbd/encryption/features/readbalance.yaml")
assert not exists("v17.2.7", "qa/suites/rbd/encryption/features/readbalance.yaml")
assert "ceph osd require-osd-release pacific" in show(
    "v16.2.15", "qa/suites/rbd/qemu/features/readbalance.yaml")
assert "ceph osd require-osd-release pacific" not in show(
    "v17.2.7", "qa/suites/rbd/qemu/features/readbalance.yaml")

reason = (
    "RADOS-QA-35: endpoint delta is confined to Teuthology suite topology or "
    "coverage: it centralizes suppression of POOL_APP_NOT_ENABLED, removes "
    "matching ignorelist entries/release setup, relocates extra-conf, or adds/"
    "removes a QA matrix case. It changes neither a shipped RBD/KRBD default "
    "nor client, daemon, wire, or on-disk runtime behavior."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)

for path in paths:
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial"
        assert not row["finding_id"]
        assert row["impact_reason"] == reason

for path in paths:
    row = by_path[path]
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
totals = (affect_count, trivial_count, blank_count)
assert totals in {(48, 188, 84), (48, 257, 15), (58, 262, 0)}
if totals == (48, 188, 84):
    replace_known(md_path, "`affect = 48`, `trivial = 135`, **chưa phân loại = 137**",
                  "`affect = 48`, `trivial = 188`, **chưa phân loại = 84**")
    replace_known(md_path, "135 hàng đã sàng lọc", "188 hàng đã sàng lọc")
    replace_known(md_path, "binary gate cho 137 hàng chưa phân loại",
                  "binary gate cho 84 hàng chưa phân loại")
    replace_known(
        readme_path,
        "1.422 hàng `affect`. 1.372 hàng `trivial`. 1.385 hàng chưa phân loại.",
        "1.422 hàng `affect`. 1.425 hàng `trivial`. 1.332 hàng chưa phân loại.",
    )
    replace_known(readme_path, "vì 1.385 hàng còn thiếu nhãn và lý do",
                  "vì 1.332 hàng còn thiếu nhãn và lý do")
    replace_known(
        plan_path,
        "`affect 1.422`, `trivial 1.372`, còn **1.385 hàng chưa phân loại**",
        "`affect 1.422`, `trivial 1.425`, còn **1.332 hàng chưa phân loại**",
    )
    replace_known(
        plan_path,
        "owner 10 hiện `48 affect`, `135 trivial`, `137` chưa phân loại",
        "owner 10 hiện `48 affect`, `188 trivial`, `84` chưa phân loại",
    )

print("Classified owner-10 RBD/KRBD QA-layout batch: 0 affect, 53 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
