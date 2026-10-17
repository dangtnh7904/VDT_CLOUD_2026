"""Classify all remaining owner-13 cmake/modules rows."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "13-build-packaging-submodules.csv"
md_path = root / "13-build-packaging-submodules.md"
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


resolver_paths = {
    "cmake/modules/BuildBoost.cmake",
    "cmake/modules/BuildFIO.cmake",
    "cmake/modules/CephChecks.cmake",
    "cmake/modules/CheckCxxAtomic.cmake",
    "cmake/modules/Distutils.cmake",
    "cmake/modules/ExternalProjectHelper.cmake",
    "cmake/modules/FindBoost.cmake",
    "cmake/modules/FindNUMA.cmake",
    "cmake/modules/FindOpenLDAP.cmake",
    "cmake/modules/FindOpenLdap.cmake",
    "cmake/modules/FindPython/Support.cmake",
    "cmake/modules/FindStdFilesystem.cmake",
    "cmake/modules/FindStdFilesystem_test.cc",
    "cmake/modules/SIMDExt.cmake",
    "cmake/modules/boost-python-use-public-api-for-filename.patch",
}

feature_by_path = {
    "cmake/modules/BuildArrow.cmake": "bundled Arrow/Parquet for RGW S3 Select",
    "cmake/modules/BuildDPDK.cmake": "bundled DPDK for the DPDK messenger",
    "cmake/modules/BuildJaeger.cmake": "old bundled Jaeger tracing stack",
    "cmake/modules/BuildOpenTracing.cmake": "old bundled OpenTracing stack",
    "cmake/modules/BuildOpentelemetry.cmake": "new OpenTelemetry Jaeger exporter stack",
    "cmake/modules/BuildQatDrv.cmake": "old in-tree QAT driver build",
    "cmake/modules/BuildRocksDB.cmake": "bundled RocksDB storage engine",
    "cmake/modules/BuildSPDK.cmake": "bundled SPDK storage path",
    "cmake/modules/BuildUtf8proc.cmake": "bundled utf8proc used by Arrow",
    "cmake/modules/BuildZstd.cmake": "bundled zstd compressor",
    "cmake/modules/Buildthrift.cmake": "old bundled Thrift tracing dependency",
    "cmake/modules/Builduring.cmake": "bundled liburing IO path",
    "cmake/modules/Buildyaml-cpp.cmake": "old bundled yaml-cpp tracing dependency",
    "cmake/modules/FindArrow.cmake": "system Arrow for RGW S3 Select",
    "cmake/modules/FindLinuxZNS.cmake": "Linux zoned-block support",
    "cmake/modules/FindParquet.cmake": "system Parquet for RGW S3 Select",
    "cmake/modules/FindQatDrv.cmake": "system QAT driver and required version",
    "cmake/modules/FindZstd.cmake": "system zstd and version metadata",
    "cmake/modules/Finddpdk.cmake": "system/static DPDK link set",
    "cmake/modules/Findleveldb.cmake": "removed LevelDB backend",
    "cmake/modules/Findpmem.cmake": "PMDK components used by RBD RWL",
    "cmake/modules/Findqatzip.cmake": "QATzip compressor dependency",
    "cmake/modules/Findthrift.cmake": "system Thrift 0.13+ tracing dependency",
    "cmake/modules/Findutf8proc.cmake": "system utf8proc used by Arrow",
    "cmake/modules/IncludeJaeger.cmake": "old Jaeger include/build glue",
}

validation_paths = {
    "cmake/modules/AddCephTest.cmake",
    "cmake/modules/FindSanitizers.cmake",
    "cmake/modules/LimitJobs.cmake",
}

assert len(resolver_paths) == 15
assert len(feature_by_path) == 25
assert len(validation_paths) == 3
paths = resolver_paths | set(feature_by_path) | validation_paths
assert len(paths) == 43
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# Core resolver/toolchain evidence.
assert "1.75" in show("v17.2.7", "cmake/modules/FindBoost.cmake")
assert "VERSION_LESS 8.1" in show("v17.2.7", "cmake/modules/CephChecks.cmake")
assert "Python3_EXECUTABLE" in show("v17.2.7", "cmake/modules/Distutils.cmake")
assert '"c++experimental"' in show("v16.2.15", "cmake/modules/FindStdFilesystem.cmake")
assert '"c++experimental"' not in show("v17.2.7", "cmake/modules/FindStdFilesystem.cmake")
assert "<experimental/filesystem>" in show("v16.2.15", "cmake/modules/FindStdFilesystem_test.cc")
assert "<experimental/filesystem>" not in show("v17.2.7", "cmake/modules/FindStdFilesystem_test.cc")
assert exists("v16.2.15", "cmake/modules/boost-python-use-public-api-for-filename.patch")
assert not exists("v17.2.7", "cmake/modules/boost-python-use-public-api-for-filename.patch")
assert not exists("v17.2.7", "cmake/modules/ExternalProjectHelper.cmake")

# Optional feature/dependency evidence, including replacement pairs.
for added in (
    "cmake/modules/BuildArrow.cmake",
    "cmake/modules/BuildOpentelemetry.cmake",
    "cmake/modules/BuildUtf8proc.cmake",
    "cmake/modules/BuildZstd.cmake",
    "cmake/modules/FindArrow.cmake",
    "cmake/modules/FindLinuxZNS.cmake",
    "cmake/modules/FindParquet.cmake",
    "cmake/modules/FindQatDrv.cmake",
    "cmake/modules/FindZstd.cmake",
    "cmake/modules/Findthrift.cmake",
    "cmake/modules/Findutf8proc.cmake",
):
    assert not exists("v16.2.15", added) and exists("v17.2.7", added)
for deleted in (
    "cmake/modules/BuildJaeger.cmake",
    "cmake/modules/BuildOpenTracing.cmake",
    "cmake/modules/BuildQatDrv.cmake",
    "cmake/modules/Buildthrift.cmake",
    "cmake/modules/Buildyaml-cpp.cmake",
    "cmake/modules/Findleveldb.cmake",
    "cmake/modules/IncludeJaeger.cmake",
):
    assert exists("v16.2.15", deleted) and not exists("v17.2.7", deleted)
assert "ARROW_PARQUET=ON" in show("v17.2.7", "cmake/modules/BuildArrow.cmake")
assert "opentelemetry_exporter_jaeger_trace" in show("v17.2.7", "cmake/modules/BuildOpentelemetry.cmake")
assert 'set(expected_version "v1.7.L.4.14.0-00031")' in show("v17.2.7", "cmake/modules/FindQatDrv.cmake")
assert "COMPONENTS" in show("v17.2.7", "cmake/modules/Findpmem.cmake")
assert "Zstd::Zstd" in show("v17.2.7", "cmake/modules/BuildZstd.cmake")

# Validation/resource-control evidence.
target_tests = show("v17.2.7", "cmake/modules/AddCephTest.cmake")
assert "PARALLEL" in target_tests and "FIXTURES_SETUP" in target_tests
assert "libasan.so.6" in show("v17.2.7", "cmake/modules/FindSanitizers.cmake")
target_limits = show("v17.2.7", "cmake/modules/LimitJobs.cmake")
assert "MAX_COMPILE_MEM 3500" in target_limits and "CMAKE_JOB_POOL_LINK" in target_limits

reasons = {}
for path in resolver_paths:
    reasons[path] = (
        "PKG-011",
        f"PKG-011: {path} changes compiler/Python/Boost/library discovery or external-build behavior; supported source builds can link a different implementation or fail under a different toolchain gate.",
    )
for path, feature in feature_by_path.items():
    reasons[path] = (
        "PKG-012",
        f"PKG-012: {path} changes how Ceph discovers or builds {feature}; the resulting target capability and linked dependency are artifact-dependent.",
    )
for path in validation_paths:
    reasons[path] = (
        "PKG-013",
        f"PKG-013: {path} changes test registration, sanitizer lookup, or Ninja resource pools and therefore changes build/validation execution and its failure signal.",
    )
assert set(reasons) == paths

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)
for path, (finding_id, reason) in reasons.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == finding_id
        assert row["impact_reason"] == reason
    row["upgrade_impact"] = "affect"
    row["finding_id"] = finding_id
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert affect_count + trivial_count + blank_count == 207
assert (affect_count, trivial_count, blank_count) == (83, 39, 85)

replace_known(
    md_path,
    "Hiện `affect = 40`, `trivial = 39`, **chưa phân loại = 128**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 83`, `trivial = 39`, **chưa phân loại = 85**; binary gate của owner chưa hoàn tất.",
)

findings = """### PKG-011 — Resolver/toolchain CMake đổi ngưỡng và cách chọn implementation

- **CSV:** 25, 27, 39–50, 53–54, 65–66 (trừ các hàng feature được tách ở PKG-012). **Nguồn:** endpoint modules và commit intent: GCC tối thiểu 8.1, Boost 1.75/Python 3.10, bỏ `experimental/filesystem`, đổi Python executable, NUMA/OpenLDAP imported target, FIO path/link và SIMD PowerPC.
- **Trước → sau:** Target thay cả bundled-build glue lẫn `find_package` semantics: nhận Boost/Python mới, bỏ patch Boost.Python cũ và helper ExternalProject dùng chung, chỉ chấp nhận `std::filesystem`, kiểm atomic 16-byte trên MIPS, thay imported target/link hints cho NUMA/OpenLDAP/FIO và mở probe SIMD trên PowerPC. Vì vậy cùng source nhưng toolchain/cache khác có thể chọn thư viện/ABI khác hoặc fail sớm.
- **Điều kiện và tác động:** Chỉ áp dụng cho build source/custom package; official artifact phải được kiểm bằng provenance. Rủi ro chính là tái build không lặp lại, extension Python/linker mismatch, hoặc platform cũ từng build Pacific không còn qua gate Quincy. Không suy runtime regression cụ thể nếu artifact đã build và link đúng. **Độ tin cậy:** cao cho build graph, chưa dựng ma trận. **Kiểm chứng:** clean configure/build trên compiler/Python/Boost/PowerPC/MIPS As-Is, lưu CMake cache/link map; import Python bindings và chạy smoke CLI/daemon từ artifact, không tái dùng build directory Pacific.

### PKG-012 — Optional dependency graph quyết định feature thực có trong artifact

- **CSV:** 24, 26, 28–38, 43, 45, 49, 51, 55–63. **Nguồn:** 25 module build/find; liên quan [RGW-039](./12-rgw.md), [MSG-047](./05-messaging-auth-common.md), [KV-001](./03-rocksdb-block-device.md), [RADOS-003](./10-rados-rbd-clients.md) và dependency gitlink PKG-004/005.
- **Trước → sau:** Quincy thêm Arrow/Parquet, utf8proc, system/bundled zstd, Linux ZNS và QAT driver finder; thay OpenTracing/Jaeger bằng OpenTelemetry; bỏ build bundled Thrift/yaml-cpp và LevelDB finder. DPDK/SPDK/RocksDB/liburing/PMDK/QATzip cũng đổi flags, version/components và link mode. Đây là quyết định compile/link của RGW Parquet, tracing, compressor, RWL, zoned/accelerated IO và backend KV.
- **Điều kiện và tác động:** Feature hiện hữu phụ thuộc CMake option, architecture, package dev files và system-vs-bundled. Rolling cluster có thể chạy artifact cùng version nhưng capability khác; rollback cần đúng library/plugin set, đặc biệt PMDK/RWL, tracing collector, QAT/SPDK/DPDK và RocksDB. Các module không tự chứng minh format state đổi. **Độ tin cậy:** cao cho dependency graph, trung bình cho artifact As-Is. **Kiểm chứng:** lập SBOM/link map/CMake cache cho từng artifact, chạy positive/negative smoke cho từng feature được bật; với RGW giải mã S3 Select/trace, với RWL mở cache clone, với storage accelerator chạy init/error path trên hardware lab.

### PKG-013 — CMake test/resource orchestration đổi tín hiệu CI

- **CSV:** 23, 52, 64. **Nguồn:** `AddCephTest.cmake`, `FindSanitizers.cmake`, `LimitJobs.cmake`.
- **Trước → sau:** Test wrapper target truyền tham số `PARALLEL`/fixture thay vì giữ wiring cũ; sanitizer finder ưu tiên `libasan.so.6`; Ninja có compile/link job pools tính theo bộ nhớ với ngưỡng 3500/4500 MiB. Những thay đổi này quyết định test concurrency/setup, sanitizer runtime và việc build có OOM/throttle.
- **Điều kiện và tác động:** Chỉ là build/validation infrastructure, không chạy trên daemon production. Tuy nhiên thiếu fixture, sanitizer khác hoặc job pool quá chặt/lỏng có thể đổi pass/fail/coverage và thời gian gate. **Độ tin cậy:** cao cho CMake behavior, chưa chạy CI. **Kiểm chứng:** chạy CTest verbose với fixture/parallel, ASAN build đúng distro, Ninja trên worker bộ nhớ thấp/cao; lưu test inventory, skipped tests, sanitizer path và peak RSS trước khi chấp nhận gate.

"""
insert_before_once(md_path, "## Thay đổi trivial", findings)

replace_known(
    readme_path,
    "1.549 hàng `affect`. 1.874 hàng `trivial`. 756 hàng chưa phân loại.",
    "1.592 hàng `affect`. 1.874 hàng `trivial`. 713 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 756 hàng còn thiếu nhãn và lý do", "vì 713 hàng còn thiếu nhãn và lý do")
replace_known(readme_path, "[PKG-001–010]", "[PKG-001–013]")
replace_known(
    readme_path,
    "toolchain, harness và activation",
    "toolchain, CMake dependency graph, harness và activation",
)
replace_known(
    plan_path,
    "`affect 1.549`, `trivial 1.874`, còn **756 hàng chưa phân loại**",
    "`affect 1.592`, `trivial 1.874`, còn **713 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 13 hiện `40 affect`, `39 trivial`, `128` chưa phân loại.",
    "owner 13 hiện `83 affect`, `39 trivial`, `85` chưa phân loại.",
)

print("Classified owner-13 CMake-module batch: 43 affect")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
