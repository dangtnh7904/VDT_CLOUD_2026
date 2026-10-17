"""Classify owner-11 CephFS QA harness changes, retaining upgrade-path exceptions."""

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


def ancestor(commit: str, ref: str) -> bool:
    return git("merge-base", "--is-ancestor", commit, ref, check=False).returncode == 0


def replace_known(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old in text:
        assert text.count(old) == expected
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected


def insert_before_once(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if block in text:
        assert text.count(block) == 1
        return
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


affect_paths = {
    "qa/tasks/cephfs/kernel_mount.py": "FS-002",
    "qa/tasks/cephfs/filesystem.py": "FS-008",
}

support_paths = {
    "qa/tasks/cephfs/caps_helper.py",
    "qa/tasks/cephfs/cephfs_test_case.py",
    "qa/tasks/cephfs/fuse_mount.py",
    "qa/tasks/cephfs/mount.py",
    "qa/tasks/kclient.py",
    "qa/tasks/mds_creation_failure.py",
    "qa/tasks/mds_thrash.py",
}

paths = set(affect_paths) | support_paths
assert len(paths) == 9

touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

for commit in (
    "f8b939e128e54af4453dce6c21d06218c4c29406",
    "a15e6d672102d1bc205f66cb4b6ca13fc8568836",
    "b44ee81e7e854f8ae7a8eabe405e5b78f5898f26",
    "285e1547ded4b703a4191da183158b9687200709",
):
    assert ancestor(commit, "v17.2.7"), commit

base_kernel = show("v16.2.15", "qa/tasks/cephfs/kernel_mount.py")
target_kernel = show("v17.2.7", "qa/tasks/cephfs/kernel_mount.py")
assert "syntax_style" not in base_kernel
assert "self.syntax_style = client_config.get('syntax', 'v2')" in target_kernel
assert "if self.syntax_style != 'v1':" in target_kernel
assert 'opts += ",nofallback"' in target_kernel

pre_upgrade = show("v17.2.7", "qa/tasks/mds_pre_upgrade.py")
assert "fs.reach_max_mds()" in pre_upgrade
base_fs = show("v16.2.15", "qa/tasks/cephfs/filesystem.py")
target_fs = show("v17.2.7", "qa/tasks/cephfs/filesystem.py")
assert 'self.mon_manager.raw_cluster_cmd("mds", "deactivate"' in base_fs
assert 'self.mon_manager.raw_cluster_cmd("mds", "deactivate"' not in target_fs
assert "status = self.wait_for_daemons()" in target_fs
for ref in ("v16.2.15", "v17.2.7"):
    featureful = show(ref, "qa/suites/fs/upgrade/featureful_client/old_client/tasks/2-upgrade.yaml")
    assert "- mds_pre_upgrade:" in featureful

# Supporting rows are framework refactors or generic non-upgrade QA behavior.
assert "random.randrange(0.0, 1.0)" in show("v16.2.15", "qa/tasks/mds_thrash.py")
assert "random.random()" in show("v17.2.7", "qa/tasks/mds_thrash.py")
assert "def _get_mount_cmd" in show("v17.2.7", "qa/tasks/cephfs/fuse_mount.py")
assert "def _create_mntpt" in show("v17.2.7", "qa/tasks/cephfs/mount.py")

reasons = {
    "FS-002": (
        "FS-002: kernel_mount.py implements the v1/v2 syntax selector used by the MDS upgrade "
        "suite and deliberately omits the test-only nofallback option for v1 because Pacific/older "
        "mount helpers would otherwise fail. This directly changes upgrade-suite mount execution."
    ),
    "FS-008": (
        "FS-008: Filesystem.reach_max_mds(), called by mds_pre_upgrade, no longer issues explicit "
        "mds deactivate operations when ranks exceed max_mds; it waits for automatic convergence "
        "and asserts the final rank set. This changes pre-upgrade suite execution/failure behavior."
    ),
}
support_reason = (
    "FS-QA-12: remaining harness hunks are API/import refactors, common mount helper extraction, "
    "temporary-file handling, or generic non-upgrade thrash/test behavior. They do not independently "
    "change an upgrade recipe; the mount-syntax and mds_pre_upgrade exceptions are FS-002/FS-008."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)

for path, finding in affect_paths.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == finding
        assert row["impact_reason"] == reasons[finding]
for path in support_paths:
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial"
        assert not row["finding_id"]
        assert row["impact_reason"] == support_reason

for path, finding in affect_paths.items():
    row = by_path[path]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = finding
    row["impact_reason"] = reasons[finding]
for path in support_paths:
    row = by_path[path]
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = support_reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert affect_count + trivial_count + blank_count == 427
assert (affect_count, trivial_count, blank_count) == (61, 115, 251)

finding_md = """### FS-008 — `mds_pre_upgrade` không còn chủ động deactivate rank thừa

- **CSV:** 1354. **Nguồn:** `qa/tasks/cephfs/filesystem.py`, `Filesystem.reach_max_mds()`; caller `qa/tasks/mds_pre_upgrade.py`; commit `285e1547ded4b703a4191da183158b9687200709`. Caller không có net diff nên chỉ là context, không thêm vào CSV.
- **Trước → sau:** Pacific đọc `max_mds`, và nếu số rank lớn hơn thì đợi daemon rồi gọi `mds deactivate` theo rank giảm dần; lỗi được bắt để fallback vì Mimic đã tự động deactivation. Quincy bỏ helper `deactivate()` và toàn bộ vòng cưỡng bức, chỉ `wait_for_daemons()` rồi assert tập rank `0..max_mds-1`.
- **Điều kiện và tác động:** `mds_pre_upgrade` của hai suite `featureful_client` gọi trực tiếp hàm này trước `install.upgrade`. Khi MDSMap bước vào gate với rank thừa/chưa hội tụ, tín hiệu và thời gian chuẩn bị có thể đổi: target dựa vào hội tụ tự động thay vì chủ động gửi lệnh. Đây là thay đổi harness QA, không thay đổi MDS production tự động. **Mixed-version:** xảy ra trước khi nâng daemon; **sau nâng cấp:** không có hành vi runtime độc lập. **Độ tin cậy:** cao về caller/endpoint, trung bình về khả năng kích hoạt. **Kiểm chứng:** tạo suite với `max_mds` giảm khi còn rank thừa, đo hội tụ/timeout và trạng thái MDSMap trước khi cho phép bước cài; chưa chạy lab.

"""

replace_known(
    md_path,
    "`affect = 59`, `trivial = 108`, chưa phân loại = 260",
    "`affect = 61`, `trivial = 115`, chưa phân loại = 251",
)
replace_known(md_path, "**CSV:** 624, 625.", "**CSV:** 624, 625, 1356.")
insert_before_once(md_path, "## Trivial changes", finding_md)
replace_known(
    md_path,
    "**108 hàng** đã sàng lọc: ngoài anchor/print, layout (`FS-QA-04`) và các cụm support `FS-QA-05–09`, 31 hàng `FS-QA-10–11` chỉ sửa thân test Python/C++; `test_newops.py` là ngoại lệ đã giữ `affect` trong FS-006. Mất gate import legacy thực tế vẫn được giữ là `affect` trong FS-007.",
    "**115 hàng** đã sàng lọc: ngoài các cụm support `FS-QA-04–11`, bảy hàng `FS-QA-12` chỉ refactor framework hoặc sửa test/thrash tổng quát. Hai ngoại lệ harness được giữ `affect`: mount syntax trong FS-002 và hội tụ rank pre-upgrade trong FS-008.",
)
replace_known(md_path, "Phân loại 260 hàng còn trống", "Phân loại 251 hàng còn trống")
replace_known(
    readme_path,
    "1.484 hàng `affect`. 1.604 hàng `trivial`. 1.091 hàng chưa phân loại.",
    "1.486 hàng `affect`. 1.611 hàng `trivial`. 1.082 hàng chưa phân loại.",
)
replace_known(
    readme_path,
    "[FS-001–007](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence, cephadm workload, no-FS gate, upgraded-client matrix và khoảng trống import legacy",
    "[FS-001–008](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence/mount syntax, cephadm workload, no-FS gate, upgraded-client matrix, khoảng trống import legacy và hội tụ rank pre-upgrade",
)
replace_known(readme_path, "vì 1.091 hàng còn thiếu nhãn và lý do", "vì 1.082 hàng còn thiếu nhãn và lý do")
replace_known(
    plan_path,
    "`affect 1.484`, `trivial 1.604`, còn **1.091 hàng chưa phân loại**",
    "`affect 1.486`, `trivial 1.611`, còn **1.082 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 11 hiện `59 affect`, `108 trivial`, `260` chưa phân loại",
    "owner 11 hiện `61 affect`, `115 trivial`, `251` chưa phân loại",
)

print("Classified owner-11 CephFS QA harness batch: 2 affect, 7 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
