"""Classify inspected RGW Admin /info endpoint and its QA/docs evidence."""

import csv
from pathlib import Path


root = Path(__file__).resolve().parents[1]
owner = root / "12-rgw.csv"
reasons = {
    "src/rgw/rgw_rest_info.cc": "RGW-005: New Admin GET /info operation returns storage backend name and cluster_id after info=read cap check.",
    "src/rgw/rgw_rest_info.h": "RGW-005: New S3-authenticated Admin /info handler dispatches GET and reads no bucket permissions.",
    "qa/tasks/radosgw_admin_rest.py": "RGW-005: QA adds /info GET with info=read and asserts info.storage_backends[0] name/cluster_id; same row has separate rate-limit tests needing review.",
    "doc/radosgw/adminops.rst": "RGW-005: Documents new /info Admin API and info=read cap, though documented cluster_id nesting differs from target code/QA; same row has separate rate-limit docs needing review.",
}

with owner.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for source, reason in reasons.items():
    matches = [row for row in rows if row["path"] == source]
    assert len(matches) == 1, source
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "RGW-005"
    row["impact_reason"] = reason

main = [row for row in rows if row["path"] == "src/rgw/rgw_main.cc"]
assert len(main) == 1 and main[0]["upgrade_impact"] == "affect"
assert "RGW-005:" not in main[0]["impact_reason"]
main[0]["impact_reason"] += " RGW-005: Registers /info beneath the configured Admin URL when admin API is enabled."

with owner.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

build = root / "13-build-packaging-submodules.csv"
with build.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    build_fields = reader.fieldnames
    build_rows = list(reader)
assert build_fields is not None
cmake = [row for row in build_rows if row["path"] == "src/rgw/CMakeLists.txt"]
assert len(cmake) == 1 and cmake[0]["upgrade_impact"] == "affect"
assert "RGW-005:" not in cmake[0]["impact_reason"]
cmake[0]["impact_reason"] += " RGW-005: Target adds rgw_rest_info.cc to RGW build for the new Admin /info endpoint."
with build.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=build_fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(build_rows)

print(f"Classified {len(reasons)} Admin /info rows and updated RGW/build cross-evidence")
