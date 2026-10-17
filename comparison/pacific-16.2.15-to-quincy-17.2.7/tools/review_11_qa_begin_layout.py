"""Classify owner-11 CephFS QA begin-layout and ignorelist-only deltas."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "11-cephfs-mds.csv"
md_path = root / "11-cephfs-mds.md"
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
        assert text.count(old) == expected
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected


suite_roots = {
    "32bits",
    "bugs/client_trim_caps",
    "full",
    "functional",
    "libcephfs",
    "mirror-ha",
    "mirror",
    "mixed-clients",
    "multiclient",
    "multifs",
    "permission",
    "shell",
    "snaps",
    "thrash/multifs",
    "thrash/workloads",
    "top",
    "traceless",
    "valgrind",
    "verify",
    "volumes",
}
begin_paths = {
    "qa/cephfs/begin/+",
    "qa/cephfs/begin/0-install.yaml",
    "qa/cephfs/begin/1-ceph.yaml",
    "qa/cephfs/begin/2-logrotate.yaml",
}
for suite in suite_roots:
    begin_paths.add(f"qa/suites/fs/{suite}/begin")
    begin_paths.add(f"qa/suites/fs/{suite}/begin.yaml")

ignorelist_paths = {
    "qa/suites/fs/mirror-ha/overrides/ignorelist_health.yaml",
    "qa/suites/fs/mirror-ha/overrides/whitelist_health.yaml",
    "qa/suites/fs/mirror/overrides/ignorelist_health.yaml",
    "qa/suites/fs/mirror/overrides/whitelist_health.yaml",
    "qa/suites/fs/valgrind/mirror/overrides/ignorelist_health.yaml",
    "qa/suites/fs/valgrind/mirror/overrides/whitelist_health.yaml",
}
paths = begin_paths | ignorelist_paths
assert len(begin_paths) == 44
assert len(paths) == 50

# Endpoint evidence is authoritative. Commit history only explains why the
# target layout was introduced.
for commit in ("5d9bfc26537", "438cb17c4a4", "da092a1edac"):
    assert git("merge-base", "--is-ancestor", commit, "v17.2.7", check=False).returncode == 0

touched = set(
    git("diff", "--name-only", "--find-renames", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

old_begin = show("v16.2.15", "qa/cephfs/begin.yaml")
new_install = show("v17.2.7", "qa/cephfs/begin/0-install.yaml")
new_ceph = show("v17.2.7", "qa/cephfs/begin/1-ceph.yaml")
new_logrotate = show("v17.2.7", "qa/cephfs/begin/2-logrotate.yaml")
assert new_install in old_begin
assert "- ceph:" in old_begin and "- ceph:" in new_ceph
assert "create_rbd_pool: false" in new_ceph
assert new_logrotate.strip() in old_begin
for suite in suite_roots:
    target = show("v17.2.7", f"qa/suites/fs/{suite}/begin").strip()
    assert target in {".qa/cephfs/begin/+", ".qa/cephfs/begin/"}, (suite, target)

old_ignore = show("v16.2.15", "qa/suites/fs/mirror/overrides/whitelist_health.yaml")
new_ignore = show("v17.2.7", "qa/suites/fs/mirror/overrides/ignorelist_health.yaml")
assert "FS_DEGRADED" in old_ignore and "MDS_DAMAGE" in old_ignore
assert new_ignore.strip() == "./.qa/cephfs/overrides/ignorelist_health.yaml"

reason = (
    "FS-QA-04: endpoint delta is confined to Teuthology layout: the previous "
    "CephFS begin YAML is split into install, ceph, and logrotate fragments and "
    "the suites point to their concatenation; mirror suites reuse the common "
    "CephFS health ignorelist. Avoiding an unused RBD pool changes only the test "
    "fixture. No shipped MDS/client code, default, protocol, or on-disk format changes."
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

for path in paths:
    row = by_path[path]
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
assert affect_count + trivial_count + blank_count == 427
assert trivial_count >= 53 and blank_count <= 367

if (affect_count, trivial_count, blank_count) == (7, 53, 367):
    replace_known(
        md_path,
        "`affect = 7`, `trivial = 3`, chưa phân loại = 417",
        "`affect = 7`, `trivial = 53`, chưa phân loại = 367",
    )
    replace_known(
        md_path,
        "**3 hàng** đã sàng lọc: 134 chỉ thêm anchor Sphinx trước tiêu đề trong `doc/cephfs/upgrading.rst`, còn nội dung các bước nâng MDS giống hệt hai endpoint; 619 và 622 chỉ đổi câu `print` từ Nautilus sang Octopus trong hai nhánh client, không đổi task thực thi.",
        "**53 hàng** đã sàng lọc: 134 chỉ thêm anchor Sphinx trước tiêu đề trong `doc/cephfs/upgrading.rst`; 619 và 622 chỉ đổi câu `print`; 50 hàng `FS-QA-04` tách cấu hình `begin` thành các fragment tương đương hoặc dùng lại health ignorelist chung, không đổi runtime được phát hành.",
    )
    replace_known(md_path, "Phân loại 417 hàng còn trống", "Phân loại 367 hàng còn trống")
    replace_known(
        readme_path,
        "1.432 hàng `affect`. 1.499 hàng `trivial`. 1.248 hàng chưa phân loại.",
        "1.432 hàng `affect`. 1.549 hàng `trivial`. 1.198 hàng chưa phân loại.",
    )
    replace_known(
        readme_path,
        "vì 1.248 hàng còn thiếu nhãn và lý do",
        "vì 1.198 hàng còn thiếu nhãn và lý do",
    )
    replace_known(
        plan_path,
        "`affect 1.432`, `trivial 1.499`, còn **1.248 hàng chưa phân loại**",
        "`affect 1.432`, `trivial 1.549`, còn **1.198 hàng chưa phân loại**",
    )
    replace_known(
        plan_path,
        "owner 10 đã chốt `58 affect`, `262 trivial`, `0` chưa phân loại; owner 12",
        "owner 10 đã chốt `58 affect`, `262 trivial`, `0` chưa phân loại; owner 11 hiện `7 affect`, `53 trivial`, `367` chưa phân loại; owner 12",
    )

print("Classified owner-11 CephFS QA begin-layout batch: 0 affect, 50 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
