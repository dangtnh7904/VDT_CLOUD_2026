"""Classify owner-15 src/test rows outside the exact upgrade gate."""

import csv
import subprocess
from collections import Counter
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
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
test_rows = [row for row in rows if row["path"].startswith("src/test/")]
assert len(test_rows) == 100

diff_paths = set(
    git(
        "diff",
        "--no-renames",
        "--name-only",
        "v16.2.15",
        "v17.2.7",
        "--",
        "src/test",
    ).stdout.splitlines()
)
assert {row["path"] for row in test_rows} <= diff_paths

# Pacific-x composes QA task/workunit YAML only.  No source-test path is named
# by the exact-pair suite, so these files cannot change that suite's verdict.
exact_ref = git(
    "grep",
    "-F",
    "src/test/",
    "v17.2.7",
    "--",
    "qa/suites/upgrade/pacific-x",
    check=False,
)
assert exact_ref.returncode == 1 and not exact_ref.stdout
exact_tasks = git(
    "grep",
    "-n",
    "-E",
    r"(workunit:|thrashosds|ceph\.healthy)",
    "v17.2.7",
    "--",
    "qa/suites/upgrade/pacific-x",
).stdout
assert "workunit:" in exact_tasks and "thrashosds" in exact_tasks


def category(path: str) -> str:
    if path.startswith("src/test/behave_tests/"):
        return "behave"
    if path.startswith(
        (
            "src/test/debian-strech/",
            "src/test/fedora-",
            "src/test/ubuntu-16.04/",
        )
    ) or path in {
        "src/test/fedora-32",
        "src/test/fedora-33",
        "src/test/fedora-34",
    }:
        return "distro-fixture"
    if path.startswith(
        (
            "src/test/crimson/",
            "src/test/direct_messenger/",
            "src/test/fio/",
        )
    ):
        return "crimson-messenger-fio"
    if path.startswith("src/test/cls_"):
        return "cls"
    return "unit-bench-other"


groups = Counter(category(row["path"]) for row in test_rows)
assert groups == {
    "behave": 10,
    "cls": 8,
    "crimson-messenger-fio": 14,
    "distro-fixture": 12,
    "unit-bench-other": 56,
}

reasons = {
    "behave": (
        "VAL-SRC-TEST-01: generic cephadm/ceph-shell behave scenario is not "
        "composed by qa/suites/upgrade/pacific-x and does not execute an "
        "endpoint-to-endpoint upgrade."
    ),
    "distro-fixture": (
        "VAL-SRC-TEST-02: build-test container/distro fixture is outside the "
        "container-host matrix selected by Pacific-x; it cannot change this "
        "pair's acceptance execution."
    ),
    "crimson-messenger-fio": (
        "VAL-SRC-TEST-03: Crimson/messenger/FIO unit or benchmark source is not "
        "invoked by the exact Pacific-x tasks or workunits; it is independent "
        "test coverage."
    ),
    "cls": (
        "VAL-SRC-TEST-04: CLS unit-test source validates component behavior but "
        "is not one of the workunits selected by Pacific-x; it supplies no "
        "exact-pair verdict."
    ),
    "unit-bench-other": (
        "VAL-SRC-TEST-05: unit/benchmark/test support source is outside the "
        "Pacific-x execution graph; related production behavior is assessed in "
        "its owning component rather than inferred from this test-only row."
    ),
}

for row in test_rows:
    reason = reasons[category(row["path"])]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial"
        assert row["finding_id"] == ""
        assert row["impact_reason"] == reason
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert (affect_count, trivial_count, blank_count) == (61, 411, 156)

replace_known(
    md_path,
    "Hiện `affect = 61`, `trivial = 311`, **chưa phân loại = 256**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 61`, `trivial = 411`, **chưa phân loại = 156**; binary gate của owner chưa hoàn tất.",
)

summary = """100 hàng `src/test/**` được kiểm theo composition thay vì suy từ hậu tố test: exact Pacific-x không tham chiếu đường dẫn nào trong cây này và chỉ gọi các task/workunit QA riêng. Batch gồm 10 behave scenario cephadm/ceph-shell độc lập, 12 fixture container distro build-test, 14 test Crimson/messenger/FIO, tám CLS unit test và 56 unit/benchmark/support test khác. Một số hunk phản ánh thay đổi production quan trọng (compat feature, encode/decode, admin socket, CORS, SnapMapper), nhưng chính test source này không được exact suite chạy; hành vi production tương ứng đã/được xét ở owner component nên 100 hàng nhận `trivial`, không dùng test churn làm bằng chứng tác động.

"""
insert_before_once(md_path, "## Kiểm chứng cần hoàn thành", summary)

replace_known(
    readme_path,
    "1.722 hàng `affect`. 2.201 hàng `trivial`. 256 hàng chưa phân loại.",
    "1.722 hàng `affect`. 2.301 hàng `trivial`. 156 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 256 hàng còn thiếu nhãn và lý do", "vì 156 hàng còn thiếu nhãn và lý do")

replace_known(
    plan_path,
    "`affect 1.722`, `trivial 2.201`, còn **256 hàng chưa phân loại**.",
    "`affect 1.722`, `trivial 2.301`, còn **156 hàng chưa phân loại**.",
)
replace_known(
    plan_path,
    "owner 15 hiện `61 affect`, `311 trivial`, `256` chưa phân loại.",
    "owner 15 hiện `61 affect`, `411 trivial`, `156` chưa phân loại.",
)

global_affect = 0
global_trivial = 0
global_blank = 0
global_rows = 0
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
    global_affect += sum(
        row["upgrade_impact"] == "affect" for row in component_rows
    )
    global_trivial += sum(
        row["upgrade_impact"] == "trivial" for row in component_rows
    )
    global_blank += sum(not row["upgrade_impact"] for row in component_rows)
assert (global_rows, global_affect, global_trivial, global_blank) == (
    4179,
    1722,
    2301,
    156,
)

print("Reviewed owner-15 src/test rows: 0 affect, 100 trivial")
print(
    f"Owner totals: affect={affect_count} trivial={trivial_count} "
    f"unclassified={blank_count}"
)
print(
    f"Suite totals: affect={global_affect} trivial={global_trivial} "
    f"unclassified={global_blank}"
)
