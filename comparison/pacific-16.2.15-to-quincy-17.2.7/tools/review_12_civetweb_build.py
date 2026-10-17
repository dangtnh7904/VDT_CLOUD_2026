"""Cross-reference Civetweb build removal on the already affecting RGW CMake row."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "13-build-packaging-submodules.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

matches = [row for row in rows if row["path"] == "src/rgw/CMakeLists.txt"]
assert len(matches) == 1
row = matches[0]
assert row["upgrade_impact"] == "affect" and row["finding_id"] == "RGW-002"
assert "RGW-004" not in row["impact_reason"]
row["impact_reason"] += " RGW-004: Same file drops Civetweb source objects, generated header, and library dependency from RGW build."

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Linked RGW build row to RGW-004")
