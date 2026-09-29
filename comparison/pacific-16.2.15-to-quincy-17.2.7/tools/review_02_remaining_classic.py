"""Screen remaining non-Crimson owner-02 source and objectstore test rows."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
review = {
    "src/os/bluestore/bluestore_common.h": ("trivial", "", "T02-mode: Git mode changes 100755 to 100644 on source header; blob contents identical and header is not executed."),
    "src/os/bluestore/fastbmap_allocator_impl.cc": ("affect", "BLU-007", "BLU-007: target rounds bitmap candidate offset to allocation unit; base-only Pacific commit 511e7388687 removed this alignment."),
    "src/os/bluestore/simple_bitmap.cc": ("affect", "BLU-001", "BLU-001: new SimpleBitmap bit/extent operations are called by BlueStore allocation reconstruction from onodes."),
    "src/os/bluestore/simple_bitmap.h": ("affect", "BLU-001", "BLU-001: new SimpleBitmap contract/state for BlueStore reconstruction and allocator restore."),
    "src/test/objectstore/Allocator_aging_fragmentation.cc": ("trivial", "", "T02-allocator-test: test fixture context lifecycle and new btree parameter; no deployment or acceptance script change."),
    "src/test/objectstore/FileStoreDiff.cc": ("trivial", "", "T02-test-api: transparent comparator and std namespace adaptation in FileStore diff helper."),
    "src/test/objectstore/FileStoreDiff.h": ("trivial", "", "T02-test-api: transparent comparator declaration adaptation in test helper."),
    "src/test/objectstore/FileStoreTracker.cc": ("trivial", "", "T02-test-api: adds std namespace declaration in test tracker only."),
    "src/test/objectstore/FileStoreTracker.h": ("trivial", "", "T02-test-api: qualifies list/string/pair with std in test tracker only."),
    "src/test/objectstore/chain_xattr.cc": ("trivial", "", "T02-test-api: std namespace, argv_to_vec and nullptr adaptation in xattr test main."),
    "src/test/objectstore/store_test.cc": ("affect", "BLU-009", "BLU-009: --smr changes test selection, skips several cases and adds FixSMRWritePointer; acceptance coverage differs conditionally."),
    "src/test/objectstore/store_test_fixture.cc": ("trivial", "", "T02-test-fixture: unique_ptr ObjectStore creation and teardown ordering in fixture; no production backend or gate selection change."),
    "src/test/objectstore/store_test_fixture.h": ("trivial", "", "T02-test-fixture: boost scoped_ptr becomes std::unique_ptr in test fixture only."),
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
