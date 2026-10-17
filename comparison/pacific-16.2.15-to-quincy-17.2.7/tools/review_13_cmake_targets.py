"""Classify the remaining production and validation CMake target graphs."""

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
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


validation_paths = {
    "qa/CMakeLists.txt",
    "src/rgw/store/dbstore/tests/CMakeLists.txt",
    "src/test/CMakeLists.txt",
    "src/test/cls_rgw/CMakeLists.txt",
    "src/test/common/CMakeLists.txt",
    "src/test/compressor/CMakeLists.txt",
    "src/test/crimson/CMakeLists.txt",
    "src/test/crimson/seastore/CMakeLists.txt",
    "src/test/crimson/seastore/onode_tree/CMakeLists.txt",
    "src/test/erasure-code/CMakeLists.txt",
    "src/test/lazy-omap-stats/CMakeLists.txt",
    "src/test/librados/CMakeLists.txt",
    "src/test/librbd/CMakeLists.txt",
    "src/test/msgr/CMakeLists.txt",
    "src/test/neorados/CMakeLists.txt",
    "src/test/osd/CMakeLists.txt",
    "src/test/rgw/CMakeLists.txt",
}

production_paths = {
    "monitoring/ceph-mixin/CMakeLists.txt",
    "src/CMakeLists.txt",
    "src/arch/CMakeLists.txt",
    "src/auth/CMakeLists.txt",
    "src/blk/CMakeLists.txt",
    "src/cls/CMakeLists.txt",
    "src/common/CMakeLists.txt",
    "src/common/options/CMakeLists.txt",
    "src/compressor/CMakeLists.txt",
    "src/compressor/zstd/CMakeLists.txt",
    "src/crimson/CMakeLists.txt",
    "src/crimson/admin/CMakeLists.txt",
    "src/crimson/os/CMakeLists.txt",
    "src/crimson/os/alienstore/CMakeLists.txt",
    "src/crimson/os/seastore/CMakeLists.txt",
    "src/crimson/osd/CMakeLists.txt",
    "src/crimson/tools/CMakeLists.txt",
    "src/crypto/qat/CMakeLists.txt",
    "src/erasure-code/CMakeLists.txt",
    "src/exporter/CMakeLists.txt",
    "src/global/CMakeLists.txt",
    "src/include/CMakeLists.txt",
    "src/librbd/CMakeLists.txt",
    "src/mgr/CMakeLists.txt",
    "src/mon/CMakeLists.txt",
    "src/msg/CMakeLists.txt",
    "src/neorados/CMakeLists.txt",
    "src/os/CMakeLists.txt",
    "src/osd/CMakeLists.txt",
    "src/perfglue/CMakeLists.txt",
    "src/pybind/CMakeLists.txt",
    "src/pybind/mgr/CMakeLists.txt",
    "src/pybind/mgr/dashboard/CMakeLists.txt",
    "src/pybind/mgr/dashboard/frontend/CMakeLists.txt",
    "src/pybind/mgr/rook/CMakeLists.txt",
    "src/pybind/rados/CMakeLists.txt",
    "src/pybind/rgw/CMakeLists.txt",
    "src/rgw/store/dbstore/CMakeLists.txt",
    "src/rgw/store/dbstore/sqlite/CMakeLists.txt",
    "src/tools/CMakeLists.txt",
    "src/tools/ceph-dencoder/CMakeLists.txt",
}

assert len(validation_paths) == 17
assert len(production_paths) == 41
paths = validation_paths | production_paths
assert len(paths) == 58
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# Representative production graph guards cover new installed binaries/modules,
# generated configuration, protocol source membership and plugin delivery.
root_graph = show("v17.2.7", "src/CMakeLists.txt")
assert "add_subdirectory(exporter)" in root_graph
assert "legacy-option-headers" in root_graph
options_graph = show("v17.2.7", "src/common/options/CMakeLists.txt")
assert "add_custom_target(legacy-option-headers" in options_graph
assert "add_ceph_test(validate-options" in options_graph
exporter_graph = show("v17.2.7", "src/exporter/CMakeLists.txt")
assert "add_executable(ceph-exporter" in exporter_graph
assert "install(TARGETS ceph-exporter DESTINATION bin)" in exporter_graph
mgr_graph = show("v17.2.7", "src/pybind/mgr/CMakeLists.txt")
assert "object_format.py" in mgr_graph and "TOX_ENVS py3 py37 mypy flake8 jinjalint nooptional" in mgr_graph
frontend_graph = show("v17.2.7", "src/pybind/mgr/dashboard/frontend/CMakeLists.txt")
assert "mgr-dashboard-frontend-build" in frontend_graph and "npm run build:localize" in frontend_graph
dbstore_graph = show("v17.2.7", "src/rgw/store/dbstore/CMakeLists.txt")
assert "add_library(dbstore_lib" in dbstore_graph and "add_subdirectory(sqlite)" in dbstore_graph
assert "async/compression_onwire.cc" in show("v17.2.7", "src/msg/CMakeLists.txt")
dencoder_graph = show("v17.2.7", "src/tools/ceph-dencoder/CMakeLists.txt")
assert "add_custom_target(ceph-dencoder-modules)" in dencoder_graph
assert "add_denc_mod(denc-mod-osd" in dencoder_graph

# Representative validation graph guards cover newly registered QA gates.
assert "TOX_ENVS flake8 mypy deadsymlinks" in show("v17.2.7", "qa/CMakeLists.txt")
assert "add_ceph_unittest(unittest_dbstore_tests)" in show(
    "v17.2.7", "src/rgw/store/dbstore/tests/CMakeLists.txt"
)
assert "unittest_comp_registry" in show("v17.2.7", "src/test/msgr/CMakeLists.txt")
assert "unittest-object-data-handler" in show("v17.2.7", "src/test/crimson/seastore/CMakeLists.txt")
assert "ceph_test_lazy_omap_stats" in show("v17.2.7", "src/test/lazy-omap-stats/CMakeLists.txt")

reasons = {}
for path in production_paths:
    reasons[path] = (
        "PKG-014",
        f"PKG-014: {path} changes production source/target/link/install membership; it determines which Quincy binary, plugin, Python module, generated option or frontend asset is delivered.",
    )
for path in validation_paths:
    reasons[path] = (
        "PKG-015",
        f"PKG-015: {path} changes test/QA target registration, linkage or execution arguments and therefore changes upgrade-relevant validation coverage and failure signals.",
    )

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
assert (affect_count, trivial_count, blank_count) == (141, 39, 27)

replace_known(
    md_path,
    "Hiện `affect = 83`, `trivial = 39`, **chưa phân loại = 85**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 141`, `trivial = 39`, **chưa phân loại = 27**; binary gate của owner chưa hoàn tất.",
)

findings = """### PKG-014 — Production target graph đổi binary/plugin/module thực được giao

- **CSV:** 41 hàng CMake production từ monitoring, core/classic/Crimson, compressor/crypto/EC, MGR/dashboard/Python, RGW DBStore, exporter và tools. **Nguồn:** endpoint target membership và commit history; owner chức năng giữ semantics runtime, owner 13 giữ hunk delivery để partition không trùng.
- **Trước → sau:** Target graph thêm `ceph-exporter`, generated option YAML/legacy headers, on-wire compression, RGW DBStore/SQLite, Dashboard frontend build tách riêng, `object_format.py`, dencoder plugins và nhiều SeaStore/Crimson target; đồng thời đổi source/link của tracing, QAT/zstd, allocator, RBD PWL, MGR/SQLite, RGW frontend và Python modules. Các thay đổi này quyết định code đã phân tích ở owner khác có thật sự vào binary/package hay không.
- **Điều kiện và tác động:** Áp dụng theo CMake option, platform và package split. Custom build có thể compile thành công nhưng thiếu target/module/asset nếu mang cache/list cũ; mixed cluster cùng version có thể khác capability. Finding này không nhân đôi từng behavior: exporter xem CFG-013/MGR, compression xem MSG, DBStore/S3 Select xem RGW, PWL xem RADOS, SeaStore/Crimson xem OSD/SEA. **Độ tin cậy:** cao cho graph, chưa kiểm artifact. **Kiểm chứng:** clean-build từng profile, đối chiếu target/install manifest, symbols/plugins/Python imports/frontend assets và SBOM; smoke-test từng feature bật, rồi so package payload với chính artifact rollout.

### PKG-015 — Test target graph đổi coverage và execution contract

- **CSV:** 17 hàng `qa`, `src/test/*` và DBStore tests. **Nguồn:** endpoint target registration/link/args cùng commit history.
- **Trước → sau:** Quincy đăng ký thêm mypy/dead-symlink, DBStore, on-wire compression registry, journald, lazy OMAP stats, remote-read class, RBD migration/QCOW, RGW stats và nhiều SeaStore/FLTree/RBM test; một số test Crimson đổi `--smp`/memory/logging, tên target hoặc được bật/tắt lại. Link dependencies cũng theo production graph mới.
- **Điều kiện và tác động:** Chỉ ảnh hưởng validation, không chạy trong daemon production. Pass/fail giữa hai branch không đồng nghĩa cùng coverage: target có case mới nhưng cũng có test tạm disable/đổi runtime resource. **Độ tin cậy:** cao cho registration, chưa chạy CTest. **Kiểm chứng:** xuất `ctest -N -V` hai build sạch, so tên/label/command/skipped test; chạy nhóm DBStore, msgr compression, RBD, RGW, OSD/SeaStore và QA mypy với timeout/resource cố định, lưu JUnit/log đầy đủ.

"""
insert_before_once(md_path, "## Thay đổi trivial", findings)

replace_known(
    readme_path,
    "1.592 hàng `affect`. 1.874 hàng `trivial`. 713 hàng chưa phân loại.",
    "1.650 hàng `affect`. 1.874 hàng `trivial`. 655 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 713 hàng còn thiếu nhãn và lý do", "vì 655 hàng còn thiếu nhãn và lý do")
replace_known(readme_path, "[PKG-001–013]", "[PKG-001–015]")
replace_known(
    readme_path,
    "CMake dependency graph, harness và activation",
    "CMake dependency/target graph, validation harness và activation",
)
replace_known(
    plan_path,
    "`affect 1.592`, `trivial 1.874`, còn **713 hàng chưa phân loại**",
    "`affect 1.650`, `trivial 1.874`, còn **655 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 13 hiện `83 affect`, `39 trivial`, `85` chưa phân loại.",
    "owner 13 hiện `141 affect`, `39 trivial`, `27` chưa phân loại.",
)

print("Classified owner-13 CMake target graphs: 41 production affect, 17 validation affect")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
