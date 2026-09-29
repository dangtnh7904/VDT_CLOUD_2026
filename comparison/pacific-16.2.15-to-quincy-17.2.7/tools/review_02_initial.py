"""Promote inspected BlueStore/BlueFS upgrade paths to owner-02 findings."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
review = {
    "src/os/bluestore/BlueStore.cc": ("BLU-001", "BLU-001: default-enabled allocation-file/null-FM path changes OSD mount, crash recovery, destage, and repair behavior on eligible DB media."),
    "src/os/bluestore/BlueStore.h": ("BLU-001 BLU-004", "BLU-001/004: declares allocation-file restore/reconstruct/invalidate methods and recovery-tool hooks used by changed mount path."),
    "src/os/bluestore/BlueFS.cc": ("BLU-002 BLU-003", "BLU-002/003: truncate marks metadata dirty before fsync; allocation unit and IOContext drain/read metrics change BlueFS startup and stabilization."),
    "src/os/bluestore/BlueFS.h": ("BLU-001 BLU-003", "BLU-001/003: exposes DB rotational check used by allocation-file gate and adds BlueFS read/write counters used for validation."),
    "src/os/bluestore/FreelistManager.cc": ("BLU-001", "BLU-001: factory creates null freelist manager to avoid per-allocation RocksDB writes."),
    "src/os/bluestore/FreelistManager.h": ("BLU-001", "BLU-001: freelist interface tracks null-manager state and allocation representation."),
    "src/os/bluestore/BitmapFreelistManager.cc": ("BLU-001", "BLU-001: allocate/release skip RocksDB bitmap XOR when null-manager mode is active."),
    "src/os/bluestore/BitmapFreelistManager.h": ("BLU-001", "BLU-001: bitmap freelist interface changes to support null-manager path."),
    "src/os/bluestore/bluestore_tool.cc": ("BLU-004", "BLU-004: offline recovery tool adds allocmap/qfsck/restore_cfb and -i, changes init and DB/WAL attach path."),
}
csv_path = root / "02-bluestore-bluefs.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert sum(row["path"] in review for row in rows) == len(review)
for row in rows:
    if row["path"] in review:
        ids, reason = review[row["path"]]
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        row["upgrade_impact"] = "affect"
        row["finding_id"] = ids
        row["impact_reason"] = reason
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
