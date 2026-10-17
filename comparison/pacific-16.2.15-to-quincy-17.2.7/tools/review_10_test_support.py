"""Classify remaining owner-10 src/test regression-support deltas."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "10-rados-rbd-clients.csv"
md_path = root / "10-rados-rbd-clients.md"
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


def exists(tag: str, path: str) -> bool:
    return git("cat-file", "-e", f"{tag}:{path}", check=False).returncode == 0


def replace_known(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old in text:
        assert text.count(old) == expected
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected


with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

reason = (
    "RADOS-TEST-36: direct endpoint delta is confined to a C++/Python/cram "
    "test, test fixture, mock or stub under src/test. It adds, removes or "
    "adapts regression coverage and expected output for production changes "
    "documented elsewhere, but this row is not an installed client/daemon "
    "runtime, wire contract, persistent format or operational default."
)

test_rows = [
    row for row in rows
    if row["path"].startswith("src/test/")
    and (not row["upgrade_impact"] or row["impact_reason"] == reason)
]
paths = {row["path"] for row in test_rows}
assert len(paths) == len(test_rows) == 69

# Prove these are actual endpoint deltas and inspect their object presence in
# both tags. The verdict is about the row's contents (test/cram/mock/fixture),
# not merely the amount of churn or its filename extension.
touched = set(git("diff", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths)).stdout.splitlines())
assert touched == paths
for row in test_rows:
    path = row["path"]
    status = row["status"]
    if status == "A":
        assert not exists("v16.2.15", path) and exists("v17.2.7", path)
    elif status == "D":
        assert exists("v16.2.15", path) and not exists("v17.2.7", path)
    else:
        assert exists("v16.2.15", path) and exists("v17.2.7", path)

for row in test_rows:
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
totals = (affect_count, trivial_count, blank_count)
assert totals in {(48, 257, 15), (58, 262, 0)}

# Synchronize the stage counts only during the first pass. A later final-QA
# batch may already have closed the owner; in that state this script verifies
# its 69 rows without rolling the report totals backward.
if totals == (48, 257, 15):
    replace_known(md_path, "`affect = 48`, `trivial = 188`, **chưa phân loại = 84**",
                  "`affect = 48`, `trivial = 257`, **chưa phân loại = 15**")
    replace_known(md_path, "188 hàng đã sàng lọc", "257 hàng đã sàng lọc")
    replace_known(md_path, "binary gate cho 84 hàng chưa phân loại",
                  "binary gate cho 15 hàng chưa phân loại")
    replace_known(
        readme_path,
        "1.422 hàng `affect`. 1.425 hàng `trivial`. 1.332 hàng chưa phân loại.",
        "1.422 hàng `affect`. 1.494 hàng `trivial`. 1.263 hàng chưa phân loại.",
    )
    replace_known(readme_path, "vì 1.332 hàng còn thiếu nhãn và lý do",
                  "vì 1.263 hàng còn thiếu nhãn và lý do")
    replace_known(
        plan_path,
        "`affect 1.422`, `trivial 1.425`, còn **1.332 hàng chưa phân loại**",
        "`affect 1.422`, `trivial 1.494`, còn **1.263 hàng chưa phân loại**",
    )
    replace_known(
        plan_path,
        "owner 10 hiện `48 affect`, `188 trivial`, `84` chưa phân loại",
        "owner 10 hiện `48 affect`, `257 trivial`, `15` chưa phân loại",
    )

print("Classified owner-10 src/test support batch: 0 affect, 69 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
