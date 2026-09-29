"""Record screened non-upgrade objectstore test changes in owner 02."""

import csv
from pathlib import Path

csv_path = Path(__file__).resolve().parents[1] / "02-bluestore-bluefs.csv"
review = {
    "src/test/filestore/TestFileStore.cc": "T02-test-api: argv_to_vec signature/std qualifier adaptation; test harness only.",
    "src/test/objectstore/Allocator_bench.cc": "T02-test-allocator: benchmark adds btree case and clears temporary list; corroborates allocator code, not an executed upgrade path.",
    "src/test/objectstore/Allocator_test.cc": "T02-test-allocator: adjusts create signature and assertion in allocator unit test; not a deployment/acceptance script.",
    "src/test/objectstore/DeterministicOpSequence.cc": "T02-test-api: std namespace declaration in test harness only.",
    "src/test/objectstore/DeterministicOpSequence.h": "T02-test-api: std::map/std::string type qualification in test header only.",
    "src/test/objectstore/ObjectStoreTransactionBenchmark.cc": "T02-test-api: argv_to_vec signature adaptation in benchmark main only.",
    "src/test/objectstore/TestObjectStoreState.cc": "T02-test-api: std namespace declaration in test harness only.",
    "src/test/objectstore/TestObjectStoreState.h": "T02-test-api: std::map/std::vector qualification in test header only.",
    "src/test/objectstore/test_bdev.cc": "T02-test-api: argv_to_vec signature adaptation in block-device test main only.",
    "src/test/objectstore/test_deferred.cc": "T02-test-api: test harness ObjectStore pointer and argv adaptation; deferred-write runtime behavior is reviewed from source rows.",
    "src/test/objectstore/test_idempotent.cc": "T02-test-api: argv_to_vec signature/std qualifier adaptation in idempotence test main only.",
    "src/test/objectstore/test_idempotent_sequence.cc": "T02-test-api: argv_to_vec signature adaptation in test main only.",
    "src/test/objectstore/test_kv.cc": "T02-test-backend: LevelDB test case removed with backend (KV-001); test file itself changes no deployed KV behavior.",
    "src/test/objectstore/test_memstore_clone.cc": "T02-test-api: argv_to_vec signature/std qualifier adaptation in memstore clone test main only.",
    "src/test/objectstore/test_transaction.cc": "T02-test-api: std namespace declaration in test harness only.",
    "src/test/os/TestLFNIndex.cc": "T02-test-api: argv_to_vec signature/std qualifier adaptation in FileStore index test main only.",
}
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert sum(row["path"] in review for row in rows) == len(review)
for row in rows:
    if row["path"] in review:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = review[row["path"]]
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
