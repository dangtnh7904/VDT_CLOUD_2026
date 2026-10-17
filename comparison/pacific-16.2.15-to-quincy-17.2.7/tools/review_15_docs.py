"""Classify owner-15 documentation rows as non-executable references."""

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
doc_rows = [row for row in rows if row["path"].startswith("doc/")]
assert len(doc_rows) == 98

diff_paths = set(
    git(
        "diff",
        "--no-renames",
        "--name-only",
        "v16.2.15",
        "v17.2.7",
        "--",
        "doc",
    ).stdout.splitlines()
)
assert {row["path"] for row in doc_rows} <= diff_paths

exact_doc_ref = git(
    "grep",
    "-F",
    "doc/",
    "v17.2.7",
    "--",
    "qa/suites/upgrade/pacific-x",
    check=False,
)
assert exact_doc_ref.returncode == 1 and not exact_doc_ref.stdout


def category(path: str) -> str:
    if path.startswith("doc/_") or path == "doc/conf.py":
        return "doc-build"
    if (
        path.startswith(
            "doc/dev/developer_guide/testing_integration_tests/"
        )
        or path.startswith("doc/dev/developer_guide/running-tests-")
        or path
        in {
            "doc/dev/continuous-integration.rst",
            "doc/dev/testing.rst",
        }
    ):
        return "testing-guide"
    if path.startswith("doc/man/") or path == "doc/man_index.rst":
        return "man"
    if path.startswith("doc/rados/"):
        return "rados"
    if path.startswith("doc/releases/"):
        return "release-index"
    return "general-reference"


groups = Counter(category(row["path"]) for row in doc_rows)
assert groups == {
    "doc-build": 9,
    "general-reference": 35,
    "man": 24,
    "rados": 19,
    "release-index": 1,
    "testing-guide": 10,
}

# Guard the high-signal content: these are substantive references, not merely
# typo churn, but still do not execute or select an upgrade job.
encoding = show("v17.2.7", "doc/dev/encoding.rst")
assert "compatibility continues between old decoders and new encoders" in encoding
cephadm_man = show("v17.2.7", "doc/man/8/cephadm.rst")
assert "When starting the shell, cephadm looks for configuration" in cephadm_man
releases = show("v17.2.7", "doc/releases/releases.yml")
assert "quincy:" in releases and "17.2.0" in releases
integration = show(
    "v17.2.7",
    "doc/dev/developer_guide/testing_integration_tests/"
    "tests-integration-testing-teuthology-intro.rst",
)
assert "upgrade" in integration.lower() and "teuthology" in integration.lower()

reasons = {
    "doc-build": (
        "VAL-DOC-01: Sphinx extension/theme/template/config changes rendered "
        "documentation only; they are not consumed by Pacific-x or by a cluster "
        "upgrade command."
    ),
    "testing-guide": (
        "VAL-DOC-02: integration/teuthology guide describes how to create or "
        "debug tests but is not an executable suite composition and supplies no "
        "exact-pair result."
    ),
    "man": (
        "VAL-DOC-03: command manpage documents CLI behavior but is not executed "
        "by Pacific-x; the corresponding source/tool change is classified at its "
        "own row or component."
    ),
    "rados": (
        "VAL-DOC-04: RADOS operations/troubleshooting prose is operator reference "
        "only; it does not alter on-disk state, command semantics or the exact "
        "upgrade gate."
    ),
    "release-index": (
        "VAL-DOC-05: release metadata drives documentation navigation, not "
        "package selection or cluster upgrade execution."
    ),
    "general-reference": (
        "VAL-DOC-06: developer/start/architecture/reference prose supplies "
        "context but is non-executable and not selected by Pacific-x; runtime "
        "claims are assessed against source evidence elsewhere."
    ),
}

for row in doc_rows:
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
assert (affect_count, trivial_count, blank_count) == (61, 526, 41)

replace_known(
    md_path,
    "Hiện `affect = 61`, `trivial = 428`, **chưa phân loại = 139**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 61`, `trivial = 526`, **chưa phân loại = 41**; binary gate của owner chưa hoàn tất.",
)

summary = """98 hàng `doc/**` được đọc theo sáu cụm: chín file Sphinx/theme, 10 hướng dẫn integration/teuthology, 24 manpage/index, 19 tài liệu vận hành RADOS, một release index và 35 tài liệu kiến trúc/developer/start khác. Các hunk có tín hiệu nâng cấp thật—quy tắc backward-compatible encoding, thứ tự tìm config của `cephadm shell`, hướng dẫn upgrade testing, health/PG và danh mục Quincy—nhưng đều là nguồn tham chiếu không thực thi, không được Pacific-x compose. Chúng nhận `trivial`; source/tool hoặc suite tương ứng mới là nơi mang tác động, tránh đếm đôi một thay đổi vì cả code lẫn tài liệu.

"""
insert_before_once(md_path, "## Kiểm chứng cần hoàn thành", summary)

replace_known(
    readme_path,
    "1.722 hàng `affect`. 2.318 hàng `trivial`. 139 hàng chưa phân loại.",
    "1.722 hàng `affect`. 2.416 hàng `trivial`. 41 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 139 hàng còn thiếu nhãn và lý do", "vì 41 hàng còn thiếu nhãn và lý do")

replace_known(
    plan_path,
    "`affect 1.722`, `trivial 2.318`, còn **139 hàng chưa phân loại**.",
    "`affect 1.722`, `trivial 2.416`, còn **41 hàng chưa phân loại**.",
)
replace_known(
    plan_path,
    "owner 15 hiện `61 affect`, `428 trivial`, `139` chưa phân loại.",
    "owner 15 hiện `61 affect`, `526 trivial`, `41` chưa phân loại.",
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
    2416,
    41,
)

print("Reviewed owner-15 documentation rows: 0 affect, 98 trivial")
print(
    f"Owner totals: affect={affect_count} trivial={trivial_count} "
    f"unclassified={blank_count}"
)
print(
    f"Suite totals: affect={global_affect} trivial={global_trivial} "
    f"unclassified={global_blank}"
)
