"""Classify the pure documentation and community-metadata batch in owner 13."""

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


paths = {
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".githubmap",
    ".mailmap",
    ".organizationmap",
    ".peoplemap",
    "COPYING",
    "CodingStyle",
    "README.md",
    "doc/install/build-ceph.rst",
    "doc/install/containers.rst",
    "doc/install/get-packages.rst",
    "doc/install/index.rst",
    "doc/install/index_manual.rst",
    "doc/install/install-storage-cluster.rst",
    "doc/install/manual-deployment.rst",
    "doc/install/manual-freebsd-deployment.rst",
    "doc/install/windows-troubleshooting.rst",
    "doc/man/8/CMakeLists.txt",
}
assert len(paths) == 19

touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# Endpoint guards: this batch changes contributor attribution/process and
# human-facing installation/build guidance. The sole CMake file only selects
# generated man pages; it does not build or activate a daemon/library.
base_readme = show("v16.2.15", "README.md")
target_readme = show("v17.2.7", "README.md")
assert "make [target name]" in base_readme
assert "ninja [target name]" in target_readme
base_install = show("v16.2.15", "doc/install/get-packages.rst")
target_install = show("v17.2.7", "doc/install/get-packages.rst")
assert "epel-release-latest-7" in base_install
assert "epel-release-latest-8" in target_install
base_man_cmake = show("v16.2.15", "doc/man/8/CMakeLists.txt")
target_man_cmake = show("v17.2.7", "doc/man/8/CMakeLists.txt")
assert "ceph-deploy.rst" in base_man_cmake
assert "ceph-deploy.rst" not in target_man_cmake
assert "cephfs-shell.rst" in target_man_cmake
assert "add_executable(" not in target_man_cmake
for path in (
    ".github/CODEOWNERS",
    ".githubmap",
    ".mailmap",
    ".organizationmap",
    ".peoplemap",
):
    assert show("v16.2.15", path) != show("v17.2.7", path)

reason = (
    "PKG-DOC-01: endpoint hunks update contributor ownership/identity, contribution text, "
    "license attribution, and human-facing build/install/troubleshooting guidance. The man-page "
    "CMake hunk only changes which RST manuals are generated. None is executed by package "
    "activation, daemon restart, mixed-version negotiation, state migration, or rollback."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)
for path in paths:
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
assert (affect_count, trivial_count, blank_count) == (4, 19, 184)

replace_known(
    md_path,
    "Hiện `affect = 4`, `trivial = 0`, **chưa phân loại = 203**; các số 0 không phải kết luận không có tác động.",
    "Hiện `affect = 4`, `trivial = 19`, **chưa phân loại = 184**; binary gate của owner chưa hoàn tất.",
)
trivial_md = """## Thay đổi trivial

19 hàng `PKG-DOC-01` đã được đọc theo endpoint: contributor ownership/identity, PR template, license/style và tài liệu build/install/troubleshooting chỉ đổi metadata hoặc hướng dẫn cho con người. `doc/man/8/CMakeLists.txt` chỉ đổi tập RST được sinh thành man page, không build/activate daemon hay thư viện. Các hunk packaging, dependency và CI còn lại chưa được suy thành `trivial` từ đường dẫn.

"""
insert_before_once(md_path, "## Kiểm chứng cần hoàn thành", trivial_md)

replace_known(
    readme_path,
    "1.513 hàng `affect`. 1.835 hàng `trivial`. 831 hàng chưa phân loại.",
    "1.513 hàng `affect`. 1.854 hàng `trivial`. 812 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 831 hàng còn thiếu nhãn và lý do", "vì 812 hàng còn thiếu nhãn và lý do")
replace_known(
    plan_path,
    "`affect 1.513`, `trivial 1.835`, còn **831 hàng chưa phân loại**",
    "`affect 1.513`, `trivial 1.854`, còn **812 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 12 đã chốt `244 affect`, `302 trivial`, `0` chưa phân loại.",
    "owner 12 đã chốt `244 affect`, `302 trivial`, `0` chưa phân loại; owner 13 hiện `4 affect`, `19 trivial`, `184` chưa phân loại.",
)

print("Classified owner-13 documentation/community batch: 19 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
