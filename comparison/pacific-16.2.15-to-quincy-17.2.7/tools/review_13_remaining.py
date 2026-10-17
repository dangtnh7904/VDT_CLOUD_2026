"""Close owner 13 by reviewing the remaining source and helper-script rows."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "13-build-packaging-submodules.csv"
md_path = root / "13-build-packaging-submodules.md"
readme_path = root / "README.md"
plan_path = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, path: str) -> str:
    return git("show", f"{tag}:{path}").stdout


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
    "src/compressor/QatAccel.cc": (
        "PKG-016",
        "PKG-016: QAT backend drops Snappy/LZ4 algorithms and adopts the session-aware QATzip API; only zlib remains hardware-accelerated.",
    ),
    "src/compressor/QatAccel.h": (
        "PKG-016",
        "PKG-016: QAT session changes to owned incomplete-type storage with an explicit teardown deleter, part of the QATzip ABI/lifecycle transition.",
    ),
    "src/dokan/ceph_dokan.h": (
        "PKG-018",
        "PKG-018: Windows Dokan build uses bcrypt's canonical NTSTATUS definition to avoid the Boost 1.79/MinGW typedef conflict.",
    ),
    "src/libcephsqlite.cc": (
        "PKG-017",
        "PKG-017: libcephsqlite registers process-exit cleanup and shuts down its RADOS handle before static destruction, changing failure-exit lifecycle.",
    ),
    "src/nasm-wrapper": (
        "PKG-007",
        "PKG-007: NASM wrapper now swallows CMake/Ninja's broken pre-3.18 -MD forwarding, changing whether affected source builds complete.",
    ),
    "src/objclass/objclass.h": (
        "OSD-019",
        "OSD-019: public object-class header exposes the new multi-object gather and gathered-result APIs used by the OSD implementation.",
    ),
    "src/script/cpatch": (
        "PKG-008",
        "PKG-008: local patch-container builder accepts Ninja output and Python 3 ABI variants, changing which validation artifact it can assemble.",
    ),
    "src/script/gen-corpus.sh": (
        "PKG-006",
        "PKG-006: corpus generator pins build-tree PATH and CEPH_CONF, changing the environment used to produce compatibility fixtures.",
    ),
    "src/script/run-cbt.sh": (
        "PKG-008",
        "PKG-008: CBT harness switches Crimson from memstore to cyanstore and manages perf-event access, changing benchmark topology and signals.",
    ),
    "src/script/run-make.sh": (
        "PKG-007",
        "PKG-007: source-build helper installs clang, selects system zstd on Focal and invokes generator-neutral cmake --build, changing build provenance.",
    ),
    "src/script/set_up_stretch_mode.sh": (
        "MON-006",
        "MON-006: stretch-mode setup stops emitting deprecated CRUSH rule min_size/max_size fields that Quincy parses only as ignored legacy input.",
    ),
}

trivial = {
    "src/SimpleRADOSStriper.cc": "PKG-MECH-02: string-view literal spelling becomes explicit std::string_view/string comparison; blocklist fallback and command payload are unchanged.",
    "src/SimpleRADOSStriper.h": "PKG-MECH-02: chrono literals become brace-initialized millisecond counts with the same 2000/30000 values.",
    "src/ceph_syn.cc": "PKG-MECH-02: argv_to_vec return-value API and std namespace update preserve the synthetic-client arguments and startup path.",
    "src/compressor/lz4/LZ4Compressor.h": "PKG-MECH-02: Tub-to-optional and structured-binding rewrite preserve LZ4 framing, lengths and software decode; QAT algorithm removal is in PKG-016.",
    "src/compressor/zlib/ZlibCompressor.cc": "PKG-MECH-02: buffer-list decompression delegates to the iterator overload, which still performs the same QAT check before software inflate.",
    "src/doc/caching.txt": "PKG-DOC-02: fixes a spelling error in caching documentation only.",
    "src/dokan/ceph_dokan.cc": "PKG-MECH-02: integer cast and argv_to_vec API update preserve Dokan status dispatch and command parsing.",
    "src/dokan/dbg.cc": "PKG-MECH-02: namespace declaration and explicit bool cast preserve Dokan diagnostic output.",
    "src/java/native/libcephfs_jni.cc": "PKG-MECH-02: adds a std namespace declaration without changing JNI flags or calls.",
    "src/krbd.cc": "PKG-MECH-02: qualifies standard-library stream names while preserving krbd map/unmap command construction and errors.",
    "src/script/backport-create-issue": "PKG-RELENG-01: release-engineering helper changes issue/backport workflow only; it is not shipped or run in a cluster upgrade.",
    "src/script/backport-resolve-issue": "PKG-RELENG-01: release-engineering helper changes issue/backport workflow only; it is not shipped or run in a cluster upgrade.",
    "src/script/build-integration-branch": "PKG-RELENG-01: release-engineering helper changes branch assembly only; it is not shipped or run in a cluster upgrade.",
    "src/script/ceph-backport.sh": "PKG-RELENG-01: release-engineering helper changes backport automation only; it is not shipped or run in a cluster upgrade.",
    "src/script/ceph-debug-docker.sh": "PKG-RELENG-01: developer debug-container helper changes local diagnostics only; it is not a deployed daemon/client or upgrade gate.",
    "src/script/ceph-release-notes": "PKG-RELENG-01: release-note generator changes formatting and PR-message options only; it is not a deployed payload or upgrade gate.",
}

paths = set(affect) | set(trivial)
assert len(affect) == 11
assert len(trivial) == 16
assert len(paths) == 27
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# Endpoint guards for the behavior claims and the deliberately mechanical rows.
qat_base = show("v16.2.15", "src/compressor/QatAccel.cc")
qat_target = show("v17.2.7", "src/compressor/QatAccel.cc")
assert 'alg == "snappy"' in qat_base and 'alg == "lz4"' in qat_base
assert 'alg == "snappy"' not in qat_target and 'alg == "lz4"' not in qat_target
assert 'alg == "zlib"' in qat_target
assert "qzMaxCompressedLength(len, session.get())" in qat_target
qat_header = show("v17.2.7", "src/compressor/QatAccel.h")
assert "std::unique_ptr<struct QzSession_S, QzSessionDeleter>" in qat_header

lz4_base = show("v16.2.15", "src/compressor/lz4/LZ4Compressor.h")
lz4_target = show("v17.2.7", "src/compressor/lz4/LZ4Compressor.h")
assert 'qat_accel.init("lz4")' in lz4_base and 'qat_accel.init("lz4")' in lz4_target
assert "Tub<ceph::buffer::ptr>" in lz4_base and "std::optional<ceph::buffer::ptr>" in lz4_target
zlib_target = show("v17.2.7", "src/compressor/zlib/ZlibCompressor.cc")
assert "return decompress(i, in.length(), out, compressor_message);" in zlib_target
assert zlib_target.count("if (qat_enabled)") >= 2

dokan_target = show("v17.2.7", "src/dokan/ceph_dokan.h")
assert "#include <bcrypt.h>" in dokan_target and "typedef DWORD NTSTATUS" not in dokan_target
sqlite_target = show("v17.2.7", "src/libcephsqlite.cc")
assert "cluster.shutdown();" in sqlite_target
assert "std::atexit(cephsqlite_atexit)" in sqlite_target
assert 'sqlite3_vfs_find("ceph")' in sqlite_target
assert "case -MD" not in show("v16.2.15", "src/nasm-wrapper")
assert "-MD )" in show("v17.2.7", "src/nasm-wrapper")
objclass_target = show("v17.2.7", "src/objclass/objclass.h")
assert "cls_cxx_gather" in objclass_target and "cls_cxx_get_gathered_data" in objclass_target
assert "build.ninja" in show("v17.2.7", "src/script/cpatch")
corpus_target = show("v17.2.7", "src/script/gen-corpus.sh")
assert 'export PATH="$PWD/bin:$PATH"' in corpus_target and 'export CEPH_CONF="$PWD/ceph.conf"' in corpus_target
cbt_target = show("v17.2.7", "src/script/run-cbt.sh")
assert "--cyanstore" in cbt_target and "kernel.perf_event_paranoid" in cbt_target
run_make_target = show("v17.2.7", "src/script/run-make.sh")
assert "cmake --build ." in run_make_target and "WITH_SYSTEM_ZSTD=ON" in run_make_target
stretch_base = show("v16.2.15", "src/script/set_up_stretch_mode.sh")
stretch_target = show("v17.2.7", "src/script/set_up_stretch_mode.sh")
assert stretch_base.count("min_size 1") == 3 and "min_size" not in stretch_target

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)
for path, (finding_id, reason) in affect.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == finding_id
        assert row["impact_reason"] == reason
    row["upgrade_impact"] = "affect"
    row["finding_id"] = finding_id
    row["impact_reason"] = reason
for path, reason in trivial.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial"
        assert not row["finding_id"]
        assert row["impact_reason"] == reason
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
assert affect_count + trivial_count + blank_count == 207
assert (affect_count, trivial_count, blank_count) == (152, 55, 0)

replace_known(
    md_path,
    "**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./13-build-packaging-submodules.csv) có 207 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 141`, `trivial = 39`, **chưa phân loại = 27**; binary gate của owner chưa hoàn tất.",
    "**Trạng thái: đã hoàn tất binary gate; kiểm chứng artifact/lab còn mở.** [CSV đầy đủ của owner](./13-build-packaging-submodules.csv) có 207 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Đã đối soát `affect = 152`, `trivial = 55`, **chưa phân loại = 0**.",
)
replace_known(
    md_path,
    "Owner 13 giữ hunk build trong CSV riêng để partition không trùng. Các hunk CMake, dependency, CI và systemd còn lại vẫn cần review.",
    "Owner 13 giữ hunk build trong CSV riêng để partition không trùng. Toàn bộ hunk build, package, dependency, CI, systemd và helper source còn lại đã được đọc và gắn binary impact.",
)
replace_known(md_path, "- **CSV:** 21. **Nguồn:** gitlink", "- **CSV:** 21, 3645. **Nguồn:** gitlink và `src/script/gen-corpus.sh`; gitlink")
replace_known(md_path, "- **CSV:** 81–82, 417–418, 4179.", "- **CSV:** 81–82, 417–418, 2427, 3647, 4179.")
replace_known(md_path, "- **CSV:** 1465, 1981, 2378, 3650, 4177.", "- **CSV:** 1465, 1981, 2378, 3644, 3646, 3650, 4177.")

cross_refs = """`src/objclass/objclass.h` được gắn [OSD-019](./01-osd-pg-recovery.md) vì public header xuất API gather tương ứng implementation OSD. `src/script/set_up_stretch_mode.sh` được gắn [MON-006](./04-mon-osdmap-crush.md): script bỏ `min_size`/`max_size` đã deprecated để tạo rule theo contract Quincy.

"""
insert_before_once(md_path, "### PKG-011", cross_refs)

findings = """### PKG-016 — QAT chỉ còn tăng tốc zlib và đổi vòng đời session

- **CSV:** 1712–1713. **Nguồn:** `src/compressor/QatAccel.{cc,h}`; commits `414c028284c` (thay Snappy/LZ4 bằng zlib) và `6609aadfc9c` (tương thích QATzip API).
- **Trước → sau:** Pacific ánh xạ QATzip cho `snappy`, `zlib` và `lz4`, giữ `QzSession_T` trực tiếp. Quincy chỉ chấp nhận `zlib`; constructor LZ4 vẫn gọi `init("lz4")` nhưng nhận `false` rồi dùng phần mềm. Session chuyển sang `unique_ptr` với deleter teardown/close, và `qzMaxCompressedLength`/compress/decompress đều nhận session theo API mới. Hai hunk LZ4/zlib còn lại chỉ refactor tương đương và được gắn `trivial`.
- **Điều kiện và tác động:** Chỉ artifact bật `HAVE_QATZIP`, cấu hình `qat_compressor_enabled` và host có/cho phép QAT. Workload LZ4/Snappy mất hardware offload sau nâng nhưng giữ codec phần mềm, nên rủi ro chính là CPU, latency và capacity asymmetry giữa daemon Pacific/Quincy; không có bằng chứng đổi on-wire format. Zlib tiếp tục offload nhưng phụ thuộc QATzip ABI/session mới. **Độ tin cậy:** cao cho control flow, chưa đo hardware. **Kiểm chứng:** build đúng QATzip target, chạy vector zlib/LZ4/Snappy qua software và hardware path, kiểm byte round-trip, fallback, restart/leak và throughput/CPU trên mixed/full Quincy; lưu SBOM và log QAT init.

### PKG-017 — `libcephsqlite` đóng RADOS trước static destruction

- **CSV:** 2064. **Nguồn:** `src/libcephsqlite.cc`; commits `664c2590010` và `7985b282cac`.
- **Trước → sau:** Pacific đặt `sqlite3_vfs` trong app-data và không gọi `cluster.shutdown()` khi process thoát. Quincy cấp phát VFS riêng, kiểm lỗi đăng ký, đăng ký `atexit`, xóa app-data và đóng RADOS trước khi static-duration objects bị hủy. Commit giải thích đường lỗi của `/bin/sqlite3` có thể gọi `exit(3)` khi thread librados còn sống.
- **Điều kiện và tác động:** Chỉ process nạp Ceph SQLite VFS, nổi bật CLI SQLite và lỗi I/O/blocklist khi thoát; đường MGR dùng VFS cũng cần smoke-test restart. Thay đổi nhằm tránh exception/segfault khi shutdown, không cho thấy schema hay object layout đổi. Mixed-version theo process, rollback không cần chuyển format nhưng phải kiểm không để handle/thread treo. **Độ tin cậy:** cao cho lifecycle, chưa tái hiện crash. **Kiểm chứng:** mở database Ceph VFS, chạy read/write rồi normal exit và fault/blocklist exit dưới Pacific/Quincy; kiểm exit code, crash/core, thread/leak và MGR failover/restart với store clone.

### PKG-018 — Build CephFS Dokan dùng định nghĩa `NTSTATUS` chuẩn của Windows

- **CSV:** 1985. **Nguồn:** `src/dokan/ceph_dokan.h`; commit `8589bc0d408` ghi rõ xung đột typedef sau khi chuyển Boost 1.79.
- **Trước → sau:** Pacific tự khai báo `NTSTATUS` là `DWORD`; Quincy bỏ typedef đó và include `bcrypt.h`, nơi MinGW/Windows SDK khai báo kiểu chuẩn. Việc này loại lỗi compile do Boost.Asio kéo `bcrypt.h` trước header Dokan.
- **Điều kiện và tác động:** Chỉ pipeline build client CephFS Dokan trên Windows/MinGW với dependency tạo xung đột; package Linux và host chỉ cài binary có sẵn không bị ảnh hưởng. Nếu custom pipeline giữ header/dependency Pacific, artifact Quincy có thể không build; thay đổi không tự đổi hành vi mount. **Độ tin cậy:** cao cho lỗi compiler/commit, chưa dựng Windows artifact. **Kiểm chứng:** clean-build Dokan với Boost/MinGW/Windows SDK đúng ma trận triển khai, kiểm symbol/header order, chạy map/unmap và smoke I/O, rồi lưu toolchain/SBOM cùng artifact.

"""
insert_before_once(md_path, "## Thay đổi trivial", findings)

replace_known(
    md_path,
    "39 hàng đã được đọc theo endpoint. Ngoài 19 hàng `PKG-DOC-01` và bảy hàng `PKG-MAN-01`, 13 hàng `PKG-CI-01` chỉ điều khiển GitHub PR/label, cache developer, build tài liệu/mypy, changelog/man text hoặc danh sách mirror source. Chúng không được cài làm payload daemon/client. Những thay đổi package có đường delivery/runtime thực được giữ `affect` ở PKG-001–003, FS-007 hoặc cross-reference liên quan.",
    "55 hàng đã được đọc theo endpoint. Ngoài 19 hàng `PKG-DOC-01`, bảy hàng `PKG-MAN-01` và 13 hàng `PKG-CI-01`, lô cuối có 10 hunk cơ học/tài liệu (`PKG-MECH-02`/`PKG-DOC-02`) và sáu helper release-engineering (`PKG-RELENG-01`). Nhóm cơ học giữ nguyên tham số, framing, nhánh lỗi hoặc chỉ đổi namespace/API tương đương; riêng LZ4/zlib vẫn giữ software codec và QAT check ở overload đích. Helper backport, release note và debug container không được cài làm payload daemon/client hay dùng làm upgrade gate. Các thay đổi có đường build, delivery, runtime hoặc validation thực được giữ `affect` và map tới finding tương ứng.",
)
replace_known(
    md_path,
    "- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.\n- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.\n- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.\n- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 207` và viết tóm tắt các cụm trivial.",
    "- Dựng ma trận artifact official/custom theo architecture, compiler, CMake option và system-vs-bundled dependency; lưu CMake cache, SBOM, link/install manifest và hash payload.\n- Mô phỏng cài/nâng/rollback package trong image sạch, kiểm split `ceph-volume`, MGR module, unit systemd/SysV và source tarball/offline submodule cache.\n- Chạy CTest/corpus/harness với topology cố định; bổ sung smoke QAT, `libcephsqlite`, Dokan Windows, CRUSH stretch và object-class gather theo finding tương ứng.\n- Đã đối soát binary gate: `152 affect + 55 trivial = 207`; mọi hàng `affect` đều trỏ tới finding có trước/sau, điều kiện, confidence và kịch bản kiểm chứng.",
)
replace_known(
    md_path,
    "Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.",
    "Chưa có As-Is cluster, artifact triển khai hoặc lab/canary cho cặp endpoint. Binary gate hoàn tất không thay thế build/install/runtime validation; chưa đưa GO/NO-GO production.",
)

replace_known(
    readme_path,
    "1.650 hàng `affect`. 1.874 hàng `trivial`. 655 hàng chưa phân loại.",
    "1.661 hàng `affect`. 1.890 hàng `trivial`. 628 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 655 hàng còn thiếu nhãn và lý do", "vì 628 hàng còn thiếu nhãn và lý do")
replace_known(readme_path, "[PKG-001–015]", "[PKG-001–018]")
replace_known(
    readme_path,
    "CMake dependency/target graph, validation harness và activation",
    "CMake dependency/target graph, validation harness, activation, QAT, SQLite cleanup và Dokan build",
)
replace_known(
    readme_path,
    "[owner 12](./12-rgw.md) và [owner 14](./14-security-cross-reference.md) đã hoàn tất binary gate",
    "[owner 12](./12-rgw.md), [owner 13](./13-build-packaging-submodules.md) và [owner 14](./14-security-cross-reference.md) đã hoàn tất binary gate",
)
replace_known(
    readme_path,
    "| 13 — build/package | [Báo cáo](./13-build-packaging-submodules.md) | [CSV](./13-build-packaging-submodules.csv) | Đang phân tích |",
    "| 13 — build/package | [Báo cáo](./13-build-packaging-submodules.md) | [CSV](./13-build-packaging-submodules.csv) | Binary gate owner đã hoàn tất; artifact/lab còn mở |",
)

replace_known(
    plan_path,
    "Owner 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 14 đã hoàn tất binary gate; tại lần đối soát gần nhất: `affect 1.650`, `trivial 1.874`, còn **655 hàng chưa phân loại**.",
    "Owner 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14 đã hoàn tất binary gate; tại lần đối soát gần nhất: `affect 1.661`, `trivial 1.890`, còn **628 hàng chưa phân loại**.",
)
replace_known(
    plan_path,
    "owner 13 hiện `141 affect`, `39 trivial`, `27` chưa phân loại.",
    "owner 13 đã chốt `152 affect`, `55 trivial`, `0` chưa phân loại.",
)
replace_known(
    plan_path,
    "4. **Hàng chờ ưu tiên:** tiếp tục owner 13 build/package và owner 15 validation.",
    "4. **Hàng chờ ưu tiên:** tiếp tục owner 15 validation; owner 13 build/package đã hoàn tất binary gate.",
)

# Recount the complete suite so summary updates cannot drift from component CSVs.
global_affect = 0
global_trivial = 0
global_blank = 0
global_rows = 0
component_csvs = [
    path for path in sorted(root.glob("[0-1][0-9]-*.csv"))
    if not path.name.startswith("00-")
]
assert len(component_csvs) == 15, [path.name for path in component_csvs]
for component_csv in component_csvs:
    with component_csv.open(encoding="utf-8-sig", newline="") as stream:
        component_rows = list(csv.DictReader(stream, delimiter=";"))
    global_rows += len(component_rows)
    global_affect += sum(row["upgrade_impact"] == "affect" for row in component_rows)
    global_trivial += sum(row["upgrade_impact"] == "trivial" for row in component_rows)
    global_blank += sum(not row["upgrade_impact"] for row in component_rows)
assert (global_rows, global_affect, global_trivial, global_blank) == (4179, 1661, 1890, 628)

print("Classified owner-13 remainder: 11 affect, 16 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
print(f"Suite totals: affect={global_affect} trivial={global_trivial} unclassified={global_blank}")
