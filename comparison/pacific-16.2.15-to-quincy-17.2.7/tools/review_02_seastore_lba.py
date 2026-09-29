"""Screen LBA/root migration and dead extent-map manager source."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
lba = {
    r["path"] for r in rows
    if not r["upgrade_impact"]
    and r["path"].startswith("src/crimson/os/seastore/lba_manager/")
}
lba.add("src/crimson/os/seastore/lba_manager.h")
lba.add("src/crimson/os/seastore/root_block.h")
extmap = {
    r["path"] for r in rows
    if not r["upgrade_impact"]
    and r["path"].startswith("src/crimson/os/seastore/extentmap_manager")
}
assert len(lba) == 12, len(lba)
assert len(extmap) == 7, len(extmap)
for row in rows:
    if row["path"] in lba:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "SEA-007"
        row["impact_reason"] = "SEA-007: root_t and LBA B-tree implementation/layout change; TransactionManager mkfs/mount and SeaStore object mapping use these persisted roots/pins."
    elif row["path"] in extmap:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T02-SEA-extmap: old ExtentMapManager tree is removed from target CMake and has no base caller outside its own cluster; remaining factory .cc is also unbuilt."
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
