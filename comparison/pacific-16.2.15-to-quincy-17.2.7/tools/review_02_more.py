"""Record additional reviewed fsck and onode-format findings for owner 02."""

import csv
from pathlib import Path

csv_path = Path(__file__).resolve().parents[1] / "02-bluestore-bluefs.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
for path in ("src/os/bluestore/BlueStore.cc", "src/os/bluestore/BlueStore.h"):
    row = by_path[path]
    assert row["upgrade_impact"] == "affect"
    if "BLU-005" not in row["finding_id"]:
        row["finding_id"] += " BLU-005 BLU-006"
        row["impact_reason"] += " BLU-005/006: fsck statfs/zone-ref checks and onode format handling alter repair/validation and rollback review."
row = by_path["src/os/bluestore/bluestore_types.h"]
assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
row["upgrade_impact"] = "affect"
row["finding_id"] = "BLU-006"
row["impact_reason"] = "BLU-006: onode DENC version rises 1→2 with zone_offset_refs (compat 1), and clear_omap_flag clears all OMAP subtype flags."
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
