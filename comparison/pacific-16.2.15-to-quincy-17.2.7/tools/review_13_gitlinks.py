"""Verify and classify owner-13 dependency/gitlink changes.

The superproject has only the ISA-L submodule objects locally. For other
gitlinks this script asks the authoritative GitHub compare API for commit and
file metadata; it never substitutes a SHA-only conclusion.
"""

import csv
import json
import subprocess
import urllib.request
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "13-build-packaging-submodules.csv"
md_path = root / "13-build-packaging-submodules.md"
readme_path = root / "README.md"
plan_path = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"


def git(*args: str, cwd: Path = repo) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
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
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


def tree_sha(tag: str, path: str) -> str | None:
    line = git("ls-tree", tag, "--", path).stdout.strip()
    if not line:
        return None
    mode, kind, rest = line.split(maxsplit=2)
    sha, actual_path = rest.split("\t", 1)
    assert mode == "160000" and kind == "commit" and actual_path == path
    return sha


def compare(repo_name: str, base: str, target: str) -> dict:
    url = f"https://api.github.com/repos/{repo_name}/compare/{base}...{target}"
    request = urllib.request.Request(url, headers={"User-Agent": "Codex-Ceph-Comparison"})
    with urllib.request.urlopen(request, timeout=30) as response:
        assert response.status == 200
        return json.load(response)


rows_to_classify = {
    ".gitmodules": (
        "PKG-004",
        "PKG-004: dependency manifest removes bundled Civetweb/OpenTracing-Jaeger/Thrift and adds Arrow/utf8proc; custom and offline builds must synchronize the source set and resulting feature gates.",
    ),
    "ceph-object-corpus": (
        "PKG-006",
        "PKG-006: compatibility corpus advances to include a Pacific archive and forward/backward-incompatibility markers, changing dencoder validation coverage rather than production runtime.",
    ),
    "src/arrow": (
        "RGW-039",
        "RGW-039: target adds bundled Apache Arrow 6.0.1 source for the compile-time-gated S3 Select Parquet path.",
    ),
    "src/civetweb": (
        "RGW-004",
        "RGW-004: target deletes the bundled Civetweb gitlink together with the removed RGW Civetweb/Mongoose frontend.",
    ),
    "src/dmclock": (
        "PKG-005",
        "PKG-005: dmclock advances by 26 commits including scheduling fixes and Seastar synchronization changes compiled into scheduler users.",
    ),
    "src/fmt": (
        "PKG-005",
        "PKG-005: bundled fmt advances by 961 commits and changes public headers/formatting implementation used across target binaries when system fmt is not selected.",
    ),
    "src/isa-l": (
        "PKG-005",
        "PKG-005: bundled ISA-L advances through the aarch64 text-relocation fix plus compression/CRC/build changes; applicability depends on architecture and bundled-library selection.",
    ),
    "src/jaegertracing/jaeger-client-cpp": (
        "MSG-047",
        "MSG-047: target deletes the bundled OpenTracing Jaeger client as tracing moves to OpenTelemetry Jaeger.",
    ),
    "src/jaegertracing/opentracing-cpp": (
        "MSG-047",
        "MSG-047: target deletes the bundled OpenTracing API implementation as tracing moves to OpenTelemetry.",
    ),
    "src/jaegertracing/thrift": (
        "MSG-047",
        "MSG-047: target deletes the bundled Thrift gitlink used by the old Jaeger client and uses the target tracing/toolchain path instead.",
    ),
    "src/rocksdb": (
        "PKG-005",
        "PKG-005: bundled RocksDB changes from the Pacific Ceph fork baseline to a diverged v6.15.5-era target (832 commits ahead, 12 behind), requiring artifact and store regression validation.",
    ),
    "src/s3select": (
        "RGW-039",
        "RGW-039: bundled S3 Select advances by 56 commits with query functions, response handling and Parquet integration consumed by the target RGW path.",
    ),
    "src/seastar": (
        "PKG-005",
        "PKG-005: bundled Seastar advances by 679 commits and changes reactor/coroutine/alien behavior used only by Crimson/Seastar artifacts.",
    ),
    "src/utf8proc": (
        "PKG-003",
        "PKG-003: target adds bundled utf8proc 2.2.0 source while Debian explicitly selects the system library, so artifact provenance determines the linked implementation.",
    ),
}
assert len(rows_to_classify) == 14

expected_tree = {
    "ceph-object-corpus": ("70228ed56466b4be8a9abff9024f69820f68f6d0", "038c72b5acec667e1aca4c79a8cfcae705d766fe"),
    "src/arrow": (None, "347a88ff9d20e2a4061eec0b455b8ea1aa8335dc"),
    "src/civetweb": ("bb99e93da00c3fe8c6b6a98520fb17cf64710ce7", None),
    "src/dmclock": ("9b1326cfa09735ae18b1c4c308ec424c5f1b9cce", "e4ccdcfa828c84b8ea775a928118f2b8012d0f42"),
    "src/fmt": ("51bf9cfacb644659e5d9c7e6fe66396726f2f4f4", "427b53405442872decb69d9735db0fa64106ebe2"),
    "src/isa-l": ("4b36e413c9ac28b4757b297779470693b699aeae", "bee5180a1517f8b5e70b02fcd66790c623536c5d"),
    "src/jaegertracing/jaeger-client-cpp": ("7ad60f7330a421fe2adcab1a2d3dbf4159af6bc2", None),
    "src/jaegertracing/opentracing-cpp": ("4bb431f7728eaf383a07e86f9754a5b67575dab0", None),
    "src/jaegertracing/thrift": ("b75e88a33d67ae05ef9b5fa001d2a63a2effe377", None),
    "src/rocksdb": ("8ab4c1aa3f1c7d89077d7f81e7d457e8333a0430", "c540de6f709b66efd41436694f72d6f7986a325b"),
    "src/s3select": ("7ae7a12c138d4607d6c012228c06f3802c493c49", "1609bb2ab5441d2314f56858f4f98fc2be509f89"),
    "src/seastar": ("afafbaa8d43627fffa00541ac26a31904d0268ab", "ce2652d39dc06801c2cfb983d6cd30937937feba"),
    "src/utf8proc": (None, "97ef668b312b96382714dbb8eaac4affce0816e6"),
}
for path, (base, target) in expected_tree.items():
    assert tree_sha("v16.2.15", path) == base
    assert tree_sha("v17.2.7", path) == target

gitmodules_diff = git("diff", "v16.2.15", "v17.2.7", "--", ".gitmodules").stdout
for added in ("src/arrow", "src/utf8proc"):
    assert f"+\tpath = {added}" in gitmodules_diff
for removed in ("src/civetweb", "src/jaegertracing/opentracing-cpp", "src/jaegertracing/jaeger-client-cpp", "src/jaegertracing/thrift"):
    assert f"-\tpath = {removed}" in gitmodules_diff

api_expectations = {
    "ceph/dmclock": (expected_tree["src/dmclock"], "ahead", 26, 0, 6),
    "ceph/fmt": (expected_tree["src/fmt"], "ahead", 961, 0, 111),
    "ceph/rocksdb": (expected_tree["src/rocksdb"], "diverged", 832, 12, 300),
    "ceph/s3select": (expected_tree["src/s3select"], "ahead", 56, 0, 19),
    "ceph/seastar": (expected_tree["src/seastar"], "ahead", 679, 0, 237),
    "ceph/ceph-object-corpus": (expected_tree["ceph-object-corpus"], "ahead", 5, 0, 300),
}
for repo_name, ((base, target), status, ahead, behind, file_count) in api_expectations.items():
    assert base and target
    data = compare(repo_name, base, target)
    assert (data["status"], data["ahead_by"], data["behind_by"], len(data["files"])) == (
        status,
        ahead,
        behind,
        file_count,
    )

isa_repo = repo / "src" / "isa-l"
assert git("cat-file", "-t", expected_tree["src/isa-l"][1], cwd=isa_repo).stdout.strip() == "commit"
isa_titles = git(
    "log",
    "--format=%s",
    f"{expected_tree['src/isa-l'][0]}..{expected_tree['src/isa-l'][1]}",
    cwd=isa_repo,
).stdout
assert "erasure_code: Fix text relocation on aarch64" in isa_titles

for finding, report in (("RGW-004", "12-rgw.md"), ("RGW-039", "12-rgw.md"), ("MSG-047", "05-messaging-auth-common.md")):
    assert f"### {finding} " in (root / report).read_text(encoding="utf-8-sig")

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert set(rows_to_classify) <= set(by_path)
for path, (finding_id, reason) in rows_to_classify.items():
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
assert (affect_count, trivial_count, blank_count) == (25, 39, 143)

replace_known(
    md_path,
    "Hiện `affect = 11`, `trivial = 39`, **chưa phân loại = 157**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 25`, `trivial = 39`, **chưa phân loại = 143**; binary gate của owner chưa hoàn tất.",
)

findings = """### PKG-004 — Tập source dependency bundled thay đổi theo feature target

- **CSV:** 9; các gitlink 1470, 1546, 2039–2041 và 4176 trỏ thêm tới RGW-004, RGW-039, MSG-047, PKG-003. **Nguồn:** `.gitmodules`, git tree hai tag và commit superproject tương ứng.
- **Trước → sau:** Quincy xóa submodule Civetweb cùng ba submodule OpenTracing/Jaeger/Thrift cũ, đồng thời thêm Apache Arrow 6.0.1 và utf8proc 2.2.0. Đây khớp với việc bỏ frontend RGW Civetweb, chuyển tracing sang OpenTelemetry, thêm S3 Select Parquet và cho phép bundled/system utf8proc; không phải chỉ dọn metadata Git.
- **Điều kiện và tác động:** Build từ source/offline cache phải chạy đồng bộ submodule và mirror đúng tập mới; nếu giữ cache/allowlist Pacific, build có thể thiếu Arrow/utf8proc hoặc vẫn mang source không còn caller. Capability runtime vẫn phụ thuộc CMake/profile và việc chọn system library, nên mixed deployment có thể có RGW Parquet/tracing khác nhau dù cùng version. **Độ tin cậy:** cao cho tree/build linkage, chưa dựng artifact. **Kiểm chứng:** clone sạch từng tag với recursive submodule, build ma trận bundled/system, lưu CMake cache/SBOM/link map và smoke-test RGW frontend, S3 Select Parquet, tracing.

### PKG-005 — Baseline thư viện bundled đổi cả fast-forward và divergent history

- **CSV:** 1982, 1999, 2038, 3635, 3649. **Nguồn:** gitlink SHA, object ISA-L cục bộ và GitHub compare API chính thức cho các repository Ceph dependency. `dmclock` đi trước 26 commit, `fmt` 961, `seastar` 679; ISA-L đi qua commit sửa text relocation aarch64. RocksDB target ở nhánh **diverged**, đi trước 832 nhưng thiếu 12 commit so với baseline Pacific; commit superproject đặt target ở dòng v6.15.5.
- **Trước → sau:** Target kéo thay đổi scheduling/Seastar trong dmclock, API/formatter mới trong fmt, compression/CRC/build và fix aarch64 trong ISA-L, một baseline RocksDB khác, cùng reactor/coroutine/alien mới của Seastar. Đây là source được compile/link khi dùng bundled dependency; không thể suy tương đương chỉ vì interface Ceph vẫn build.
- **Điều kiện và tác động:** Áp dụng theo `WITH_SYSTEM_*`, architecture và việc chạy classic hay Crimson. RocksDB là đường persistent store nên baseline divergent cần đặc biệt kiểm mở DB/compaction/rollback, nhưng source evidence chưa chứng minh format SST/MANIFEST cụ thể đã đổi. dmclock ảnh hưởng scheduler users; Seastar chỉ ảnh hưởng artifact Crimson; fmt có thể đổi output/exception tại các caller đã được owner chức năng phân tích. **Độ tin cậy:** cao về commit graph/file set, trung bình về artifact thực tế. **Kiểm chứng:** trích SBOM/link map, chạy store-open/compaction/restart trên clone DB Pacific với binary target rồi rollback lab, scheduler regression, aarch64 loader check, và Crimson canary; so cả build system-library lẫn bundled nếu pipeline hỗ trợ.

### PKG-006 — Object corpus đổi baseline kiểm tương thích, không phải runtime payload

- **CSV:** 21. **Nguồn:** gitlink `ceph-object-corpus` đi trước năm commit. Commit superproject `13f3129f54e91053ed26ce5007c53d57ef5de6da` lấy archive `16.2.0-90-g50f1821b4c`; lịch sử dependency còn đánh dấu `MOSDScrub`/log-related classes forward-incompatible và bỏ một archive không còn backward-compatible.
- **Trước → sau:** Target dencoder corpus có thêm object encode từ nhánh Pacific và metadata expected incompatibility, nên tập type/fixture được thử và cách diễn giải failure khác baseline Pacific. Corpus không được cài vào daemon production.
- **Điều kiện và tác động:** Chỉ ảnh hưởng pipeline compatibility/dencoder có checkout submodule; bỏ qua cập nhật submodule có thể tạo false pass/false fail hoặc không kiểm type mới trước rollout. Không có mixed-version runtime effect độc lập. **Độ tin cậy:** cao về corpus history, chưa chạy corpus. **Kiểm chứng:** chạy exact corpus target với dencoder Pacific/Quincy, lưu danh sách expected pass/fail/forward-incompatible và tách regression bất ngờ khỏi incompatibility được khai báo.

"""
insert_before_once(md_path, "## Thay đổi trivial", findings)

replace_known(
    readme_path,
    "1.520 hàng `affect`. 1.874 hàng `trivial`. 785 hàng chưa phân loại.",
    "1.534 hàng `affect`. 1.874 hàng `trivial`. 771 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 785 hàng còn thiếu nhãn và lý do", "vì 771 hàng còn thiếu nhãn và lý do")
replace_known(readme_path, "[PKG-001–003]", "[PKG-001–006]")
replace_known(
    readme_path,
    "cho split `ceph-volume`, payload MGR và ma trận build Debian",
    "cho split `ceph-volume`, payload MGR, ma trận build Debian, source dependency/gitlink và corpus tương thích",
)
replace_known(
    plan_path,
    "`affect 1.520`, `trivial 1.874`, còn **785 hàng chưa phân loại**",
    "`affect 1.534`, `trivial 1.874`, còn **771 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 13 hiện `11 affect`, `39 trivial`, `157` chưa phân loại.",
    "owner 13 hiện `25 affect`, `39 trivial`, `143` chưa phân loại.",
)

print("Classified owner-13 dependency/gitlink batch: 14 affect")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
