"""Screen SeaStore unit-test source rows after hunk and commit review."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
review = {
    "src/test/crimson/seastore/nvmedevice/test_nvmedevice.cc": "T02-SEA-nvme: adds write/verify unit case for new NVMe device backend; production path lives in random_block_manager sources.",
    "src/test/crimson/seastore/onode_tree/test_fltree_onode_manager.cc": "T02-SEA-onode: adds fltree onode manager unit cases; no deployed OSD or upgrade gate change.",
    "src/test/crimson/seastore/onode_tree/test_node.cc": "T02-SEA-onode: deletes old onode node unit source as staged fltree tests replace it; no deployed path in this row.",
    "src/test/crimson/seastore/onode_tree/test_staged_fltree.cc": "T02-SEA-onode: replaces/extends staged fltree insert, erase, split and replay unit cases supporting SeaStore source review.",
    "src/test/crimson/seastore/onode_tree/test_value.h": "T02-SEA-onode: new value test fixture for staged fltree unit cases; not a persisted onode schema definition.",
    "src/test/crimson/seastore/test_block.cc": "T02-SEA-block: test block helper adapts to changed SeaStore address/device types.",
    "src/test/crimson/seastore/test_block.h": "T02-SEA-block: test block helper declaration adapts to changed SeaStore address/device types.",
    "src/test/crimson/seastore/test_btree_lba_manager.cc": "T02-SEA-lba: new/changed LBA btree split/merge cases and fixture setup; runtime implementation is in lba_manager source.",
    "src/test/crimson/seastore/test_collection_manager.cc": "T02-SEA-coll: adds collection manager basic/overflow/update unit cases for new manager implementation.",
    "src/test/crimson/seastore/test_extmap_manager.cc": "T02-SEA-extmap: deletes old extent-map manager unit source with old manager; production removal must be reviewed in source rows.",
    "src/test/crimson/seastore/test_object_data_handler.cc": "T02-SEA-data: adds object data handler write/overwrite/truncate unit cases; no test filter or deployment script change.",
    "src/test/crimson/seastore/test_omap_manager.cc": "T02-SEA-omap: adds OMAP split/merge/list/replay unit cases supporting new SeaStore OMAP manager.",
    "src/test/crimson/seastore/test_randomblock_manager.cc": "T02-SEA-rbm: adds RBM mkfs/open/alloc/free unit cases; no deployment path in this test source.",
    "src/test/crimson/seastore/test_seastore.cc": "T02-SEA-store: adds SeaStore collection/object/OMAP integration tests for SEA-001; no automatic upgrade acceptance policy is defined here.",
    "src/test/crimson/seastore/test_seastore_cache.cc": "T02-SEA-cache: updates cache fixture and assertions for changed SeaStore extent/cache implementation.",
    "src/test/crimson/seastore/test_seastore_journal.cc": "T02-SEA-journal: updates journal fixture and replay cases for SEA-002; test source does not change deployed journal.",
    "src/test/crimson/seastore/test_transaction_manager.cc": "T02-SEA-tm: adds conflict/concurrent write transaction-manager unit cases for SEA-002; no deployment or acceptance script change.",
    "src/test/crimson/seastore/transaction_manager_test_state.h": "T02-SEA-tm: updates transaction manager test state/mock MDStore and ephemeral device fixture; production state reviewed in source.",
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
