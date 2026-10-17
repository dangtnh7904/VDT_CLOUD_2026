"""Classify owner-11 mgr, mount, QA-fragment, and CephFS tool clusters."""

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


affect_paths = {
    "src/pybind/mgr/snap_schedule/fs/schedule.py": "FS-013",
    "src/pybind/mgr/snap_schedule/fs/schedule_client.py": "FS-013",
    "src/mount/conf.cc": "FS-014",
    "src/mount/mount.ceph.c": "FS-014",
    "src/mount/mount.ceph.h": "FS-014",
    "qa/cephfs/mount/fuse.yaml": "FS-006",
    "qa/cephfs/mount/kclient/mount-syntax/v1.yaml": "FS-006",
    "qa/cephfs/mount/kclient/mount-syntax/v2.yaml": "FS-006",
    "qa/cephfs/mount/kclient/mount.yaml": "FS-006",
    "qa/cephfs/mount/kclient/overrides/distro/stock/k-stock.yaml": "FS-006",
    "qa/cephfs/mount/kclient/overrides/distro/testing/flavor/ubuntu_latest.yaml": "FS-006",
    "qa/cephfs/mount/kclient/overrides/distro/testing/k-testing.yaml": "FS-006",
    "qa/cephfs/overrides/ignorelist_health.yaml": "FS-015",
    "qa/cephfs/overrides/ignorelist_wrongly_marked_down.yaml": "FS-015",
    "src/mount.fuse.ceph": "FS-016",
}
assert len(affect_paths) == 15

mgr_trivial_paths = {
    "src/pybind/mgr/nfs/cluster.py",
    "src/pybind/mgr/nfs/export.py",
    "src/pybind/mgr/nfs/ganesha_conf.py",
    "src/pybind/mgr/nfs/module.py",
    "src/pybind/mgr/nfs/tests/test_nfs.py",
    "src/pybind/mgr/snap_schedule/module.py",
    "src/pybind/mgr/volumes/fs/async_job.py",
    "src/pybind/mgr/volumes/fs/fs_util.py",
    "src/pybind/mgr/volumes/fs/operations/access.py",
    "src/pybind/mgr/volumes/fs/operations/clone_index.py",
    "src/pybind/mgr/volumes/fs/operations/group.py",
    "src/pybind/mgr/volumes/fs/operations/resolver.py",
    "src/pybind/mgr/volumes/fs/operations/snapshot_util.py",
    "src/pybind/mgr/volumes/fs/operations/subvolume.py",
    "src/pybind/mgr/volumes/fs/operations/versions/auth_metadata.py",
    "src/pybind/mgr/volumes/fs/operations/versions/subvolume_attrs.py",
    "src/pybind/mgr/volumes/fs/operations/versions/subvolume_base.py",
    "src/pybind/mgr/volumes/fs/operations/volume.py",
    "src/pybind/mgr/volumes/fs/purge_queue.py",
    "src/pybind/mgr/volumes/fs/vol_spec.py",
    "src/pybind/mgr/volumes/fs/volume.py",
    "src/pybind/mgr/volumes/module.py",
}
assert len(mgr_trivial_paths) == 22

tool_trivial_paths = {
    "src/tools/cephfs/DataScan.cc",
    "src/tools/cephfs/DataScan.h",
    "src/tools/cephfs/Dumper.cc",
    "src/tools/cephfs/JournalFilter.cc",
    "src/tools/cephfs/JournalTool.cc",
    "src/tools/cephfs/MetaTool.cc",
    "src/tools/cephfs/MetaTool.h",
    "src/tools/cephfs/Resetter.cc",
    "src/tools/cephfs/TableTool.cc",
    "src/tools/cephfs/cephfs-data-scan.cc",
    "src/tools/cephfs/cephfs-journal-tool.cc",
    "src/tools/cephfs/cephfs-meta-injection.cc",
    "src/tools/cephfs/cephfs-table-tool.cc",
    "src/tools/cephfs/first-damage.sh",
    "src/tools/cephfs/shell/cephfs-shell",
    "src/tools/cephfs/top/cephfs-top",
    "src/tools/cephfs/type_helper.hpp",
    "src/tools/cephfs_mirror/FSMirror.cc",
    "src/tools/cephfs_mirror/FSMirror.h",
    "src/tools/cephfs_mirror/InstanceWatcher.cc",
    "src/tools/cephfs_mirror/InstanceWatcher.h",
    "src/tools/cephfs_mirror/PeerReplayer.cc",
    "src/tools/cephfs_mirror/PeerReplayer.h",
    "src/tools/cephfs_mirror/main.cc",
}
assert len(tool_trivial_paths) == 24

misc_trivial_paths = {
    "qa/cephfs/conf/mds.yaml",
    "qa/cephfs/mount/kclient/mount-syntax/$",
    "src/ceph_fuse.cc",
    "src/ceph_mds.cc",
}
assert len(misc_trivial_paths) == 4

trivial_paths = mgr_trivial_paths | tool_trivial_paths | misc_trivial_paths
paths = set(affect_paths) | trivial_paths
assert len(trivial_paths) == 50
assert len(paths) == 65

# Endpoint inventory check deliberately disables heuristic rename pairing. This
# is important for the empty suite marker whose inventory old_path is unrelated.
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# Provenance for target-side migrations/features and the late Pacific-only
# mount.fuse backport.
for commit in (
    "a2dbf943a26bb85c70a58f466efdd54470be4621",
    "3f4a6ee6f6c4330e5b00deb43f1239bdee6d93c6",
    "707543779e24c6bc1489c07f5fa1a239d110d9fb",
    "ed82b871bb01396ce9c6c910b6a73e61f6a790c9",
    "8606f5839d5cc9979237eb4a2dbad06658881e70",
    "63ac4f9e48ea60e30f66c9e03e3ad20dc96983ce",
    "903a14f756cd057a408b22a3eee8b236b47d4423",
):
    assert ancestor(commit, "v17.2.7"), commit
pacific_nofail = "2593eec40208f614928448494bea20aa8a885f80"
assert ancestor(pacific_nofail, "v16.2.15")
assert not ancestor(pacific_nofail, "v17.2.7")

# FS-013: the base serializes an in-memory SQLite database as a SQL dump in a
# single RADOS object. The target opens a Ceph SQLite VFS database, imports and
# removes the legacy dump and creates tables idempotently. Both endpoints
# already reconstruct active timers in the constructor after mgr restart.
base_sched = show("v16.2.15", "src/pybind/mgr/snap_schedule/fs/schedule.py")
target_sched = show("v17.2.7", "src/pybind/mgr/snap_schedule/fs/schedule.py")
base_sched_client = show("v16.2.15", "src/pybind/mgr/snap_schedule/fs/schedule_client.py")
target_sched_client = show("v17.2.7", "src/pybind/mgr/snap_schedule/fs/schedule_client.py")
assert "CREATE TABLE schedules" in base_sched
assert "CREATE TABLE IF NOT EXISTS schedules" in target_sched
assert "for row in db.iterdump()" in base_sched_client
assert "def store_schedule_db" in base_sched_client
assert 'vfs=ceph' in target_sched_client
assert "ioctx.remove_object(SNAP_DB_OBJECT_NAME)" in target_sched_client
for source in (base_sched_client, target_sched_client):
    assert "Schedule.list_all_schedules" in source
    assert "self.refresh_snap_timers(fs_name, sched.path, db)" in source
assert "def store_schedule_db" not in target_sched_client

# The upgrade-discovery behavior from ed82b871 exists at both endpoints (the
# Pacific endpoint contains an equivalent branch backport). The remaining net
# diff in this file is formatting/import cleanup, so it is not an affect row.
base_subvol = show(
    "v16.2.15", "src/pybind/mgr/volumes/fs/operations/versions/subvolume_base.py"
)
target_subvol = show(
    "v17.2.7", "src/pybind/mgr/volumes/fs/operations/versions/subvolume_base.py"
)
for needle in (
    "self.fs.stat(self.legacy_config_path)",
    "fabricated .meta",
    "assuming legacy_mode",
):
    assert needle in base_subvol
    assert needle in target_subvol

# FS-014: target mount.ceph defaults to the new local-kernel device syntax,
# reads the cluster fsid, requests prefer-crc, and can retry the old syntax.
base_mount = show("v16.2.15", "src/mount/mount.ceph.c")
target_mount = show("v17.2.7", "src/mount/mount.ceph.c")
target_conf = show("v17.2.7", "src/mount/conf.cc")
for needle in (
    "MOUNT_DEV_FORMAT_NEW",
    "CEPH_V2_MOUNT_SUPPORT_PATH",
    "CEPH_DEFAULT_V2_MS_MODE",
    "mount_new_device_format",
    "mount_old_device_format",
    "should_fallback",
    'strcmp(data, "nofallback")',
):
    assert needle not in base_mount
    assert needle in target_mount
assert 'conf.get_val<uuid_d>("fsid")' in target_conf

# FS-006 extension: the upgraded-client suite points at the shared mount
# matrix. Target fragments expose mount type/syntax to postmerge filters and
# split v1/v2 kernel syntax plus distro/upstream kernel selection.
suite_mount_pointer = show(
    "v17.2.7", "qa/suites/fs/upgrade/upgraded_client/tasks/1-mount/mount"
)
target_fuse_fragment = show("v17.2.7", "qa/cephfs/mount/fuse.yaml")
target_kclient_fragment = show("v17.2.7", "qa/cephfs/mount/kclient/mount.yaml")
assert ".qa/cephfs/mount/" in suite_mount_pointer
assert "teuthology:\n  postmerge:" in target_fuse_fragment
assert "local function is_fuse()" in target_fuse_fragment
assert "local function syntax_version()" in target_kclient_fragment
assert "yaml.overrides.kclient.syntax" in target_kclient_fragment
assert "syntax: 'v1'" in show(
    "v17.2.7", "qa/cephfs/mount/kclient/mount-syntax/v1.yaml"
)
assert "syntax: 'v2'" in show(
    "v17.2.7", "qa/cephfs/mount/kclient/mount-syntax/v2.yaml"
)
assert "ktype: distro" in show(
    "v17.2.7", "qa/cephfs/mount/kclient/overrides/distro/stock/k-stock.yaml"
)
assert "ktype: upstream" in show(
    "v17.2.7", "qa/cephfs/mount/kclient/overrides/distro/testing/k-testing.yaml"
)

# FS-015: all upgrade matrices symlink these shared filters. Target stops
# hiding broad FS/PG/OSD messages and adds the specific pool-application case.
base_health = show("v16.2.15", "qa/cephfs/overrides/ignorelist_health.yaml")
target_health = show("v17.2.7", "qa/cephfs/overrides/ignorelist_health.yaml")
base_down = show("v16.2.15", "qa/cephfs/overrides/ignorelist_wrongly_marked_down.yaml")
target_down = show("v17.2.7", "qa/cephfs/overrides/ignorelist_wrongly_marked_down.yaml")
assert "- FS_" in base_health and "- FS_" not in target_health
assert "compat changed unexpectedly" in base_health
assert "compat changed unexpectedly" not in target_health
assert "POOL_APP_NOT_ENABLED" not in base_health
assert "POOL_APP_NOT_ENABLED" in target_health
assert "- OSD_" in base_down and "- OSD_" not in target_down
assert "- is down" in base_down and "- is down" not in target_down
for suite_path in (
    "qa/suites/fs/upgrade/featureful_client/old_client/overrides/ignorelist_health.yaml",
    "qa/suites/fs/upgrade/featureful_client/upgraded_client/overrides/ignorelist_health.yaml",
    "qa/suites/fs/upgrade/mds_upgrade_sequence/overrides/ignorelist_health.yaml",
    "qa/suites/fs/upgrade/nofs/overrides/ignorelist_health.yaml",
    "qa/suites/fs/upgrade/upgraded_client/overrides/ignorelist_health.yaml",
):
    assert ".qa/cephfs/overrides/ignorelist_health.yaml" in show("v17.2.7", suite_path)

# FS-016: the base endpoint includes a later branch-only fix that strips the
# fstab nofail option before libfuse sees it. Target lacks that compatibility
# fix and only changes EBUSY diagnostic handling.
base_mount_fuse = show("v16.2.15", "src/mount.fuse.ceph")
target_mount_fuse = show("v17.2.7", "src/mount.fuse.ceph")
assert "'defaults', 'noauto', '_netdev', 'nofail'" in base_mount_fuse
assert "'defaults', 'noauto', '_netdev', 'nofail'" not in target_mount_fuse
assert "mount_cmd.returncode != errno.EBUSY" not in base_mount_fuse
assert "mount_cmd.returncode != errno.EBUSY" in target_mount_fuse

# The screened remainder consists of target features/refactors or standalone
# diagnostics/recovery tools. They alter normal target behavior, but none is a
# migration, compatibility negotiation, mixed-version path, or upgrade gate.
nfs_rename = git(
    "diff", "--summary", "--find-renames", "v16.2.15", "v17.2.7", "--",
    "src/pybind/mgr/nfs/export_utils.py", "src/pybind/mgr/nfs/ganesha_conf.py"
).stdout
assert "rename src/pybind/mgr/nfs/{export_utils.py => ganesha_conf.py} (86%)" in nfs_rename
assert "rename_volume" in show("v17.2.7", "src/pybind/mgr/volumes/fs/operations/volume.py")
assert "rename_volume" not in show("v16.2.15", "src/pybind/mgr/volumes/fs/operations/volume.py")
assert "Recover symlinks as symlinks" in git(
    "log", "--format=%s", "v16.2.15..v17.2.7", "--", "src/tools/cephfs/DataScan.cc"
).stdout
mirror_diff = git(
    "diff", "--unified=0", "v16.2.15", "v17.2.7", "--",
    *sorted(path for path in tool_trivial_paths if path.startswith("src/tools/cephfs_mirror/"))
).stdout
assert "std::string_view" in mirror_diff

reasons = {
    "FS-006": (
        "FS-006: the upgraded_client matrix is restructured and expanded to a Pacific source, "
        "upstream kernel client with v1 syntax, and four FUSE-only post-client-upgrade stress workloads; "
        "test_newops also stops skipping kclient. Endpoint paths and shared mount/postmerge "
        "fragments change actual mixed-version coverage."
    ),
    "FS-013": (
        "FS-013: Quincy migrates snap-schedule persistence from an in-memory SQLite SQL-dump "
        "RADOS object to a Ceph SQLite VFS .db object, removes the legacy dump after import, "
        "and creates tables idempotently; reconstruction of active timers after mgr restart "
        "already exists at both endpoints. Persistent schedules and failback after dump "
        "removal need validation."
    ),
    "FS-014": (
        "FS-014: Quincy mount.ceph adds and prefers name@fsid.fs_name=/path device syntax, "
        "fetches fsid, defaults to v2 monitor addresses with prefer-crc, and falls back to the "
        "old monitor:/path syntax for unsupported kernels. Client-package upgrade changes the "
        "local mount path and compatibility behavior."
    ),
    "FS-015": (
        "FS-015: shared health ignorelists linked by CephFS upgrade suites stop suppressing broad "
        "FS/PG/OSD and compatibility messages and add POOL_APP_NOT_ENABLED. This changes upgrade "
        "test acceptance/observability, not production daemon behavior."
    ),
    "FS-016": (
        "FS-016: Pacific 16.2.15 has a later branch-only mount.fuse backport that strips nofail "
        "before libfuse sees it, while Quincy 17.2.7 lacks it. Upgrading this client helper can "
        "therefore regress nofail fstab mounts on libfuse versions that reject the option."
    ),
}

mgr_reason = (
    "FS-MGR-01: screened endpoint changes are normal target behavior or refactoring: NFS config "
    "parser/file reorganization and command/features, snap-schedule CLI validation, volume rename, "
    "formatting, and lock/log cleanup. Auth metadata is already version 6 at both endpoints. "
    "The legacy-subvolume discovery fix is present at both endpoints. No independent migration, "
    "mixed-version, rollback, or upgrade-gate causal path remains; FS-013 is the stateful exception."
)
tool_reason = (
    "FS-TOOL-01: screened CephFS repair/inspection/shell/top and mirror endpoint hunks add normal "
    "target capabilities (including symlink recovery, named-FS shell mounting and first-damage) "
    "or compile/API qualification. They are not invoked by the upgrade workflow and do not "
    "independently change persisted compatibility or rolling-upgrade execution."
)
misc_reason = (
    "FS-CODE-04: the MDS debug override removal, empty suite marker, and ceph-fuse/ceph-mds "
    "argv/std namespace edits affect logging, matrix structure, or source compatibility only; "
    "they do not change an executed upgrade path independently."
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
for cluster, reason in (
    (mgr_trivial_paths, mgr_reason),
    (tool_trivial_paths, tool_reason),
    (misc_trivial_paths, misc_reason),
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
    row["impact_reason"] = reasons[finding]
for cluster, reason in (
    (mgr_trivial_paths, mgr_reason),
    (tool_trivial_paths, tool_reason),
    (misc_trivial_paths, misc_reason),
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
assert (affect_count, trivial_count, blank_count) == (87, 266, 74)

finding_md = """### FS-013 — Snap scheduler chuyển SQL dump sang Ceph SQLite VFS

- **CSV:** 3220–3221. **Nguồn:** `Schedule.CREATE_TABLES`, `SnapSchedClient.get_schedule_db()` và constructor của `SnapSchedClient`; commit `3f4a6ee6f6c4330e5b00deb43f1239bdee6d93c6`, `707543779e24c6bc1489c07f5fa1a239d110d9fb` và `a2dbf943a26bb85c70a58f466efdd54470be4621`.
- **Trước → sau:** Pacific mở SQLite trong bộ nhớ, đọc/ghi một SQL dump tại RADOS object `SNAP_DB_OBJECT_NAME` bằng `iterdump()` sau mỗi thay đổi. Quincy mở `file:///*<metadata-pool-id>:/<object>.db?vfs=ceph`, đặt các PRAGMA cho Ceph VFS, import dump cũ nếu có rồi xóa object dump, và dùng `CREATE TABLE IF NOT EXISTS`. Cả hai endpoint đều duyệt filesystem/lịch đã lưu trong constructor và gọi `refresh_snap_timers()`; tái dựng timer sau restart không phải cải tiến mới của hop này.
- **Điều kiện và tác động:** Áp dụng khi bật `snap_schedule` và đã có lịch trước khi nâng/failover mgr. Active mgr Quincy tự động import legacy dump khi mở DB lần đầu; dump cũ bị xóa sau import, nên rollback thẳng về Pacific có thể không còn object SQL dump mà code cũ chờ đọc. Tác động chính là compatibility/durability của lịch persist; không suy timer Quincy tốt hơn Pacific. **Mixed-version:** failover về mgr Pacific sau migration cần kiểm khả năng đọc lịch; **full Quincy:** kiểm kho VFS, dependency và import thành công. **Độ tin cậy:** cao về endpoint/migration, chưa có RADOS object/lab. **Kiểm chứng:** tạo lịch ở Pacific, lưu danh sách/object và thời điểm snapshot; nâng/restart/failover mgr, xác nhận import chỉ một lần, timer tiếp tục tạo snapshot, object `.db` tồn tại; diễn tập rollback trên bản sao lab. Chưa chạy runtime.

### FS-014 — `mount.ceph` ưu tiên device syntax mới và fallback cho kernel cũ

- **CSV:** 2375–2377. **Nguồn:** `parse_new_dev()`, `mount_new_device_format()`, `mount_old_device_format()`, `should_fallback()` và `mount_ceph_get_config_info()`; commit `8606f5839d5cc9979237eb4a2dbad06658881e70`, `63ac4f9e48ea60e30f66c9e03e3ad20dc96983ce`, `9663f8aaec97de928ac286cdaf35b7c5f7afb69a`, `d5ae180976b62ac97254986de7f734165680e071` và các fix tiếp theo.
- **Trước → sau:** Pacific helper chủ yếu dựng device `<resolved-mon>:/path`. Quincy nhận/dựng `name@fsid.fs_name=/path`, lấy FSID từ config, ưu tiên địa chỉ msgr2 và thêm `ms_mode=prefer-crc` khi phù hợp; nếu mount mới trả `EINVAL`, helper có thể chuyển sang device cũ, địa chỉ v1, `mds_namespace` và `fsid`. `nofallback` chỉ chặn retry khi kernel tự công bố support v2; kernel không có sysfs marker vẫn được fallback.
- **Điều kiện và tác động:** Kích hoạt khi nâng package client có `mount.ceph`, kể cả khi MDS/cluster vẫn ở Pacific; phần parse/mount nằm ở client/kernel cục bộ. Kernel cũ dựa vào fallback, còn automation truyền device mới, `mon_addr`, `ms_mode` hoặc `nofallback` đi qua nhánh khác trước đây. **Full Quincy:** không đảm bảo mọi kernel distro hỗ trợ v2. **Độ tin cậy:** cao về code, chưa biết kernel/client matrix As-Is. **Kiểm chứng:** trên từng kernel distro, mount cùng filesystem bằng device cũ và mới, với/không `nofallback`, msgr1-only/msgr2 và config có nhiều FS; xác nhận source trong `/proc/mounts`, I/O và remount sau reboot. Chưa chạy lab.

### FS-015 — Shared health ignorelist làm đổi tín hiệu pass/fail của các suite upgrade

- **CSV:** 447–448. **Nguồn:** `qa/cephfs/overrides/{ignorelist_health,ignorelist_wrongly_marked_down}.yaml`; các suite `featureful_client`, `mds_upgrade_sequence`, `nofs`, `upgraded_client` và `volumes/import-legacy` đều symlink tới các fragment này. Commit `698e37884c0ff44117ad48bd33ab381d0ce4c028` thêm ngoại lệ cụ thể `POOL_APP_NOT_ENABLED`; rename `whitelist` → `ignorelist` không phải căn cứ chính.
- **Trước → sau:** Pacific bỏ qua các pattern rộng như `FS_`, `PG_`, `OSD_`, `compat changed unexpectedly`, `is down` và một số cảnh báo degradation. Quincy bỏ phần lớn pattern rộng đó, dùng regex cụ thể hơn cho OSD và thêm `POOL_APP_NOT_ENABLED`.
- **Điều kiện và tác động:** Nếu dùng upstream CephFS upgrade suites làm gate, target sẽ phơi ra/fail trên nhiều health log mà Pacific che khuất, nhưng lại chấp nhận riêng cảnh báo application tag của pool. Đây là thay đổi **validation acceptance/observability**, không cấu hình production và không chứng minh daemon runtime khác. **Độ tin cậy:** cao về symlink và YAML; chưa có teuthology result. **Kiểm chứng:** chạy cùng scenario 16.2.15 → 17.2.7 với log archive, đối chiếu warning nào từng bị ignore, và chỉ bổ sung local exception sau khi chứng minh expected/transient. Chưa chạy suite.

### FS-016 — Quincy thiếu backport Pacific loại `nofail` trước khi gọi libfuse

- **CSV:** 2374. **Nguồn:** `mount.fuse.ceph::fs_options()`; commit `2593eec40208f614928448494bea20aa8a885f80` có ở Pacific 16.2.15 nhưng không là ancestor của Quincy 17.2.7. Target còn đổi việc in lỗi `EBUSY`, nhưng đó chủ yếu là diagnostics.
- **Trước → sau:** Pacific loại `defaults`, `noauto`, `_netdev` **và** `nofail` khỏi options đưa cho `ceph-fuse`, với chú thích libfuse cũ không nhận `nofail` và từ FUSE 3.2.2 mới tự bỏ qua. Quincy chỉ loại ba option đầu, nên `nofail` có thể đi tới libfuse.
- **Điều kiện và tác động:** Chỉ áp dụng cho mount CephFS FUSE qua fstab/systemd có `nofail` và client dùng libfuse không tự ignore option. Nâng client helper từ endpoint Pacific mới hơn về hành vi sang Quincy 17.2.7 có thể làm mount fail dù major release tăng; server/MDS mixed version không liên quan. **Độ tin cậy:** cao về backport/net diff, chưa biết phiên bản libfuse As-Is. **Kiểm chứng:** inventory `/etc/fstab` và `fusermount3 --version`; reboot/mount lab với `nofail` trên đúng distro, kiểm exit/log/mount table, hoặc giữ patch/vendor package nếu còn libfuse cũ. Chưa chạy runtime.

"""
insert_before_once(md_path, "## Trivial changes", finding_md)

replace_known(
    md_path,
    "Hiện **`affect = 72`, `trivial = 216`, chưa phân loại = 139**.",
    "Hiện **`affect = 87`, `trivial = 266`, chưa phân loại = 74**.",
)
replace_known(
    md_path,
    "- **CSV:** 629–661 và 1375. **Nguồn:** `qa/suites/fs/upgrade/upgraded_client/**`, `qa/tasks/cephfs/test_newops.py`; commit `bdd93b44bc68bc06a07e11b74546f6c8ce1c5758`, `ec46a59720db2f23c5409a7ae8ddbe11583160d3`, `623f226c57ebf9067c2975febaf9abcf504f5eb5`.",
    "- **CSV:** 439, 441–446, 629–661 và 1375. **Nguồn:** `qa/suites/fs/upgrade/upgraded_client/**`, shared matrix `qa/cephfs/mount/**`, `qa/tasks/cephfs/test_newops.py`; commit `bdd93b44bc68bc06a07e11b74546f6c8ce1c5758`, `ec46a59720db2f23c5409a7ae8ddbe11583160d3`, `623f226c57ebf9067c2975febaf9abcf504f5eb5`, `48dd06f13b33def06481816f408c12433743c21f` và `903a14f756cd057a408b22a3eee8b236b47d4423`.",
)
replace_known(
    md_path,
    "**216 hàng** đã sàng lọc: ngoài các cụm QA `FS-QA-04–12`, batch mới có 31 hàng tài liệu `FS-DOC-01`, 16 header journal-event `FS-CODE-01`, 51 message header không đổi wire payload `FS-CODE-02` và ba cleanup runtime `FS-CODE-03`. Các ngoại lệ hành vi/wire được giữ `affect` trong FS-009–012.",
    "**266 hàng** đã sàng lọc: ngoài các cụm QA `FS-QA-04–12`, tài liệu và runtime/wire trước đó, batch mới có 22 hàng mgr/NFS/volumes `FS-MGR-01`, 24 hàng công cụ/cephfs-mirror `FS-TOOL-01` và bốn cleanup/marker `FS-CODE-04`. Các ngoại lệ state/mount và gate QA được giữ `affect` trong FS-013–016; shared mount matrix được nối vào FS-006.",
)
replace_known(md_path, "Phân loại 139 hàng còn trống", "Phân loại 74 hàng còn trống")

replace_known(
    readme_path,
    "1.497 hàng `affect`. 1.712 hàng `trivial`. 970 hàng chưa phân loại.",
    "1.512 hàng `affect`. 1.762 hàng `trivial`. 905 hàng chưa phân loại.",
)
replace_known(
    readme_path,
    "[FS-001–012](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence/mount syntax, cephadm workload, no-FS gate, upgraded-client matrix, khoảng trống import legacy, hội tụ rank pre-upgrade, eviction khi OSD laggy, ACK unlink, refresh feature bits và legacy retry/fwd",
    "[FS-001–016](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence, upgraded-client matrix, legacy import, eviction khi OSD laggy, ACK unlink, feature bits, retry/fwd, snap-schedule state, kernel/FUSE mount và health gate",
)
replace_known(
    readme_path,
    "[FS-001–012](./11-cephfs-mds.md) về baseline client, MDS upgrade sequence, cephadm workload, no-FS gate, upgraded-client matrix, khoảng trống import legacy, hội tụ rank pre-upgrade, eviction khi OSD laggy, ACK unlink, refresh feature bits và legacy retry/fwd",
    "[FS-001–016](./11-cephfs-mds.md) về baseline client, MDS upgrade sequence, upgraded-client matrix, legacy import, eviction khi OSD laggy, ACK unlink, feature bits, retry/fwd, snap-schedule state, kernel/FUSE mount và health gate",
)
replace_known(readme_path, "vì 970 hàng còn thiếu nhãn và lý do", "vì 905 hàng còn thiếu nhãn và lý do")

replace_known(
    plan_path,
    "`affect 1.497`, `trivial 1.712`, còn **970 hàng chưa phân loại**",
    "`affect 1.512`, `trivial 1.762`, còn **905 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 11 hiện `72 affect`, `216 trivial`, `139` chưa phân loại",
    "owner 11 hiện `87 affect`, `266 trivial`, `74` chưa phân loại",
)

print("Classified owner-11 mgr/mount/tools batch: 15 affect, 50 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
