"""Screen SeaStore device backend changes after caller and build review."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
segment = {
    "src/crimson/os/seastore/segment_manager.cc",
    "src/crimson/os/seastore/segment_manager.h",
    "src/crimson/os/seastore/segment_manager/block.cc",
    "src/crimson/os/seastore/segment_manager/block.h",
    "src/crimson/os/seastore/segment_manager/zns.cc",
    "src/crimson/os/seastore/segment_manager/zns.h",
}
ephemeral = {
    "src/crimson/os/seastore/segment_manager/ephemeral.cc",
    "src/crimson/os/seastore/segment_manager/ephemeral.h",
}
rbm = {
    "src/crimson/os/seastore/random_block_manager.h",
    "src/crimson/os/seastore/random_block_manager/nvme_manager.cc",
    "src/crimson/os/seastore/random_block_manager/nvme_manager.h",
    "src/crimson/os/seastore/random_block_manager/nvmedevice.cc",
    "src/crimson/os/seastore/random_block_manager/nvmedevice.h",
}
all_paths = segment | ephemeral | rbm
assert len(all_paths) == 13
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in all_paths} == all_paths
for row in rows:
    path = row["path"]
    if path in segment:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "SEA-006"
        row["impact_reason"] = "SEA-006: target SegmentManager factory selects block or ZNS backend by device and both mount/read/write persisted segments; SeaStore::make_seastore calls factory."
    elif path in ephemeral:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T02-SEA-ephemeral: changed address/device-id and test-device semantics; target production make_seastore selects block/ZNS manager, and create_test_ephemeral callers are test fixtures."
    elif path in rbm:
        assert row["status"] == "A", path
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T02-SEA-rbm: new NVMe random-block manager is compiled and unit tested, but endpoint search finds no production instantiation; only test_randomblock_manager.cc constructs NVMeManager."
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
