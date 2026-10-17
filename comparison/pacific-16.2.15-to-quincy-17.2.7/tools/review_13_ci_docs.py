"""Classify owner-13 CI, documentation-build, and repository-support files."""

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


paths = {
    ".github/dependabot.yml",
    ".github/labeler.yml",
    ".github/workflows/pr-check-deps.yml",
    ".github/workflows/pr-checklist.yml",
    ".gitignore",
    "admin/build-doc",
    "admin/doc-requirements.txt",
    "debian/changelog",
    "man/ceph_selinux.8",
    "mirroring/MIRRORS",
    "mirroring/mirror-ceph.sh",
    "src/mypy-constrains.txt",
    "src/mypy.ini",
}
assert len(paths) == 13
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# Endpoint guards establish that these files drive GitHub/repository hygiene,
# docs/static-analysis builds, release metadata, or mirror administration—not
# installed Ceph daemon/client payloads.
assert 'package-ecosystem: "npm"' in show("v17.2.7", ".github/dependabot.yml")
assert "on: [pull_request_target]" in show("v17.2.7", ".github/workflows/pr-check-deps.yml")
assert "pull_request:" in show("v17.2.7", ".github/workflows/pr-checklist.yml")
assert "/src/python-common/build/" in show("v16.2.15", ".gitignore")
assert ".cache" in show("v17.2.7", ".gitignore")
target_build_doc = show("v17.2.7", "admin/build-doc")
assert "sphinx-build" in target_build_doc and "BUILD_DOC=1" in target_build_doc
assert "ceph (16.2.15-1) stable" in show("v16.2.15", "debian/changelog")
assert "ceph (17.2.7-1) stable" in show("v17.2.7", "debian/changelog")
assert "sepecify alternate labeling" in show("v16.2.15", "man/ceph_selinux.8")
assert "specify alternate labeling" in show("v17.2.7", "man/ceph_selinux.8")
assert "ca.ceph.com" in show("v17.2.7", "mirroring/MIRRORS")
assert 'SOURCES[ca]="ca.ceph.com"' in show("v17.2.7", "mirroring/mirror-ceph.sh")
assert "mypy==0.901" in show("v17.2.7", "src/mypy-constrains.txt")
assert "disallow_untyped_defs = True" in show("v17.2.7", "src/mypy.ini")

reason = (
    "PKG-CI-01: endpoint hunk is limited to GitHub PR automation/labels, ignored developer cache, "
    "documentation or mypy tooling, release-changelog/man-page text, or administration of the "
    "public source-package mirror. It is not installed as a Ceph daemon/client payload and has no "
    "mixed-version protocol, state-migration, activation, or rollback path."
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
assert (affect_count, trivial_count, blank_count) == (11, 39, 157)

replace_known(
    md_path,
    "Hiện `affect = 11`, `trivial = 26`, **chưa phân loại = 170**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 11`, `trivial = 39`, **chưa phân loại = 157**; binary gate của owner chưa hoàn tất.",
)
replace_known(
    md_path,
    "26 hàng đã được đọc theo endpoint. Ngoài 19 hàng `PKG-DOC-01`, bảy hàng `PKG-MAN-01` chỉ đổi man page/additive CLI, comment/indent, test benchmark hoặc cú pháp manifest tương đương; deletion `debian/libjaeger.install` chỉ bỏ ba dòng comment và không từng cài artifact. Những thay đổi package có đường delivery/runtime thực được giữ `affect` ở PKG-001–003, FS-007 hoặc cross-reference liên quan.",
    "39 hàng đã được đọc theo endpoint. Ngoài 19 hàng `PKG-DOC-01` và bảy hàng `PKG-MAN-01`, 13 hàng `PKG-CI-01` chỉ điều khiển GitHub PR/label, cache developer, build tài liệu/mypy, changelog/man text hoặc danh sách mirror source. Chúng không được cài làm payload daemon/client. Những thay đổi package có đường delivery/runtime thực được giữ `affect` ở PKG-001–003, FS-007 hoặc cross-reference liên quan.",
)
replace_known(
    readme_path,
    "1.520 hàng `affect`. 1.861 hàng `trivial`. 798 hàng chưa phân loại.",
    "1.520 hàng `affect`. 1.874 hàng `trivial`. 785 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 798 hàng còn thiếu nhãn và lý do", "vì 785 hàng còn thiếu nhãn và lý do")
replace_known(
    plan_path,
    "`affect 1.520`, `trivial 1.861`, còn **798 hàng chưa phân loại**",
    "`affect 1.520`, `trivial 1.874`, còn **785 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 13 hiện `11 affect`, `26 trivial`, `170` chưa phân loại.",
    "owner 13 hiện `11 affect`, `39 trivial`, `157` chưa phân loại.",
)

print("Classified owner-13 CI/docs/repository-support batch: 13 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
