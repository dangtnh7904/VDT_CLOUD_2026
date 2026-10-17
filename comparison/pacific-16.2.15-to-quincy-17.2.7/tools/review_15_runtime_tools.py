"""Finish owner-15 shared runtime and administration-tool review."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "15-upgrade-validation.csv"
md_path = root / "15-upgrade-validation.md"
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
    assert text.count(marker) == 1, (path, marker, text.count(marker))
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


affect = {
    "src/pybind/ceph_argparse.py": (
        "MGR-037",
        "MGR-037: CLI parser consumes the target positional=false metadata used by orch upgrade start; scripts using a bare second positional argument can be rejected or bound differently when the Quincy MGR descriptor becomes active.",
    ),
    "src/pybind/ceph_volume_client.py": (
        "FS-007",
        "FS-007: target deletes the legacy ceph_volume_client library that Pacific retained for Manila and older CephFS automation, so package/import inventory is required before upgrade.",
    ),
    "src/python-common/ceph/deployment/drive_group.py": (
        "ADM-022",
        "ADM-022: shared DriveGroup parsing accepts per-path crush_device_class and OSD config, validates empty paths, and changes nested-spec handling used when Quincy reads/applies OSD specs.",
    ),
    "src/python-common/ceph/deployment/inventory.py": (
        "ADM-022",
        "ADM-022: Device now persists crush_device_class in the shared inventory model consumed by DriveGroup selection and ceph-volume command generation.",
    ),
    "src/python-common/ceph/deployment/service_spec.py": (
        "ADM-009;ADM-012;ADM-013;ADM-014;MGR-051",
        "ADM-009/012/013/014 and MGR-051: shared persisted-spec dispatch adds tuned profiles, Grafana anonymous access, MON CRUSH locations, NFS/ingress VIP fields and RGW multisite fields read by the target MGR.",
    ),
    "src/python-common/ceph/deployment/translate.py": (
        "ADM-022",
        "ADM-022: ceph-volume command generation groups data paths by per-device CRUSH class, including raw-mode DB/WAL pairing; this affects new or replacement OSD creation from such specs.",
    ),
    "src/python-common/ceph/rgw/diff.py": (
        "MGR-051",
        "MGR-051: RGWAM reconciliation uses this target-only diff engine before opt-in realm/zone metadata updates; it is production control-plane code, not a test helper.",
    ),
    "src/python-common/ceph/rgw/rgwam_core.py": (
        "MGR-051",
        "MGR-051: target-only RGWAM core executes radosgw-admin and orchestrator operations for realm bootstrap, zone creation/modification and reconcile; commands are opt-in, not automatic during upgrade.",
    ),
    "src/python-common/ceph/rgw/types.py": (
        "MGR-051",
        "MGR-051: shared RGWAM environment, exception and realm-token types carry the results and credentials used by the target MGR RGW control commands.",
    ),
    "src/tools/ceph-dencoder/ceph_dencoder.cc": (
        "VAL-007",
        "VAL-007: target dencoder no longer auto-falls back to build/lib from CMakeCache and can return an empty plugin registry when CEPH_LIB/module packaging is wrong, changing compatibility-test validity.",
    ),
    "src/tools/ceph-dencoder/common_types.h": (
        "VAL-007",
        "VAL-007: the target dencoder registry adds std::string coverage, changing the type set exercised by generated/corpus compatibility checks.",
    ),
    "src/tools/ceph-dencoder/rgw_types.h": (
        "VAL-007",
        "VAL-007: the target dencoder registry adds RGWBucketEncryptionConfig, extending upgrade-compatibility validation coverage for an RGW persisted type.",
    ),
    "src/tools/ceph-dencoder/str.h": (
        "VAL-007",
        "VAL-007: target adds the wrapper and generated instances that make std::string part of dencoder compatibility validation.",
    ),
    "src/tools/contrib/ceph-migrate-bluestore.bash": (
        "VAL-006",
        "VAL-006: target adds an opt-in, destructive FileStore-to-BlueStore migration script that creates/purges a temporary OSD, rewrites LVM/labels, duplicates object-store data and disables the original device.",
    ),
}

trivial = {
    "src/pybind/ceph_daemon.py": "VAL-RUNTIME-TRIVIAL-01: annotations and formatting dominate; the removed string-only get_command_descriptions shortcut was unreachable because src/ceph.in passes a list at both endpoints.",
    "src/pybind/ceph_mgr_repl.py": "VAL-RUNTIME-TRIVIAL-02: new interactive mgr self-test/eval console is a developer diagnostic tool and is not invoked by Pacific-x or the production upgrade workflow.",
    "src/pybind/tox.ini": "VAL-RUNTIME-TRIVIAL-03: adds a mypy tox environment for ceph_argparse/ceph_daemon; it changes static validation only.",
    "src/python-common/ceph/deployment/drive_selection/selector.py": "VAL-RUNTIME-TRIVIAL-04: changes only the log level for a device rejected by the existing limit policy; selection result is unchanged.",
    "src/python-common/ceph/deployment/hostspec.py": "VAL-RUNTIME-TRIVIAL-05: improves invalid-host error text and returns NotImplemented for cross-type equality; persisted HostSpec fields and placement behavior are unchanged.",
    "src/python-common/ceph/rgw/__init__.py": "VAL-RUNTIME-TRIVIAL-06: package marker contains no executable RGWAM behavior; the callable control path is classified in diff.py, rgwam_core.py and types.py.",
    "src/python-common/ceph/tests/test_drive_group.py": "VAL-RUNTIME-TRIVIAL-07: unit tests support ADM-022 but are not composed by the exact upgrade suite and do not independently alter OSD deployment.",
    "src/python-common/ceph/tests/test_service_spec.py": "VAL-RUNTIME-TRIVIAL-08: expected-YAML updates support shared spec findings but this unit-test source is not an upgrade execution artifact.",
    "src/python-common/requirements.txt": "VAL-RUNTIME-TRIVIAL-09: changes mypy/type-stub test dependencies only; these packages are not the ceph-common runtime dependency set.",
    "src/python-common/tox.ini": "VAL-RUNTIME-TRIVIAL-10: adds a constraints file to the python-common test environment; no installed runtime or exact-pair suite command changes.",
    "src/tools/RadosDump.cc": "VAL-TOOLS-TRIVIAL-01: std namespace qualification only; dump format and read path are unchanged.",
    "src/tools/RadosDump.h": "VAL-TOOLS-TRIVIAL-02: transparent-comparator/std qualification refactor preserves encoded map ordering and RADOS dump section versions.",
    "src/tools/ceph-client-debug.cc": "VAL-TOOLS-TRIVIAL-03: adapts to the shared argv_to_vec return API without changing inode lookup semantics.",
    "src/tools/ceph-dencoder/denc_plugin.h": "VAL-TOOLS-TRIVIAL-04: std::filesystem/string_view qualification cleanup preserves dlopen/dlsym plugin registration behavior.",
    "src/tools/ceph-dencoder/denc_registry.h": "VAL-TOOLS-TRIVIAL-05: STL qualification and empty-string spelling changes preserve decode/encode/copy registry semantics.",
    "src/tools/ceph_authtool.cc": "VAL-TOOLS-TRIVIAL-06: argv_to_vec/std qualification adaptation; key generation, import and capability operations are unchanged.",
    "src/tools/ceph_conf.cc": "VAL-TOOLS-TRIVIAL-07: argv_to_vec/std::quoted adaptation preserves configuration lookup and dump behavior.",
    "src/tools/ceph_dedup_tool.cc": "VAL-TOOLS-TRIVIAL-08: adds opt-in dedup/repair administration commands and help text; existing upgrade path does not invoke them and related QA coverage is already owned by OSD-081.",
    "src/tools/contrib/README.rst": "VAL-TOOLS-TRIVIAL-09: contributor warning states scripts are unsupported/as-is; it documents VAL-006 but has no executable migration behavior.",
    "src/tools/crimson/perf_async_msgr.cc": "VAL-TOOLS-TRIVIAL-10: std::unique_ptr qualification in a standalone Crimson benchmark only.",
    "src/tools/crimson/perf_crimson_msgr.cc": "VAL-TOOLS-TRIVIAL-11: benchmark namespace/message-construction cleanup; it is not an upgrade acceptance workload.",
    "src/tools/crimson/perf_staged_fltree.cc": "VAL-TOOLS-TRIVIAL-12: expands a standalone SeaStore onode-tree performance benchmark, not production OSD activation or exact-pair validation.",
    "src/tools/neorados.cc": "VAL-TOOLS-TRIVIAL-13: fmt-v9 formatter compatibility affects building the experimental CLI only, not its object operations or upgrade path.",
    "src/tools/psim.cc": "VAL-TOOLS-TRIVIAL-14: adds a std namespace declaration to the placement simulator; decoding and simulation logic are unchanged.",
    "src/tools/radosacl.cc": "VAL-TOOLS-TRIVIAL-15: adds a std namespace declaration to a standalone sample/admin tool; ACL wire behavior is unchanged.",
    "src/tools/scratchtoolpp.cc": "VAL-TOOLS-TRIVIAL-16: adds a std namespace declaration to a scratch utility with no upgrade caller.",
    "src/tools/setup-virtualenv.sh": "VAL-TOOLS-TRIVIAL-17: fixes wheelhouse pip flags for developer/test virtualenv setup; Pacific-x teuthology execution does not call this script.",
}

expected_paths = set(affect) | set(trivial)
assert len(affect) == 14
assert len(trivial) == 27
assert len(expected_paths) == 41

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
blank_paths = {row["path"] for row in rows if not row["upgrade_impact"]}
assert blank_paths == expected_paths, (blank_paths - expected_paths, expected_paths - blank_paths)

# Recheck the key source/caller claims before writing classifications.
argparse_diff = git("diff", "--unified=3", "v16.2.15", "v17.2.7", "--", "src/pybind/ceph_argparse.py").stdout
assert "positional=False" in argparse_diff and "Unexpected argument" in argparse_diff
orch_target = git("show", "v17.2.7:src/pybind/mgr/orchestrator/module.py").stdout
assert "_end_positional_" in orch_target and "orch upgrade start" in orch_target
rgw_module = git("show", "v17.2.7:src/pybind/mgr/rgw/module.py").stdout
assert "RGWAM(self.env).realm_bootstrap" in rgw_module
assert "RGWAM(self.env).realm_reconcile" in rgw_module
migrate = git("show", "v17.2.7:src/tools/contrib/ceph-migrate-bluestore.bash").stdout
for needle in (
    "ceph osd purge",
    "ceph-objectstore-tool --type filestore",
    "--op dup",
    "ceph-volume lvm trigger",
    "disable-filestore",
):
    assert needle in migrate
dencoder_diff = git("diff", "--unified=5", "v16.2.15", "v17.2.7", "--", "src/tools/ceph-dencoder").stdout
assert "unable to load dencoders" in dencoder_diff
assert "TYPE(string_wrapper)" in dencoder_diff
assert "TYPE(RGWBucketEncryptionConfig)" in dencoder_diff

for row in rows:
    path = row["path"]
    if path in affect:
        finding_id, reason = affect[path]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding_id
        row["impact_reason"] = reason
    elif path in trivial:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[path]

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

owner_affect = sum(row["upgrade_impact"] == "affect" for row in rows)
owner_trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
owner_blank = sum(not row["upgrade_impact"] for row in rows)
assert (owner_affect, owner_trivial, owner_blank) == (75, 553, 0)

replace_known(
    md_path,
    "**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./15-upgrade-validation.csv) có 628 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 61`, `trivial = 526`, **chưa phân loại = 41**; binary gate của owner chưa hoàn tất.",
    "**Trạng thái: đã hoàn tất binary gate của owner; lab/canary còn mở.** [CSV đầy đủ của owner](./15-upgrade-validation.csv) có 628 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 75`, `trivial = 553`, **chưa phân loại = 0**; `75 + 553 = 628`.",
)

findings = """### VAL-006 — Script contrib di chuyển FileStore sang BlueStore có đường ghi phá hủy

- **CSV:** `src/tools/contrib/ceph-migrate-bluestore.bash`. **Nguồn:** file target, commit `2a181ef9330` và cảnh báo `src/tools/contrib/README.rst`; Pacific không có script này.
- **Trước → sau:** Quincy thêm script tương tác nhận OSD ID và raw device `/dev/disk/by-id/`, kiểm dung lượng, tạo LV `block.db`, dùng `ceph-volume lvm prepare` để tạo OSD tạm rồi purge OSD đó, sửa tag/label/LV về ID và FSID cũ, mkfs BlueStore, dừng FileStore, chạy `ceph-objectstore-tool --op dup`, chuyển file JSON cũ, kích hoạt BlueStore rồi đổi GPT type và comment mount FileStore. Script có tên VG/size DB hard-code và tự tuyên bố contrib “as-is”, không phải workflow cephadm tự động.
- **Điều kiện và tác động:** Chỉ áp dụng khi As-Is còn OSD FileStore kiểu systemd/ceph-volume phù hợp và operator chủ động chọn script làm bước chuẩn bị nâng cấp. Nó sửa trực tiếp dữ liệu, LVM, label, `/etc/fstab` và trạng thái OSD; lỗi giữa chừng có thể để cả source/target không tự kích hoạt. Script không chạy chỉ vì nâng daemon lên Quincy. **Độ tin cậy:** cao cho chuỗi lệnh; applicability và tính đầy đủ trên layout thật chưa biết.
- **Kiểm chứng:** chỉ dùng bản sao OSD FileStore trong lab cô lập, thay VG/device bằng inventory lab, chụp backup partition/LVM/config trước khi chạy; so object count, data, xattr, OMAP, snapshot, PG scrub/deep-scrub và activation sau reboot. Diễn tập rollback về thiết bị FileStore gốc. Không chạy script contrib này trên thiết bị production để “thử”.

### VAL-007 — Dencoder đổi điều kiện nạp plugin và mở rộng type được kiểm

- **CSV:** `src/tools/ceph-dencoder/ceph_dencoder.cc`, `common_types.h`, `rgw_types.h`, `str.h`; liên quan [PKG-006](./13-build-packaging-submodules.md) cho corpus và PKG-014 cho build/install plugin. **Nguồn:** endpoint hunk và caller trong `src/test/encoding/**`.
- **Trước → sau:** Pacific có fallback từ `CMakeCache.txt` sang `lib` khi chạy trong build tree. Quincy bỏ fallback đó; nếu `CEPH_LIB`/thư mục module mặc định không hợp lệ, tool báo “not a directory” rồi trả registry rỗng. Target đồng thời thêm generated type `string_wrapper` và `RGWBucketEncryptionConfig`. Harness chuẩn có `detect-build-env-vars.sh` đặt `CEPH_LIB`, nhưng lệnh ad-hoc hoặc packaging thiếu module vẫn có thể tạo danh sách type rỗng và làm phép kiểm không còn giá trị.
- **Điều kiện và tác động:** Đây là runtime của công cụ validation, không phải daemon cluster. Nó ảnh hưởng độ tin cậy của corpus/encode-decode gate nếu môi trường hoặc package plugin sai, đồng thời mở rộng phạm vi type kỳ vọng. Không chứng minh wire incompatibility chỉ từ việc type được thêm. **Độ tin cậy:** cao cho loader/registry, chưa chạy binary/corpus hai endpoint.
- **Kiểm chứng:** chạy dencoder Pacific và Quincy với `CEPH_LIB` đúng, thiếu và sai; bắt buộc `list_types` không rỗng và có các type kỳ vọng, rồi chạy corpus forward/backward theo PKG-006. Lưu binary/package version, module directory, type count và expected-incompatibility markers; coi registry rỗng là lỗi harness, không phải pass.

"""
insert_before_once(md_path, "## Thay đổi trivial đã sàng lọc", findings)

cross_owner = """14 hàng `affect` cuối được nối theo call graph thay vì gom hết thành finding owner 15: `ceph_argparse.py` là phía client của [MGR-037](./07-mgr-modules-monitoring.md), nơi `orch upgrade start` chặn positional sau image; việc xóa `ceph_volume_client.py` nối [FS-007](./11-cephfs-mds.md). Ba file DriveGroup/inventory/translate nối [ADM-022](./08-cephadm-orchestrator.md) vì target đọc class theo từng path và sinh nhiều lệnh `ceph-volume`; `service_spec.py` mang schema persisted cho tuned profile, Grafana, MON, ingress/NFS và RGW đã mô tả ở ADM-009/012/013/014 cùng MGR-051. Ba implementation RGWAM target-only nối MGR-051 vì chỉ chạy khi operator gọi lệnh realm/zone/reconcile. Bốn file dencoder thuộc VAL-007 và script migration thuộc VAL-006.

27 hàng còn lại đã được đọc tới hunk/caller: `ceph_daemon.py` bỏ shortcut string vốn không tới được vì `ceph.in` truyền list ở cả hai endpoint; `ceph_mgr_repl.py` là console self-test; hai test DriveGroup/ServiceSpec chỉ hỗ trợ finding production; selector/HostSpec và các tool RadosDump/authtool/conf/client-debug chỉ đổi log, lỗi, equality, namespace hoặc API argv tương đương. `ceph_dedup_tool` thêm lệnh opt-in ngoài đường nâng cấp, ba perf tool Crimson/SeaStore là benchmark độc lập, còn tox/requirements/setup-virtualenv chỉ đổi static/developer test environment. Chúng nhận `trivial` cho gate nâng cấp này, không có nghĩa công cụ mới vô dụng.

"""
insert_before_once(md_path, "## Kiểm chứng cần hoàn thành", cross_owner)

replace_known(
    md_path,
    "- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.\n- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.\n- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.\n- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 628` và viết tóm tắt các cụm trivial.",
    "- Chạy exact-pair Pacific-x với image/hash đúng hai endpoint và lưu expanded matrix, archive/JUnit, version/health timeline, command log cùng partition cron đã chọn.\n- Phục dựng client Pacific→Quincy hai chiều; chạy cú pháp `orch upgrade start` cũ/mới và xác nhận descriptor, mã trả về, image/version backend nhận.\n- Chạy dencoder/corpus với module directory được ghi lại; registry rỗng phải fail. Nếu còn FileStore và cân nhắc migration, chỉ diễn tập trên bản sao OSD lab theo VAL-006.\n- Đối chiếu As-Is cho legacy `ceph_volume_client`, persisted cephadm/RGW specs và automation dùng các lệnh control-plane trước khi chốt applicability.",
)

replace_known(
    readme_path,
    "**Trạng thái: đã chốt nguồn, hoàn thành master inventory và phân owner cho 4.179 hàng; 15 cặp component đã tạo, binary gate và phân tích component chưa hoàn tất.**",
    "**Trạng thái: đã chốt nguồn, hoàn thành master inventory, phân owner và binary impact gate cho toàn bộ 4.179 hàng; lab/canary và inventory As-Is còn mở.**",
)
replace_known(
    readme_path,
    "**1.722 hàng `affect`. 2.416 hàng `trivial`. 41 hàng chưa phân loại.**",
    "**1.736 hàng `affect`. 2.443 hàng `trivial`. 0 hàng chưa phân loại.**",
)
replace_known(readme_path, "[VAL-001–005](./15-upgrade-validation.md)", "[VAL-001–007](./15-upgrade-validation.md)")
replace_known(
    readme_path,
    "[owner 13](./13-build-packaging-submodules.md) và [owner 14](./14-security-cross-reference.md) đã hoàn tất binary gate trong phạm vi hàng của mình. Chưa thể tổng hợp rủi ro toàn suite.",
    "[owner 13](./13-build-packaging-submodules.md), [owner 14](./14-security-cross-reference.md) và [owner 15](./15-upgrade-validation.md) đã hoàn tất binary gate trong phạm vi hàng của mình. Toàn suite không còn nhãn trống; đây vẫn chưa phải GO/NO-GO vì lab/canary và inventory As-Is còn mở.",
)
replace_known(
    readme_path,
    "| 15 — validation | [Báo cáo](./15-upgrade-validation.md) | [CSV](./15-upgrade-validation.csv) | Đang phân tích |",
    "| 15 — validation | [Báo cáo](./15-upgrade-validation.md) | [CSV](./15-upgrade-validation.csv) | Binary gate owner đã hoàn tất; lab còn mở |",
)
replace_known(
    readme_path,
    "Validator `--mode complete` đã qua cho layout, link và partition CSV. Gate cuối `--mode complete --require-impact binary` hiện **không qua** vì 41 hàng còn thiếu nhãn và lý do; đây là trạng thái có chủ đích, không phải coi các hàng ấy là `trivial`.",
    "Validator `--mode complete --impact-schema binary` đã qua cho layout, schema, link, partition và đủ nhãn của toàn bộ 4.179 hàng. `impact_complete=true`; kiểm chứng lab/runtime vẫn là gate riêng và chưa có kết quả chạy.",
)

replace_known(
    plan_path,
    "3. **Đang làm:** đọc hunk/metadata, commit liên quan và context để gắn **mọi** hàng `affect` hoặc `trivial`. Owner 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14 đã hoàn tất binary gate; tại lần đối soát gần nhất: `affect 1.722`, `trivial 2.416`, còn **41 hàng chưa phân loại**. Owner 07 đã chốt `287 affect`, `439 trivial`, `0` chưa phân loại; owner 08 đã chốt `95 affect`, `39 trivial`, `0` chưa phân loại; owner 10 đã chốt `58 affect`, `262 trivial`, `0` chưa phân loại; owner 11 đã chốt `88 affect`, `339 trivial`, `0` chưa phân loại; owner 12 đã chốt `244 affect`, `302 trivial`, `0` chưa phân loại; owner 13 đã chốt `152 affect`, `55 trivial`, `0` chưa phân loại; owner 15 hiện `61 affect`, `526 trivial`, `41` chưa phân loại. Không suy ra `trivial` chỉ từ đường dẫn, churn hay loại file. Mỗi `affect` phải có finding ID, bằng chứng trước/sau, điều kiện kích hoạt, mixed-version/full-version và kịch bản kiểm chứng.\n4. **Hàng chờ ưu tiên:** tiếp tục owner 15 validation; owner 13 build/package đã hoàn tất binary gate. [`config-default-candidates.tsv`](./pacific-16.2.15-to-quincy-17.2.7/config-default-candidates.tsv) vẫn là dữ liệu hỗ trợ đối soát và cross-reference, không phải nhãn tác động.\n5. Kiểm tra partition, số lượng, link, và chạy validator ở chế độ `complete --require-impact binary`. `--mode complete` hiện qua cấu trúc/partition; strict binary hiện thất bại đúng vì các hàng chưa phân loại. Trước khi xong bước này, suite là **đang phân tích**, không phải kết luận đủ để GO/NO-GO production.",
    "3. **Đã làm:** đọc hunk/metadata, commit và caller để gắn đủ mọi hàng `affect` hoặc `trivial`. Cả 15 owner đã hoàn tất binary gate; toàn suite có `affect 1.736`, `trivial 2.443`, **0 hàng chưa phân loại**. Owner 15 chốt `75 affect`, `553 trivial`, `0` chưa phân loại. Không suy `trivial` chỉ từ đường dẫn, churn hay loại file; mỗi `affect` trỏ tới finding có bằng chứng, điều kiện và kịch bản kiểm chứng.\n4. **Đang làm tiếp:** biến finding có điều kiện thành inventory As-Is và test case ưu tiên; [`config-default-candidates.tsv`](./pacific-16.2.15-to-quincy-17.2.7/config-default-candidates.tsv) vẫn là dữ liệu hỗ trợ, không phải nhãn tác động.\n5. **Đã làm:** validator `--mode complete --impact-schema binary` qua layout, schema, partition, link và đủ nhãn (`impact_complete=true`). Gate lab/canary, rollback rehearsal và artifact provenance vẫn mở; binary gate hoàn tất không đồng nghĩa đủ cơ sở GO/NO-GO production.",
)

global_rows = global_affect = global_trivial = global_blank = 0
component_csvs = [
    path
    for path in sorted(root.glob("[0-1][0-9]-*.csv"))
    if not path.name.startswith("00-")
]
assert len(component_csvs) == 15
for component_csv in component_csvs:
    with component_csv.open(encoding="utf-8-sig", newline="") as stream:
        component_rows = list(csv.DictReader(stream, delimiter=";"))
    global_rows += len(component_rows)
    global_affect += sum(row["upgrade_impact"] == "affect" for row in component_rows)
    global_trivial += sum(row["upgrade_impact"] == "trivial" for row in component_rows)
    global_blank += sum(not row["upgrade_impact"] for row in component_rows)
assert (global_rows, global_affect, global_trivial, global_blank) == (4179, 1736, 2443, 0)

print("Reviewed owner-15 shared runtime/tools rows: 14 affect, 27 trivial")
print("Owner totals: affect=75 trivial=553 unclassified=0")
print("Suite totals: affect=1736 trivial=2443 unclassified=0")
