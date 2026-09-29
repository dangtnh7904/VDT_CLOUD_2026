"""Record new, directly called SeaStore manager implementations."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
clusters = {
    "SEA-003": {
        "src/crimson/os/seastore/omap_manager.cc",
        "src/crimson/os/seastore/omap_manager.h",
        "src/crimson/os/seastore/omap_manager/btree/btree_omap_manager.cc",
        "src/crimson/os/seastore/omap_manager/btree/btree_omap_manager.h",
        "src/crimson/os/seastore/omap_manager/btree/omap_btree_node.h",
        "src/crimson/os/seastore/omap_manager/btree/omap_btree_node_impl.cc",
        "src/crimson/os/seastore/omap_manager/btree/omap_btree_node_impl.h",
        "src/crimson/os/seastore/omap_manager/btree/omap_types.h",
        "src/crimson/os/seastore/omap_manager/btree/string_kv_node_layout.h",
    },
    "SEA-004": {
        "src/crimson/os/seastore/collection_manager.cc",
        "src/crimson/os/seastore/collection_manager.h",
        "src/crimson/os/seastore/collection_manager/collection_flat_node.cc",
        "src/crimson/os/seastore/collection_manager/collection_flat_node.h",
        "src/crimson/os/seastore/collection_manager/flat_collection_manager.cc",
        "src/crimson/os/seastore/collection_manager/flat_collection_manager.h",
    },
    "SEA-005": {
        "src/crimson/os/seastore/object_data_handler.cc",
        "src/crimson/os/seastore/object_data_handler.h",
    },
}
reasons = {
    "SEA-003": "New OMapManager/BtreeOMapManager and string-key node layout implement SeaStore OMAP/xattr get/set/list/clear called from SeaStore; persisted tree path.",
    "SEA-004": "New CollectionManager/FlatCollectionManager and flat-node layout implement SeaStore collection root/create/list/remove called by SeaStore mkfs and operations.",
    "SEA-005": "New ObjectDataHandler read/write/overwrite/truncate path is called by SeaStore object operations; changes object data persistence.",
}
all_paths = set().union(*clusters.values())
assert len(all_paths) == 17
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in all_paths} == all_paths
for row in rows:
    if row["path"] in all_paths:
        assert row["status"] == "A", row["path"]
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        finding = next(fid for fid, paths in clusters.items() if row["path"] in paths)
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding
        row["impact_reason"] = f"{finding}: {reasons[finding]}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
