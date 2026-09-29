"""Record screened allocator, BlueFS metadata, and test rows for owner 02."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
review = {
    "src/os/bluestore/Allocator.cc": ("affect", "BLU-007", "BLU-007: factory accepts btree, forwards SMR zone geometry, and is called by BlueStore/BlueFS allocation setup."),
    "src/os/bluestore/Allocator.h": ("affect", "BLU-007", "BLU-007: allocator factory signature adds zone geometry and removes generic zoned state methods; caller path reviewed."),
    "src/os/bluestore/AvlAllocator.cc": ("affect", "BLU-007", "BLU-007: free-range candidate offset is rounded to requested alignment before capacity check; hybrid derives from AVL."),
    "src/os/bluestore/BtreeAllocator.cc": ("affect", "BLU-007", "BLU-007: new selectable btree free-range allocator implements aligned first/best fit and recovery initialization."),
    "src/os/bluestore/BtreeAllocator.h": ("affect", "BLU-007", "BLU-007: btree allocator state and interface; instantiated by Allocator::create when configured."),
    "src/os/bluestore/StupidAllocator.cc": ("affect", "BLU-007", "BLU-007: allocation checks effective aligned extent length and adjusts chosen offset; conditional on stupid allocator."),
    "src/os/bluestore/StupidAllocator.h": ("affect", "BLU-007", "BLU-007: declares aligned-length helper used in changed allocation search."),
    "src/os/bluestore/BlueRocksEnv.cc": ("affect", "BLU-008", "BLU-008: RocksDB reuse/delete/rename now synchronously flushes BlueFS metadata through sync_metadata(false)."),
    "src/os/bluestore/AvlAllocator.h": ("trivial", "", "T02-allocator-api: constructor parameter becomes string_view; allocation behavior resides in AvlAllocator.cc."),
    "src/os/bluestore/HybridAllocator.cc": ("trivial", "", "T02-log: only changes spacing in an unexpected-extent diagnostic; no allocation path change in this file."),
    "src/os/bluestore/HybridAllocator.h": ("trivial", "", "T02-allocator-api: constructor name parameter becomes string_view and still delegates to AVL."),
    "src/os/bluestore/BitmapAllocator.cc": ("trivial", "", "T02-allocator-api: constructor name parameter becomes string_view; no bitmap allocation logic change."),
    "src/os/bluestore/BitmapAllocator.h": ("trivial", "", "T02-allocator-api: constructor declaration adapts to string_view only."),
    "src/test/objectstore/test_bluefs.cc": ("trivial", "", "T02-BlueFS-tests: adds compaction/replay, concurrent link/compaction, truncate/fsync and unlink/fsync cases supporting BLU-002/008; test binary is not a deployed OSD or suite gate."),
    "src/test/objectstore/test_bluestore_types.cc": ("trivial", "", "T02-types-tests: adds SimpleBitmap boundary/randomized cases and adjusts test constructors/argv; production behavior reviewed in source rows."),
    "src/test/objectstore/fastbmap_allocator_test.cc": ("trivial", "", "T02-fastbmap-test: expected aligned offsets and free-bin assertions change in unit test; no deployed source change in this row."),
    "src/test/objectstore/allocator_replay_test.cc": ("affect", "BLU-009", "BLU-009: diagnostic replay tool changes accepted allocator dump keys and adds try_alloc action; affects opt-in allocator validation workflow."),
    "src/test/objectstore/run_smr_bluestore_test.sh": ("affect", "BLU-009", "BLU-009: new opt-in SMR validation runner provisions zbc device and invokes objectstore test with gtest_filter=*/2."),
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
