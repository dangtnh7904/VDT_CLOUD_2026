"""Record the six screened FileStore and MemStore owner-02 source rows."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
review = {
    "src/os/filestore/CollectionIndex.h": ("trivial", "", "T02-include: removes unused RWLock include; index interface and behavior unchanged."),
    "src/os/filestore/FileStore.cc": ("affect", "BLU-010", "BLU-010: live config changes now set FileStore workqueue timeouts; sync-pause max latency counter correction changes stop/go telemetry."),
    "src/os/filestore/FileStore.h": ("trivial", "", "T02-getattrs-api: transparent std::less<> map signature adaptation; FileStore behavior change separately labeled in .cc."),
    "src/os/filestore/JournalingObjectStore.h": ("trivial", "", "T02-include: removes unused RWLock include; no journal operation change."),
    "src/os/memstore/MemStore.cc": ("affect", "BLU-011", "BLU-011: WITH_SEASTAR MemStore omap_get_values(start_after) implementation affects AlienStore/Crimson test and conditional runtime path."),
    "src/os/memstore/MemStore.h": ("affect", "BLU-011", "BLU-011: used_bytes becomes atomic and WITH_SEASTAR omap overload is declared; conditional MemStore runtime state."),
}

with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert sum(row["path"] in review for row in rows) == len(review)
for row in rows:
    if row["path"] in review:
        verdict, finding, reason = review[row["path"]]
        assert not row["upgrade_impact"] or row["upgrade_impact"] == verdict
        row["upgrade_impact"] = verdict
        row["finding_id"] = finding
        row["impact_reason"] = reason
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
