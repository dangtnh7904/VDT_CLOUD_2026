"""Classify owner-11 CephFS upgrade/workload QA changes with endpoint evidence."""

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


nofs_paths = {
    "qa/suites/fs/upgrade/nofs/tasks/0-octopus.yaml",
    "qa/suites/fs/upgrade/nofs/tasks/1-upgrade.yaml",
}

workload_paths = {
    "qa/suites/fs/workload/0-rhel_8.yaml",
    "qa/suites/fs/workload/begin.yaml",
    "qa/suites/fs/workload/begin/+",
    "qa/suites/fs/workload/begin/.qa",
    "qa/suites/fs/workload/begin/0-install.yaml",
    "qa/suites/fs/workload/begin/1-cephadm.yaml",
    "qa/suites/fs/workload/begin/2-logrotate.yaml",
}

upgraded_client_paths = {
    "qa/suites/fs/upgrade/upgraded_client/%",
    "qa/suites/fs/upgrade/upgraded_client/bluestore-bitmap.yaml",
    "qa/suites/fs/upgrade/upgraded_client/centos_latest.yaml",
    "qa/suites/fs/upgrade/upgraded_client/clusters/%",
    "qa/suites/fs/upgrade/upgraded_client/clusters/.qa",
    "qa/suites/fs/upgrade/upgraded_client/clusters/1-mds-1-client-micro.yaml",
    "qa/suites/fs/upgrade/upgraded_client/conf",
    "qa/suites/fs/upgrade/upgraded_client/from_nautilus/bluestore-bitmap.yaml",
    "qa/suites/fs/upgrade/upgraded_client/from_nautilus/centos_latest.yaml",
    "qa/suites/fs/upgrade/upgraded_client/overrides/%",
    "qa/suites/fs/upgrade/upgraded_client/overrides/.qa",
    "qa/suites/fs/upgrade/upgraded_client/overrides/ignorelist_health.yaml",
    "qa/suites/fs/upgrade/upgraded_client/overrides/ignorelist_wrongly_marked_down.yaml",
    "qa/suites/fs/upgrade/upgraded_client/overrides/pg-warn.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/%",
    "qa/suites/fs/upgrade/upgraded_client/tasks/.qa",
    "qa/suites/fs/upgrade/upgraded_client/tasks/0-from/nautilus.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/0-from/pacific.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/1-mount/.qa",
    "qa/suites/fs/upgrade/upgraded_client/tasks/1-mount/mount",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/.qa",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/new_ops/%",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/new_ops/0-clients/fuse-upgrade.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/new_ops/0-clients/kclient.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/new_ops/1-client-sanity.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/%",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/.qa",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/0-client-upgrade.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/1-tests/.qa",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/1-tests/blogbench.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/1-tests/dbench.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/1-tests/fsstress.yaml",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/1-tests/iozone.yaml",
    "qa/tasks/cephfs/test_newops.py",
}

import_legacy_paths = {
    "qa/suites/fs/upgrade/volumes/import-legacy/bluestore-bitmap.yaml",
    "qa/suites/fs/upgrade/volumes/import-legacy/clusters/1-mds-2-client-micro.yaml",
    "qa/suites/fs/upgrade/volumes/import-legacy/conf",
    "qa/suites/fs/upgrade/volumes/import-legacy/overrides/ignorelist_wrongly_marked_down.yaml",
    "qa/suites/fs/upgrade/volumes/import-legacy/tasks/1-client.yaml",
    "qa/suites/fs/upgrade/volumes/import-legacy/tasks/2-upgrade.yaml",
    "qa/suites/fs/upgrade/volumes/import-legacy/tasks/3-verify.yaml",
    "qa/suites/fs/upgrade/volumes/import-legacy/ubuntu_18.04.yaml",
    "qa/workunits/fs/upgrade/volume_client",
}

support_paths = {"qa/tasks/cephfs/test_volume_client.py"}
affect_paths = nofs_paths | workload_paths | upgraded_client_paths | import_legacy_paths
paths = affect_paths | support_paths
assert len(nofs_paths) == 2
assert len(workload_paths) == 7
assert len(upgraded_client_paths) == 34
assert len(import_legacy_paths) == 9
assert len(affect_paths) == 52
assert len(paths) == 53

# Avoid Git's cross-directory empty-marker rename pairings: every endpoint path
# must independently appear in a no-renames net diff.
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

for commit in (
    "97f9f5362bea855628c2f82c31176bd129db19b7",
    "bc2eaba8c6616c3469ac85d36ee21f3e9765cf42",
    "e2c7fe2e7f12bedc8b42d9db4d08fdb61d8549bd",
    "bdd93b44bc68bc06a07e11b74546f6c8ce1c5758",
    "ec46a59720db2f23c5409a7ae8ddbe11583160d3",
    "623f226c57ebf9067c2975febaf9abcf504f5eb5",
    "a3db265ad5b3ff899d8b71164a7f9ea5a426b19e",
):
    assert ancestor(commit, "v17.2.7"), commit
assert ancestor("38352858098bebe1196a8f225efc689a995f3349", "v16.2.15")

assert "- ceph-volume" not in show("v16.2.15", next(iter(nofs_paths - {"qa/suites/fs/upgrade/nofs/tasks/1-upgrade.yaml"})))
assert "- ceph-volume" in show("v17.2.7", "qa/suites/fs/upgrade/nofs/tasks/0-octopus.yaml")
assert "require-osd-release pacific" in show("v16.2.15", "qa/suites/fs/upgrade/nofs/tasks/1-upgrade.yaml")
assert "require-osd-release quincy" in show("v17.2.7", "qa/suites/fs/upgrade/nofs/tasks/1-upgrade.yaml")

assert show("v16.2.15", "qa/suites/fs/workload/begin.yaml").strip() == ".qa/cephfs/begin.yaml"
assert not exists("v17.2.7", "qa/suites/fs/workload/begin.yaml")
cephadm_begin = show("v17.2.7", "qa/suites/fs/workload/begin/1-cephadm.yaml")
assert "- cephadm:" in cephadm_begin and "roleless: false" in cephadm_begin
assert "ceph orch status" in cephadm_begin and "fs.ready:" in cephadm_begin
assert "rhel_8.4_container_tools_rhel8.yaml" in show("v17.2.7", "qa/suites/fs/workload/0-rhel_8.yaml")

assert not exists("v16.2.15", "qa/suites/fs/upgrade/upgraded_client/tasks/0-from/pacific.yaml")
pacific_source = show("v17.2.7", "qa/suites/fs/upgrade/upgraded_client/tasks/0-from/pacific.yaml")
assert "branch: pacific" in pacific_source
assert "set-require-min-compat-client pacific" in pacific_source
kclient = show("v17.2.7", "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/new_ops/0-clients/kclient.yaml")
assert "is_kupstream()" in kclient and "syntax_version() == 'v2'" in kclient
# The separate stress cohort upgrades and remounts FUSE clients only;
# kernel v1 new-op coverage does not make these four stress jobs kernel tests.
stress_upgrade = show(
    "v17.2.7",
    "qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/0-client-upgrade.yaml",
)
assert "if not is_fuse() then reject() end" in stress_upgrade
assert "- ceph-fuse:" in stress_upgrade and "- install.upgrade:" in stress_upgrade
for workload in ("blogbench", "dbench", "fsstress", "iozone"):
    path = f"qa/suites/fs/upgrade/upgraded_client/tasks/2-workload/stress_tests/1-tests/{workload}.yaml"
    assert exists("v17.2.7", path) and not exists("v16.2.15", path)
base_newops = show("v16.2.15", "qa/tasks/cephfs/test_newops.py")
target_newops = show("v17.2.7", "qa/tasks/cephfs/test_newops.py")
assert "skipTest(\"Currently kclient hasn't fixed new ops issue yet.\")" in base_newops
assert "skipTest" not in target_newops

for path in import_legacy_paths | support_paths:
    assert exists("v16.2.15", path) and not exists("v17.2.7", path), path
assert exists("v16.2.15", "src/pybind/ceph_volume_client.py")
assert not exists("v17.2.7", "src/pybind/ceph_volume_client.py")
legacy_upgrade = show("v16.2.15", "qa/suites/fs/upgrade/volumes/import-legacy/tasks/2-upgrade.yaml")
legacy_verify = show("v16.2.15", "qa/suites/fs/upgrade/volumes/import-legacy/tasks/3-verify.yaml")
assert "mds_pre_upgrade" in legacy_upgrade and "require-osd-release pacific" in legacy_upgrade
assert "ACTION: verify" in legacy_verify and "ceph fs subvolume ls cephfs" in legacy_verify

reasons = {
    "FS-004": (
        "FS-004: the fs:workload Teuthology matrix changes from the classic ceph task to "
        "cephadm deployment, adds orchestrator/fs.ready checks, and pins the RHEL 8 container-tools "
        "fragment. This changes the executed validation environment and acceptance path, not production automatically."
    ),
    "FS-005": (
        "FS-005: the no-CephFS upgrade recipe now excludes ceph-volume from the Octopus install "
        "and raises require-osd-release from Pacific to Quincy. These commands alter the executed "
        "upgrade gate and its health outcome when this suite is used."
    ),
    "FS-006": (
        "FS-006: the upgraded_client matrix is restructured and expanded to a Pacific source, "
        "upstream kernel client with v1 syntax, and four FUSE-only post-client-upgrade stress workloads; "
        "test_newops also stops skipping kclient. Endpoint paths and markers change actual mixed-version coverage."
    ),
    "FS-007": (
        "FS-007: Quincy removes the import-legacy upgrade recipe/workunit that created legacy "
        "ceph_volume_client subvolumes, restarted MON/OSD/MDS, and verified data afterward. "
        "The upstream gate therefore no longer validates this migration path."
    ),
}
support_reason = (
    "FS-QA-05: deletion of the standalone test_volume_client.py follows removal of the legacy "
    "ceph_volume_client library and only removes supporting unit/functional coverage. The actual "
    "upgrade-recipe loss is recorded separately in FS-007."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)

finding_for_path = {}
for path in workload_paths:
    finding_for_path[path] = "FS-004"
for path in nofs_paths:
    finding_for_path[path] = "FS-005"
for path in upgraded_client_paths:
    finding_for_path[path] = "FS-006"
for path in import_legacy_paths:
    finding_for_path[path] = "FS-007"
assert set(finding_for_path) == affect_paths

for path, finding in finding_for_path.items():
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

for path, finding in finding_for_path.items():
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
totals = (affect_count, trivial_count, blank_count)
assert totals in {
    (59, 54, 314),
    (59, 77, 291),
    (59, 108, 260),
    (61, 115, 251),
}
if totals != (59, 54, 314):
    print("Classified owner-11 CephFS upgrade/workload QA batch: 52 affect, 1 trivial")
    print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
    raise SystemExit(0)

findings_md = """### FS-004 — Suite `fs:workload` chuyển môi trường triển khai sang cephadm

- **CSV:** 680–686. **Nguồn:** `qa/suites/fs/workload/{0-rhel_8.yaml,begin/**}`; commit `e2c7fe2e7f12bedc8b42d9db4d08fdb61d8549bd`, cùng `144eb49509f0748afcc118630a8f1e9fa5d1aa7e` và `5a33ef6bdd250b104faf3e9e1a657733f2850452` cho distro/container tools.
- **Trước → sau:** Pacific nối suite vào `.qa/cephfs/begin.yaml`, dùng task `ceph`. Quincy giữ bước cài package workload nhưng dựng cluster bằng `cephadm`, chạy các lệnh `ceph orch`, kiểm `ceph fs dump`/`ceph osd dump`, rồi chờ `fs.ready`; matrix distro được thu về RHEL 8.4 kèm container tools.
- **Điều kiện và tác động:** Chỉ ảnh hưởng khi dùng upstream `fs:workload` làm gate. Cùng workload giờ được nghiệm thu trên deployment cephadm thay vì classic task, nên lỗi phụ thuộc deployment hoặc distro có thể xuất hiện/mất khỏi tín hiệu stop/go. Đây không phải thay đổi tự chạy trên production. **Độ tin cậy:** cao về endpoint/task, trung bình về pipeline người dùng. **Kiểm chứng:** chạy workload đại diện trên cả deployment kiểu As-Is và cephadm với cùng client/MDS, so sánh mount, I/O, failover và log; chưa chạy lab.

### FS-005 — Gate upgrade không có CephFS đổi package exclusion và OSD release đích

- **CSV:** 627–628. **Nguồn:** `qa/suites/fs/upgrade/nofs/tasks/{0-octopus,1-upgrade}.yaml`; commit `97f9f5362bea855628c2f82c31176bd129db19b7` và `bc2eaba8c6616c3469ac85d36ee21f3e9765cf42`.
- **Trước → sau:** recipe Quincy loại `ceph-volume` khỏi bước cài Octopus và sau restart OSD gọi `ceph osd require-osd-release quincy` thay vì `pacific`. Suite vẫn kiểm cluster không có CephFS qua `ceph fs dump`, restart MON/MGR/OSD và `ceph.healthy`.
- **Điều kiện và tác động:** Thay đổi **execution/acceptance** của suite `nofs`: tránh cài package không phù hợp ở nguồn và đánh giá health với release đích đúng Quincy. Không chứng minh lệnh này được chạy ngoài QA. Mixed-version được bao phủ trong restart; sau nâng cấp gate yêu cầu OSD release Quincy. **Độ tin cậy:** cao. **Kiểm chứng:** pin nguồn đúng 16.2.15, chạy cluster không tạo filesystem, lưu package set, `ceph versions`, FSMap và health trước/sau; chưa chạy lab.

### FS-006 — Ma trận `upgraded_client` mở rộng Pacific, kernel client và stress workload

- **CSV:** 629–661 và 1375. **Nguồn:** `qa/suites/fs/upgrade/upgraded_client/**`, `qa/tasks/cephfs/test_newops.py`; commit `bdd93b44bc68bc06a07e11b74546f6c8ce1c5758`, `ec46a59720db2f23c5409a7ae8ddbe11583160d3`, `623f226c57ebf9067c2975febaf9abcf504f5eb5`. Một số marker rỗng bị inventory ghép thành rename với path không liên quan; kết luận dùng endpoint `--no-renames` và nội dung suite, không dựa vào heuristic đó.
- **Trước → sau:** Pacific chủ yếu có đường Nautilus rồi nâng client FUSE và chạy sanity `getvxattr`. Quincy tái cấu trúc thành nguồn Nautilus **hoặc Pacific**, thêm nguồn `set-require-min-compat-client pacific`, lựa chọn mount FUSE/kernel, cho kernel upstream cú pháp v1 chạy new-op, và thêm blogbench/dbench/fsstress/iozone sau nâng client FUSE. `test_newops.py` bỏ skip nội bộ cho kernel vì filter chuyển sang fragment `postmerge`; riêng stress cohort còn `if not is_fuse() then reject() end`, nên bốn stress workload không phải coverage kernel upstream.
- **Điều kiện và tác động:** Nếu dùng suite này, coverage mixed-version “client mới/cluster cũ” rộng hơn đáng kể, đặc biệt đúng hướng Pacific → Quincy và kernel client. Filter vẫn loại kernel downstream hoặc syntax v2, nên suite chưa chứng minh các tổ hợp đó. Đây là validation coverage, không tự thay đổi client production. **Độ tin cậy:** cao về ma trận endpoint; trung bình về kernel/distro As-Is. **Kiểm chứng:** pin Pacific 16.2.15, chạy FUSE và kernel v1 qua `getfattr ceph.dir.pin.random` cùng bốn workload, quan sát MDS crash/session feature và I/O; chưa chạy lab.

### FS-007 — Quincy bỏ gate import từ legacy `ceph_volume_client`

- **CSV owner 11:** 662–669 và 1441; hàng 1382 là test hỗ trợ `trivial`. **Bằng chứng liên owner:** `src/pybind/ceph_volume_client.py` thuộc owner 15 cũng vắng ở endpoint Quincy và chưa được kết luận tại đây. Commit target `a3db265ad5b3ff899d8b71164a7f9ea5a426b19e` loại library/suite; Pacific có revert riêng `38352858098bebe1196a8f225efc689a995f3349` vì Manila còn dùng library trong thêm một release.
- **Trước → sau:** Pacific có recipe tạo hai volume bằng `CephFSVolumeClient`, mount/populate dữ liệu, chạy `mds_pre_upgrade`, restart MON/MGR/OSD/MDS, rồi dùng CLI subvolume để xác nhận volume và dữ liệu còn tồn tại. Quincy không còn recipe/workunit này.
- **Điều kiện và tác động:** Upstream Quincy không còn gate chứng minh migration của dữ liệu/authorization được tạo bởi legacy API qua nâng cấp. Khả năng áp dụng phụ thuộc As-Is có Manila hoặc automation còn import module này hay không; ảnh hưởng packaging/runtime cuối cùng phải đối chiếu owner 15 và package inventory. Trong mixed-version/full-version, báo cáo này chỉ kết luận **khoảng trống validation**, không kết luận dữ liệu sẽ lỗi. **Độ tin cậy:** cao về endpoint và lịch sử hai nhánh, trung bình về deployment. **Kiểm chứng:** inventory import/package/client trước rollout; nếu còn dùng, tái dựng recipe Pacific 16.2.15, populate dữ liệu, nâng lab và xác nhận auth/subvolume/data; chưa chạy lab.

"""

replace_known(
    md_path,
    "`affect = 7`, `trivial = 53`, chưa phân loại = 367",
    "`affect = 59`, `trivial = 54`, chưa phân loại = 314",
)
insert_before_once(md_path, "## Trivial changes", findings_md)
replace_known(
    md_path,
    "**53 hàng** đã sàng lọc: 134 chỉ thêm anchor Sphinx trước tiêu đề trong `doc/cephfs/upgrading.rst`; 619 và 622 chỉ đổi câu `print`; 50 hàng `FS-QA-04` tách cấu hình `begin` thành các fragment tương đương hoặc dùng lại health ignorelist chung, không đổi runtime được phát hành.",
    "**54 hàng** đã sàng lọc: 134 chỉ thêm anchor Sphinx; 619 và 622 chỉ đổi câu `print`; 50 hàng `FS-QA-04` đổi layout/ignorelist QA; hàng 1382 (`FS-QA-05`) chỉ bỏ test hỗ trợ cho legacy volume client, còn mất gate upgrade thực tế đã được giữ là `affect` trong FS-007.",
)
replace_known(md_path, "Phân loại 367 hàng còn trống", "Phân loại 314 hàng còn trống")
replace_known(
    readme_path,
    "1.432 hàng `affect`. 1.549 hàng `trivial`. 1.198 hàng chưa phân loại.",
    "1.484 hàng `affect`. 1.550 hàng `trivial`. 1.145 hàng chưa phân loại.",
)
replace_known(
    readme_path,
    "[VOL-001–003](./09-ceph-volume-activation.md) cho inventory, encrypted zap và tox gate; [RADOS-001–016]",
    "[VOL-001–003](./09-ceph-volume-activation.md) cho inventory, encrypted zap và tox gate; [FS-001–007](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence, cephadm workload, no-FS gate, upgraded-client matrix và khoảng trống import legacy; [RADOS-001–016]",
)
replace_known(readme_path, "vì 1.198 hàng còn thiếu nhãn và lý do", "vì 1.145 hàng còn thiếu nhãn và lý do")
replace_known(
    plan_path,
    "`affect 1.432`, `trivial 1.549`, còn **1.198 hàng chưa phân loại**",
    "`affect 1.484`, `trivial 1.550`, còn **1.145 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 11 hiện `7 affect`, `53 trivial`, `367` chưa phân loại",
    "owner 11 hiện `59 affect`, `54 trivial`, `314` chưa phân loại",
)

print("Classified owner-11 CephFS upgrade/workload QA batch: 52 affect, 1 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
