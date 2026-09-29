"""Record screened zoned allocator/freelist/zone-state rows for owner 02."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
review = {
    "src/os/bluestore/ZonedAllocator.cc": ("BLU-012 BLU-013", "Zoned allocator initializes from device zone pointers, counts only sequential free space, skips cleaning zone and scores cleaner candidates; SMR-only path."),
    "src/os/bluestore/ZonedAllocator.h": ("BLU-012 BLU-013", "Zoned allocator interface/state changes for device-pointer startup and cleaning coordination; SMR-only path."),
    "src/os/bluestore/ZonedFreelistManager.cc": ("BLU-012 BLU-013", "Zoned freelist loads changed zone-state encoding and splits cross-zone allocation/release deltas; reset writes full state synchronously."),
    "src/os/bluestore/ZonedFreelistManager.h": ("BLU-012 BLU-013", "Zoned freelist interface adds geometry and explicit zone reset; target reader/initializer use changed state format."),
    "src/os/bluestore/zoned_types.cc": ("BLU-012", "Old packed uint64 zone-state encode/decode is deleted as target moves to two uint64 fields in header."),
    "src/os/bluestore/zoned_types.h": ("BLU-012", "On-disk zone-state encoding changes from packed uint32+uint32 in one uint64 to two separate uint64 values; direct compatibility needs clone test."),
}

with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert sum(row["path"] in review for row in rows) == len(review)
for row in rows:
    if row["path"] in review:
        finding, reason = review[row["path"]]
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding
        row["impact_reason"] = f"{finding}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
