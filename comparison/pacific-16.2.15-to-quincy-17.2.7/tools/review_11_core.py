"""Finish owner-11 classification for core CephFS client and MDS paths."""

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
        assert text.count(old) == expected, (path, old, text.count(old))
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected, (path, new, text.count(new))


def insert_before_once(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if block in text:
        assert text.count(block) == 1
        return
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


affect_paths = {"src/mds/FSMap.h": "FS-017"}

client_trivial_paths = {
    "src/client/Client.h",
    "src/client/ClientSnapRealm.cc",
    "src/client/ClientSnapRealm.h",
    "src/client/Dentry.h",
    "src/client/Dir.h",
    "src/client/Fh.cc",
    "src/client/Fh.h",
    "src/client/Inode.cc",
    "src/client/Inode.h",
    "src/client/MetaSession.h",
    "src/client/ObjecterWriteback.h",
    "src/client/SyntheticClient.cc",
    "src/client/SyntheticClient.h",
    "src/client/barrier.cc",
    "src/client/fuse_ll.cc",
    "src/include/cephfs/ceph_ll_client.h",
    "src/include/cephfs/libcephfs.h",
    "src/include/cephfs/metrics/Types.h",
    "src/libcephfs.cc",
}
assert len(client_trivial_paths) == 19

recovery_trivial_paths = {
    "src/cls/cephfs/cls_cephfs_client.cc",
    "src/cls/cephfs/cls_cephfs_client.h",
    "src/mds/CInode.cc",
    "src/mds/CInode.h",
}
assert len(recovery_trivial_paths) == 4

binding_trivial_paths = {
    "src/pybind/cephfs/cephfs.pyx",
    "src/pybind/cephfs/setup.py",
}

mds_trivial_paths = {
    "src/mds/Anchor.cc",
    "src/mds/Anchor.h",
    "src/mds/CDentry.cc",
    "src/mds/CDir.cc",
    "src/mds/CDir.h",
    "src/mds/FSMap.cc",
    "src/mds/Locker.cc",
    "src/mds/LogEvent.h",
    "src/mds/LogSegment.h",
    "src/mds/MDBalancer.cc",
    "src/mds/MDBalancer.h",
    "src/mds/MDLog.cc",
    "src/mds/MDLog.h",
    "src/mds/MDSAuthCaps.cc",
    "src/mds/MDSAuthCaps.h",
    "src/mds/MDSDaemon.cc",
    "src/mds/MDSDaemon.h",
    "src/mds/MDSMap.cc",
    "src/mds/MDSMap.h",
    "src/mds/MDSMetaRequest.h",
    "src/mds/MDSRank.h",
    "src/mds/MDSTable.cc",
    "src/mds/MDSTable.h",
    "src/mds/MDSTableClient.cc",
    "src/mds/MDSTableClient.h",
    "src/mds/MDSTableServer.cc",
    "src/mds/MDSTableServer.h",
    "src/mds/Mantle.cc",
    "src/mds/Migrator.cc",
    "src/mds/Migrator.h",
    "src/mds/Mutation.cc",
    "src/mds/Mutation.h",
    "src/mds/OpenFileTable.cc",
    "src/mds/OpenFileTable.h",
    "src/mds/PurgeQueue.cc",
    "src/mds/RecoveryQueue.cc",
    "src/mds/ScrubStack.cc",
    "src/mds/SessionMap.cc",
    "src/mds/SnapClient.cc",
    "src/mds/SnapClient.h",
    "src/mds/SnapRealm.cc",
    "src/mds/SnapServer.cc",
    "src/mds/SnapServer.h",
    "src/mds/StrayManager.cc",
    "src/mds/StrayManager.h",
    "src/mds/journal.cc",
    "src/mds/locks.c",
    "src/mds/snap.cc",
}
assert len(mds_trivial_paths) == 48

trivial_paths = (
    client_trivial_paths
    | recovery_trivial_paths
    | binding_trivial_paths
    | mds_trivial_paths
)
paths = set(affect_paths) | trivial_paths
assert len(trivial_paths) == 73
assert len(paths) == 74

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)
blank_paths = {row["path"] for row in rows if not row["upgrade_impact"]}
if blank_paths:
    assert blank_paths == paths, (sorted(paths - blank_paths), sorted(blank_paths - paths))

# All mapped rows are real endpoint changes. Disable rename heuristics because
# the suite inventory deliberately preserves its own pairing decisions.
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# FS-017: the target expands the compatibility-upgrade gate to a failed file
# system whose desired rank set is still non-empty but no MDS is up. The caller
# can then choose a newer-compatible standby and merge its CompatSet on promote.
upgrade_commit = "4a0e7734d7761ffb31b57d64f28c288b36ff75e0"
assert ancestor(upgrade_commit, "v17.2.7")
assert not ancestor(upgrade_commit, "v16.2.15")
base_fsmap_h = show("v16.2.15", "src/mds/FSMap.h")
target_fsmap_h = show("v17.2.7", "src/mds/FSMap.h")
assert "!mds_map.allows_standby_replay() && mds_map.get_num_in_mds() <= 1" in base_fsmap_h
assert "auto up_mds = mds_map.get_num_up_mds();" not in base_fsmap_h
assert "auto up_mds = mds_map.get_num_up_mds();" in target_fsmap_h
assert "(!asr && up_mds == 0)" in target_fsmap_h
for tag in ("v16.2.15", "v17.2.7"):
    fsmap_cc = show(tag, "src/mds/FSMap.cc")
    assert "const bool upgradeable = fs.is_upgradeable();" in fsmap_cc
    assert "!upgradeable && !fs.mds_map.compat.writeable(info.compat)" in fsmap_cc
    assert "filesystem.mds_map.compat.merge(info.compat);" in fsmap_cc

# False-positive guard: the graceful journal-recovery branches exist at both
# endpoints. The only net behavior here is that Quincy prints "recovered" only
# after checking the result, so MDLog.cc is not a new upgrade recovery path.
base_mdlog = show("v16.2.15", "src/mds/MDLog.cc")
target_mdlog = show("v17.2.7", "src/mds/MDLog.cc")
for text in (base_mdlog, target_mdlog):
    for needle in (
        "if (recovery_result == -CEPHFS_EBLOCKLISTED)",
        "else if (recovery_result != 0)",
        "mds->damaged_unlocked();",
    ):
        assert needle in text
front_wait = 'dout(4) << "Waiting for journal " << jp.front'
base_front = base_mdlog.index(front_wait)
target_front = target_mdlog.index(front_wait)
base_recovery = base_mdlog[base_front:]
target_recovery = target_mdlog[target_front:]
success_log = 'dout(4) << "Journal " << jp.front << " recovered."'
error_check = "if (recovery_result == -CEPHFS_EBLOCKLISTED)"
assert base_recovery.index(success_log) < base_recovery.index(error_check)
assert target_recovery.index(error_check) < target_recovery.index(success_log)

# The remaining apparent compatibility candidates are additive or already
# retain their old interface: callback2 keeps callback1, and symlink recovery
# stores an optional xattr that older daemons ignore rather than rewriting an
# existing CephFS metadata encoding.
base_lib = show("v16.2.15", "src/include/cephfs/libcephfs.h")
target_lib = show("v17.2.7", "src/include/cephfs/libcephfs.h")
assert "void ceph_ll_register_callbacks(" in base_lib
assert "void ceph_ll_register_callbacks(" in target_lib
assert "int ceph_ll_register_callbacks2(" not in base_lib
assert "int ceph_ll_register_callbacks2(" in target_lib
base_inode = show("v16.2.15", "src/mds/CInode.cc")
target_inode = show("v17.2.7", "src/mds/CInode.cc")
assert 'op.setxattr("symlink", symlink_bl);' not in base_inode
assert 'op.setxattr("symlink", symlink_bl);' in target_inode

finding_reason = (
    "FS-017: Quincy expands Filesystem::is_upgradeable() to allow a newer-compatible "
    "standby when max_mds/in ranks remain but every MDS is down and standby-replay is "
    "disabled. Promotion can then merge the standby CompatSet; Pacific rejects this "
    "cephadm fail_fs upgrade state. Validate promotion and rollback compatibility."
)
client_reason = (
    "FS-CLIENT-02: endpoint hunks are std-qualification/lifetime refactors, additive "
    "libcephfs/FUSE interfaces that retain the old callback ABI, or normal target fixes "
    "for mount/snapshot/I/O behavior. They do not independently alter an on-disk/wire "
    "upgrade contract; the mixed-session feature regression remains covered by FS-011."
)
recovery_reason = (
    "FS-RECOVERY-02: Quincy optionally stores and reads a symlink target xattr on the first "
    "data object for disaster-recovery scanning. This is additive metadata ignored by old "
    "MDS code, not a rewrite or required rolling-upgrade step, so it has no independent "
    "upgrade/rollback causal path."
)
binding_reason = (
    "FS-BIND-01: the Python binding endpoint diff adds typing/docstring cleanup and removes "
    "the obsolete Python-2 print_function import. Exported filesystem behavior and persisted "
    "state are unchanged for the upgrade path."
)
mds_reason = (
    "FS-MDS-03: screened core-MDS endpoint hunks are namespace/assert/logging changes or "
    "normal target fixes for locks, stray reintegration, cache/recovery and diagnostics. "
    "Persisted encode/decode contracts in this batch do not gain a required migration. "
    "MDLog error handling already exists at both endpoints; FS-017 is the upgrade-gate exception."
)

for path, finding in affect_paths.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == finding
        assert row["impact_reason"] == finding_reason
for cluster, reason in (
    (client_trivial_paths, client_reason),
    (recovery_trivial_paths, recovery_reason),
    (binding_trivial_paths, binding_reason),
    (mds_trivial_paths, mds_reason),
):
    for path in cluster:
        row = by_path[path]
        if row["upgrade_impact"]:
            assert row["upgrade_impact"] == "trivial"
            assert not row["finding_id"]
            assert row["impact_reason"] == reason

for path, finding in affect_paths.items():
    row = by_path[path]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = finding
    row["impact_reason"] = finding_reason
for cluster, reason in (
    (client_trivial_paths, client_reason),
    (recovery_trivial_paths, recovery_reason),
    (binding_trivial_paths, binding_reason),
    (mds_trivial_paths, mds_reason),
):
    for path in cluster:
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
assert affect_count + trivial_count + blank_count == 427
assert (affect_count, trivial_count, blank_count) == (88, 339, 0)

finding_md = """### FS-017 — Cho phép nâng compat khi filesystem còn rank `in` nhưng mọi MDS đều down

- **CSV:** 2163. **Nguồn:** `Filesystem::is_upgradeable()`, caller `FSMap::get_available_standby()` và `FSMap::promote()`; commit `4a0e7734d7761ffb31b57d64f28c288b36ff75e0` nêu trực tiếp scenario `fail_fs` của cephadm khi `max_mds >= 1` và toàn bộ MDS down.
- **Trước → sau:** Pacific chỉ coi filesystem có thể nâng compat khi không còn rank `in`, hoặc khi tắt standby-replay và số rank `in <= 1`. Quincy vẫn giữ hai trường hợp đó nhưng thêm `!allows_standby_replay && get_num_up_mds() == 0`. Vì vậy với `max_mds`/tập rank `in` lớn hơn 1 nhưng mọi daemon đã fail, target có thể chọn standby có CompatSet mới; khi promote, `FSMap::promote()` merge CompatSet đó vào MDSMap. Pacific từ chối standby không tương thích ngược ở cùng trạng thái và có thể làm tiến trình nâng dừng lại.
- **Điều kiện và tác động:** Áp dụng khi cephadm hoặc thao tác vận hành đưa filesystem vào `fail_fs`, standby-replay đã tắt, không MDS nào `up`, nhưng rank vẫn còn `in`, rồi đưa binary MDS mới vào. Leader MON chạy logic Quincy có thể cho phép promotion và nâng CompatSet; sau khi merge, quay lại MDS Pacific chỉ an toàn nếu CompatSet vẫn writable với binary cũ. Trong pha MON lẫn phiên bản, kết quả phụ thuộc leader đang xử lý FSMap; full Quincy dùng gate mới. **Độ tin cậy:** cao về code/caller/commit, chưa có lab. **Kiểm chứng:** dựng filesystem `max_mds=2`, chạy `fs fail` để còn rank `in` nhưng `up=0`, đưa standby Quincy có CompatSet mới vào, xác nhận selection/promotion/compat merge và availability; lặp với leader MON Pacific/Quincy rồi thử rollback MDS trên bản sao lab. Chưa chạy runtime.

"""
insert_before_once(md_path, "## Trivial changes", finding_md)

replace_known(md_path, "**Trạng thái: đang phân tích.**", "**Trạng thái: đã hoàn tất binary gate.**")
replace_known(
    md_path,
    "Hiện **`affect = 87`, `trivial = 266`, chưa phân loại = 74**. Các finding chi tiết dưới đây chỉ lấy từ hàng `affect`; các số này chưa phải kết luận cho toàn owner.",
    "Kết quả **`affect = 88`, `trivial = 339`, chưa phân loại = 0**; chưa có kết quả lab/runtime.",
)
replace_known(
    md_path,
    "**266 hàng** đã sàng lọc: ngoài các cụm QA `FS-QA-04–12`, tài liệu và runtime/wire trước đó, batch mới có 22 hàng mgr/NFS/volumes `FS-MGR-01`, 24 hàng công cụ/cephfs-mirror `FS-TOOL-01` và bốn cleanup/marker `FS-CODE-04`. Các ngoại lệ state/mount và gate QA được giữ `affect` trong FS-013–016; shared mount matrix được nối vào FS-006. Danh sách đầy đủ nằm trong CSV.",
    "**339 hàng** đã sàng lọc. Batch cuối thêm 19 hàng client/libcephfs `FS-CLIENT-02`, bốn hàng symlink-recovery `FS-RECOVERY-02`, hai hàng Python binding `FS-BIND-01` và 48 hàng core MDS `FS-MDS-03`. Callback API mới vẫn giữ API cũ; symlink xattr là additive; xử lý lỗi journal đã có ở cả hai endpoint. Ngoại lệ upgrade-gate được giữ `affect` trong FS-017. Danh sách và lý do đầy đủ nằm trong CSV.",
)
replace_known(md_path, "## Việc còn lại", "## Kiểm chứng cần hoàn thành")
replace_known(
    md_path,
    "- Phân loại 74 hàng còn trống theo hunk, metadata, commit và caller; ưu tiên runtime MDS/client rồi volumes/NFS và test upgrade liên quan.",
    "- Binary gate đã đối soát đủ `88 affect + 339 trivial = 427`; tiếp theo là inventory As-Is và lab/canary cho các finding có điều kiện.",
)
replace_known(
    md_path,
    "- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 427` và đánh giá rủi ro toàn owner.",
    "- Đối chiếu đặc biệt FS-017 với quy trình `fail_fs`, trạng thái CompatSet và kế hoạch rollback MDS trước rollout.",
)

replace_known(
    readme_path,
    "1.512 hàng `affect`. 1.762 hàng `trivial`. 905 hàng chưa phân loại.",
    "1.513 hàng `affect`. 1.835 hàng `trivial`. 831 hàng chưa phân loại.",
)
replace_known(
    readme_path,
    "[FS-001–016](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence, upgraded-client matrix, legacy import, eviction khi OSD laggy, ACK unlink, feature bits, retry/fwd, snap-schedule state, kernel/FUSE mount và health gate",
    "[FS-001–017](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence, upgraded-client matrix, legacy import, eviction khi OSD laggy, ACK unlink, feature bits, retry/fwd, snap-schedule state, kernel/FUSE mount, health gate và compat promotion khi mọi MDS down",
)
replace_known(
    readme_path,
    "[FS-001–016](./11-cephfs-mds.md) về baseline client, MDS upgrade sequence, upgraded-client matrix, legacy import, eviction khi OSD laggy, ACK unlink, feature bits, retry/fwd, snap-schedule state, kernel/FUSE mount và health gate",
    "[FS-001–017](./11-cephfs-mds.md) về baseline client, MDS upgrade sequence, upgraded-client matrix, legacy import, eviction khi OSD laggy, ACK unlink, feature bits, retry/fwd, snap-schedule state, kernel/FUSE mount, health gate và compat promotion khi mọi MDS down",
)
replace_known(
    readme_path,
    "[owner 10](./10-rados-rbd-clients.md), [owner 12](./12-rgw.md) và [owner 14](./14-security-cross-reference.md) đã hoàn tất binary gate",
    "[owner 10](./10-rados-rbd-clients.md), [owner 11](./11-cephfs-mds.md), [owner 12](./12-rgw.md) và [owner 14](./14-security-cross-reference.md) đã hoàn tất binary gate",
)
replace_known(readme_path, "vì 905 hàng còn thiếu nhãn và lý do", "vì 831 hàng còn thiếu nhãn và lý do")

replace_known(
    plan_path,
    "Owner 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 12, 14 đã hoàn tất binary gate",
    "Owner 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 14 đã hoàn tất binary gate",
)
replace_known(
    plan_path,
    "`affect 1.512`, `trivial 1.762`, còn **905 hàng chưa phân loại**",
    "`affect 1.513`, `trivial 1.835`, còn **831 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 11 hiện `87 affect`, `266 trivial`, `74` chưa phân loại",
    "owner 11 đã chốt `88 affect`, `339 trivial`, `0` chưa phân loại",
)
replace_known(
    plan_path,
    "**Hàng chờ ưu tiên:** tiếp tục owner 11 CephFS, owner 13 build/package và owner 15 validation.",
    "**Hàng chờ ưu tiên:** tiếp tục owner 13 build/package và owner 15 validation.",
)

print("Classified owner-11 core batch: 1 affect, 73 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
