"""Review the ObjectStore QA recipe split without inferring logical rename."""

import csv
import subprocess
from pathlib import Path


suite = Path(__file__).resolve().parents[1]
repo = suite.parents[1] / "ceph16.2.15" / "ceph"
csv_path = suite / "01-osd-pg-recovery.csv"
prefix = "qa/suites/rados/objectstore/backends/"
filters = {
    prefix + "objectstore-bluestore-a.yaml": "--gtest_filter=*/2:-*SyntheticMatrixC*",
    prefix + "objectstore-bluestore-b.yaml": "--gtest_filter=*SyntheticMatrixC*/2",
    prefix + "objectstore-filestore-memstore.yaml": "--gtest_filter=*/1:*/0",
}

def show(ref, path):
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


assert "--gtest_filter=-*/3" in show("v16.2.15", prefix + "objectstore.yaml")
for name, expected in filters.items():
    target = show("v17.2.7", name)
    assert expected in target and "ceph_test_objectstore" in target, name

with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in filters} == set(filters)

for row in rows:
    if row["path"] not in filters:
        continue
    assert not row["upgrade_impact"], row["path"]
    if row["path"].endswith("objectstore-bluestore-a.yaml"):
        assert row["status"] == "R" and row["old_path"] == prefix + "objectstore.yaml"
    else:
        assert row["status"] == "A" and not row["old_path"]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "OSD-071"
    row["impact_reason"] = (
        "OSD-071/T01-objectstore-split: old -*/3 ObjectStore gtest selection is "
        "split into BlueStore /2 normal and SyntheticMatrixC selections plus "
        "FileStore/MemStore /1,/0; changes QA partition and acceptance/duration. "
        "Git's R067 pairing is heuristic, not proof of a logical rename."
    )

with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Reviewed 3 ObjectStore QA recipe split rows")
