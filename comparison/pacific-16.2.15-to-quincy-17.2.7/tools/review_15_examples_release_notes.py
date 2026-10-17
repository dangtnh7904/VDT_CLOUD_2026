"""Classify owner-15 examples and the release-note source as references."""

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


with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = [
    row
    for row in rows
    if row["path"] == "PendingReleaseNotes"
    or row["path"].startswith("examples/")
]
assert len(selected) == 17


def category(path: str) -> str:
    if path == "PendingReleaseNotes":
        return "release-notes"
    if path.startswith("examples/lua/"):
        return "lua"
    if path.startswith("examples/rgw-cache/"):
        return "rgw-cache"
    if path.startswith("examples/boto3/"):
        return "boto3"
    return "librados"


groups = Counter(category(row["path"]) for row in selected)
assert groups == {
    "release-notes": 1,
    "lua": 10,
    "rgw-cache": 3,
    "boto3": 2,
    "librados": 1,
}

diff_paths = set(
    git(
        "diff",
        "--no-renames",
        "--name-only",
        "v16.2.15",
        "v17.2.7",
        "--",
        "PendingReleaseNotes",
        "examples",
    ).stdout.splitlines()
)
assert {row["path"] for row in selected} <= diff_paths

exact_examples = git(
    "grep",
    "-F",
    "examples/",
    "v17.2.7",
    "--",
    "qa/suites/upgrade/pacific-x",
    check=False,
)
assert exact_examples.returncode == 1 and not exact_examples.stdout

# Keep guards for the substantive reference signals so a later endpoint change
# cannot silently turn this into a spelling-only classification.
notes = show("v17.2.7", "PendingReleaseNotes")
assert "require-osd-release" in notes
assert "backwards-incompatible changes to the ON-RADOS" in notes
assert "LevelDB support has been removed" in notes
lua_adapter = show("v17.2.7", "examples/lua/elasticsearch_adapter.lua")
assert "Request.User.Tenant" in lua_adapter
assert "Request.HTTP.Metadata" in lua_adapter

reasons = {
    "release-notes": (
        "VAL-REFERENCE-01: PendingReleaseNotes documents compatibility and "
        "operator warnings but is not executable; the underlying production "
        "changes are classified in their owning component findings."
    ),
    "lua": (
        "VAL-EXAMPLE-01: standalone RGW Lua adapter/example is neither installed "
        "nor referenced by Pacific-x; it demonstrates the API but cannot change "
        "an existing upgrade unless an operator separately deploys it."
    ),
    "rgw-cache": (
        "VAL-EXAMPLE-02: sample nginx cache configuration changes only an "
        "optional copied deployment example and is outside the exact-pair suite."
    ),
    "boto3": (
        "VAL-EXAMPLE-03: Boto3 example changes comments only and is not executed "
        "by the exact upgrade validation path."
    ),
    "librados": (
        "VAL-EXAMPLE-04: hello-world example fixes completion release handling "
        "but is not a shipped upgrade tool or Pacific-x workload."
    ),
}

for row in selected:
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
assert (affect_count, trivial_count, blank_count) == (61, 428, 139)

replace_known(
    md_path,
    "Hiện `affect = 61`, `trivial = 411`, **chưa phân loại = 156**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 61`, `trivial = 428`, **chưa phân loại = 139**; binary gate của owner chưa hoàn tất.",
)

summary = """16 file dưới `examples/**` và `PendingReleaseNotes` được dùng làm nguồn tham chiếu nhưng không phải execution artifact của exact suite. Lua adapter mới minh họa `Request.User`/HTTP metadata, nginx cache là config mẫu, Boto3 chỉ sửa comment và librados hello-world sửa giải phóng completion; không file nào được Pacific-x gọi hay tự động triển khai. `PendingReleaseNotes` nêu nhiều cảnh báo thật như metadata MDS không downgrade, LevelDB bị bỏ và `require-osd-release`, nhưng các tác động đó được gắn vào source/config ở owner tương ứng; bản thân tài liệu nhận `trivial` để tránh đếm đôi bằng chứng thành hành vi.

"""
insert_before_once(md_path, "## Kiểm chứng cần hoàn thành", summary)

replace_known(
    readme_path,
    "1.722 hàng `affect`. 2.301 hàng `trivial`. 156 hàng chưa phân loại.",
    "1.722 hàng `affect`. 2.318 hàng `trivial`. 139 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 156 hàng còn thiếu nhãn và lý do", "vì 139 hàng còn thiếu nhãn và lý do")

replace_known(
    plan_path,
    "`affect 1.722`, `trivial 2.301`, còn **156 hàng chưa phân loại**.",
    "`affect 1.722`, `trivial 2.318`, còn **139 hàng chưa phân loại**.",
)
replace_known(
    plan_path,
    "owner 15 hiện `61 affect`, `411 trivial`, `156` chưa phân loại.",
    "owner 15 hiện `61 affect`, `428 trivial`, `139` chưa phân loại.",
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
    2318,
    139,
)

print("Reviewed owner-15 examples/release notes: 0 affect, 17 trivial")
print(
    f"Owner totals: affect={affect_count} trivial={trivial_count} "
    f"unclassified={blank_count}"
)
print(
    f"Suite totals: affect={global_affect} trivial={global_trivial} "
    f"unclassified={global_blank}"
)
