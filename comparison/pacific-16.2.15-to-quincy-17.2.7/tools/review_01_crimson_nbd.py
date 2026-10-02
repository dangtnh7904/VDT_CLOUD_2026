"""Exclude the standalone Crimson NBD profiling tool after checking its scope."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
selected = {
    "src/crimson/tools/store-nbd.cc",
    "src/crimson/tools/store_nbd/block_driver.cc",
    "src/crimson/tools/store_nbd/block_driver.h",
    "src/crimson/tools/store_nbd/fs_driver.cc",
    "src/crimson/tools/store_nbd/fs_driver.h",
    "src/crimson/tools/store_nbd/store-nbd.cc",
    "src/crimson/tools/store_nbd/tm_driver.cc",
    "src/crimson/tools/store_nbd/tm_driver.h",
}
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    if row["path"] in selected:
        assert not row["upgrade_impact"], row["path"]
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = (
            "T01-crimson-nbd: endpoint restructures the separate crimson-store-nbd "
            "executable into block/FS/TM drivers for NBD+fio profiling; "
            "doc/dev/crimson/crimson.rst and tools/CMakeLists.txt show this is a "
            "standalone benchmark path, not an OSD daemon or selected upgrade/repair gate."
        )
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
