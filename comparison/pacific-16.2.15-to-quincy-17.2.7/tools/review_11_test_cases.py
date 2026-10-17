"""Classify owner-11 Python/C++ test bodies that only support runtime findings."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "11-cephfs-mds.csv"
md_path = root / "11-cephfs-mds.md"
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


python_tests = {
    "qa/tasks/cephfs/test_acls.py",
    "qa/tasks/cephfs/test_admin.py",
    "qa/tasks/cephfs/test_auto_repair.py",
    "qa/tasks/cephfs/test_backtrace.py",
    "qa/tasks/cephfs/test_cephfs_shell.py",
    "qa/tasks/cephfs/test_client_limits.py",
    "qa/tasks/cephfs/test_client_recovery.py",
    "qa/tasks/cephfs/test_data_scan.py",
    "qa/tasks/cephfs/test_exports.py",
    "qa/tasks/cephfs/test_failover.py",
    "qa/tasks/cephfs/test_forward_scrub.py",
    "qa/tasks/cephfs/test_full.py",
    "qa/tasks/cephfs/test_journal_repair.py",
    "qa/tasks/cephfs/test_mds_metrics.py",
    "qa/tasks/cephfs/test_misc.py",
    "qa/tasks/cephfs/test_multifs_auth.py",
    "qa/tasks/cephfs/test_multimds_misc.py",
    "qa/tasks/cephfs/test_nfs.py",
    "qa/tasks/cephfs/test_recovery_pool.py",
    "qa/tasks/cephfs/test_snap_schedules.py",
    "qa/tasks/cephfs/test_snapshots.py",
    "qa/tasks/cephfs/test_strays.py",
    "qa/tasks/cephfs/test_subvolume.py",
    "qa/tasks/cephfs/test_volumes.py",
    "qa/tasks/cephfs/xfstests_dev.py",
}

cpp_tests = {
    "src/test/fs/test_ino_release_cb.cc",
    "src/test/libcephfs/access.cc",
    "src/test/libcephfs/monconfig.cc",
    "src/test/libcephfs/multiclient.cc",
    "src/test/libcephfs/test.cc",
    "src/test/mds/TestMDSAuthCaps.cc",
}

paths = python_tests | cpp_tests
assert len(python_tests) == 25
assert len(cpp_tests) == 6
assert len(paths) == 31

touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# The one Python module in this area wired directly into upgraded_client is
# test_newops.py; it is deliberately excluded and classified by FS-006.
upgrade_tree = git("grep", "-n", "tasks.cephfs.test_", "v17.2.7", "--", "qa/suites/fs/upgrade", check=False).stdout
for path in python_tests:
    module = Path(path).stem
    assert f"tasks.cephfs.{module}" not in upgrade_tree, (path, upgrade_tree)

assert exists("v16.2.15", "qa/tasks/cephfs/test_subvolume.py")
assert not exists("v17.2.7", "qa/tasks/cephfs/test_subvolume.py")
assert "class TestRenameCommand" in show("v17.2.7", "qa/tasks/cephfs/test_admin.py")
assert "pending_subvolume_deletions" in show("v17.2.7", "qa/tasks/cephfs/test_volumes.py")
assert "ceph.caps" in show("v17.2.7", "src/test/libcephfs/test.cc")
assert "g_ceph_context" in show("v17.2.7", "src/test/mds/TestMDSAuthCaps.cc")
assert "std::atomic<bool>" in show("v17.2.7", "src/test/fs/test_ino_release_cb.cc")

reasons = {
    "FS-QA-10": (
        "FS-QA-10: endpoint hunks only add, remove, refactor, or stabilize Python feature/recovery "
        "test bodies (admin, volumes, NFS, scrub, failover, snapshots, client limits and related "
        "coverage). None is selected by qa/suites/fs/upgrade; test_newops is the separately handled exception."
    ),
    "FS-QA-11": (
        "FS-QA-11: changes are confined to C++ test targets for libcephfs/MDS caps and test hygiene "
        "(new assertions, API signature adaptation, cleanup, atomics, or namespace fixes). They do "
        "not change a shipped library/daemon object or an upgrade recipe independently."
    ),
}

cluster_for_path = {path: "FS-QA-10" for path in python_tests}
cluster_for_path.update({path: "FS-QA-11" for path in cpp_tests})

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)

for path, cluster in cluster_for_path.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial"
        assert not row["finding_id"]
        assert row["impact_reason"] == reasons[cluster]

for path, cluster in cluster_for_path.items():
    row = by_path[path]
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = reasons[cluster]

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert affect_count + trivial_count + blank_count == 427
totals = (affect_count, trivial_count, blank_count)
assert totals in {(59, 108, 260), (61, 115, 251)}
if totals != (59, 108, 260):
    print("Classified owner-11 CephFS Python/C++ test batch: 0 affect, 31 trivial")
    print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
    raise SystemExit(0)

replace_known(
    md_path,
    "`affect = 59`, `trivial = 77`, chưa phân loại = 291",
    "`affect = 59`, `trivial = 108`, chưa phân loại = 260",
)
replace_known(
    md_path,
    "**77 hàng** đã sàng lọc: ngoài anchor/print và 50 hàng layout (`FS-QA-04`), hàng 1382 chỉ bỏ test hỗ trợ legacy volume client (`FS-QA-05`); 23 hàng `FS-QA-06–09` chỉ đổi feature suite, filter test, vị trí subvolume coverage hoặc độ bền workunit. Mất gate import legacy thực tế vẫn được giữ là `affect` trong FS-007.",
    "**108 hàng** đã sàng lọc: ngoài anchor/print, layout (`FS-QA-04`) và các cụm support `FS-QA-05–09`, 31 hàng `FS-QA-10–11` chỉ sửa thân test Python/C++; `test_newops.py` là ngoại lệ đã giữ `affect` trong FS-006. Mất gate import legacy thực tế vẫn được giữ là `affect` trong FS-007.",
)
replace_known(md_path, "Phân loại 291 hàng còn trống", "Phân loại 260 hàng còn trống")
replace_known(
    readme_path,
    "1.484 hàng `affect`. 1.573 hàng `trivial`. 1.122 hàng chưa phân loại.",
    "1.484 hàng `affect`. 1.604 hàng `trivial`. 1.091 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 1.122 hàng còn thiếu nhãn và lý do", "vì 1.091 hàng còn thiếu nhãn và lý do")
replace_known(
    plan_path,
    "`affect 1.484`, `trivial 1.573`, còn **1.122 hàng chưa phân loại**",
    "`affect 1.484`, `trivial 1.604`, còn **1.091 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 11 hiện `59 affect`, `77 trivial`, `291` chưa phân loại",
    "owner 11 hiện `59 affect`, `108 trivial`, `260` chưa phân loại",
)

print("Classified owner-11 CephFS Python/C++ test batch: 0 affect, 31 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
