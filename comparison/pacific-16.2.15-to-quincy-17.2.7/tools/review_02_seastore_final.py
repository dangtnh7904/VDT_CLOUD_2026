"""Screen remaining SeaStore cache, placement, replay, and GC source rows."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
clusters = {
    "SEA-010": {
        "src/crimson/os/seastore/cache.cc",
        "src/crimson/os/seastore/cache.h",
        "src/crimson/os/seastore/cached_extent.cc",
        "src/crimson/os/seastore/cached_extent.h",
        "src/crimson/os/seastore/ordering_handle.h",
        "src/crimson/os/seastore/transaction.cc",
        "src/crimson/os/seastore/transaction.h",
    },
    "SEA-011": {
        "src/crimson/os/seastore/extent_placement_manager.cc",
        "src/crimson/os/seastore/extent_placement_manager.h",
        "src/crimson/os/seastore/segment_cleaner.cc",
        "src/crimson/os/seastore/segment_cleaner.h",
    },
    "SEA-012": {
        "src/crimson/os/seastore/extent_reader.cc",
        "src/crimson/os/seastore/extent_reader.h",
    },
}
reasons = {
    "SEA-010": "Cache/transaction/OrderingHandle change read-set, retired extents, conflict retry and ordered journal submission; target TransactionManager and Journal call these paths.",
    "SEA-011": "New ExtentPlacementManager out-of-line writes and changed SegmentCleaner trim/reclaim/space accounting are wired into target TransactionManager.",
    "SEA-012": "New ExtentReader scans and CRC-checks persisted records/extents for Journal replay and SegmentCleaner reclaim.",
}
all_paths = set().union(*clusters.values())
log_path = "src/crimson/os/seastore/logging.h"
assert len(all_paths) == 13
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in all_paths | {log_path}} == all_paths | {log_path}
for row in rows:
    path = row["path"]
    if path in all_paths:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        finding = next(fid for fid, paths in clusters.items() if path in paths)
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding
        row["impact_reason"] = f"{finding}: {reasons[finding]}"
    elif path == log_path:
        assert row["status"] == "A"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T02-SEA-log: new macros route format/debug messages to SeaStore subsystems; no state, wire, storage, gate, or alert contract changed by this header alone."
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
