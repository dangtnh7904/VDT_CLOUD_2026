"""Classify inspected FastCGI build removal and supporting doc rows."""

import csv
from pathlib import Path


root = Path(__file__).resolve().parents[1]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        return reader.fieldnames, list(reader)


def write(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


build = root / "13-build-packaging-submodules.csv"
fields, rows = read(build)
assert fields is not None
changes = {
    "CMakeLists.txt": "CFG-008: Target removes WITH_RADOSGW_FCGI_FRONTEND CMake option and find_package(fcgi), so a custom FastCGI build is no longer available.",
    "cmake/modules/Findfcgi.cmake": "CFG-008: Deletes the FastCGI dependency finder used by Pacific's optional RGW FastCGI build path.",
}
for source, reason in changes.items():
    matches = [row for row in rows if row["path"] == source]
    assert len(matches) == 1, source
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "CFG-008"
    row["impact_reason"] = reason
matches = [row for row in rows if row["path"] == "src/rgw/CMakeLists.txt"]
assert len(matches) == 1
row = matches[0]
assert row["upgrade_impact"] == "affect" and row["finding_id"] == "RGW-002"
assert "CFG-008" not in row["impact_reason"]
row["impact_reason"] += " CFG-008: Same file removes FastCGI source lists and FCGI_LIBRARY links from RGW targets."
write(build, fields, rows)

rgw = root / "12-rgw.csv"
fields, rows = read(rgw)
assert fields is not None
matches = [row for row in rows if row["path"] == "doc/start/rgw.conf"]
assert len(matches) == 1
row = matches[0]
assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
row["upgrade_impact"] = "trivial"
row["finding_id"] = "CFG-008"
row["impact_reason"] = "CFG-008 support: Deleted Apache FastCGI example follows removal of runtime/build frontend; example itself is not an executed upgrade recipe or independent acceptance gate."
write(rgw, fields, rows)

print("Classified 2 build rows as affect, 1 FastCGI example as trivial; linked RGW build row")
