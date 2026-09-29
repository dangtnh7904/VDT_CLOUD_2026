"""Screen SeaStore onode layout, tree integration, and retired test code."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

core = {
    "src/crimson/os/seastore/onode.cc",
    "src/crimson/os/seastore/onode.h",
    "src/crimson/os/seastore/onode_manager.h",
    "src/crimson/os/seastore/onode_manager/staged-fltree/fltree_onode_manager.cc",
    "src/crimson/os/seastore/onode_manager/staged-fltree/fltree_onode_manager.h",
    "src/crimson/os/seastore/onode_manager/staged-fltree/value.cc",
    "src/crimson/os/seastore/onode_manager/staged-fltree/value.h",
}
old_simple = {
    r["path"] for r in rows
    if not r["upgrade_impact"]
    and "/onode_manager/simple-fltree/" in r["path"]
}
stage = {
    r["path"] for r in rows
    if not r["upgrade_impact"]
    and "/onode_manager/staged-fltree/" in r["path"]
} - core
dummy = "src/crimson/os/seastore/onode_manager/staged-fltree/node_extent_manager/dummy.h"
assert len(core) == 7
assert len(old_simple) == 6
assert len(stage) == 35, len(stage)
assert dummy in stage
stage.remove(dummy)
for row in rows:
    path = row["path"]
    if path in core:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "SEA-008"
        row["impact_reason"] = "SEA-008: target Onode layout and FLTreeOnodeManager implement persisted object metadata, OMAP/xattr/data roots and tree operations called by SeaStore."
    elif path in stage:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "SEA-009"
        row["impact_reason"] = "SEA-009: staged FL-tree node/key/value layout, extent access, delta replay and split/merge path now under target runtime FLTreeOnodeManager; old tree source is replaced."
    elif path in old_simple:
        assert row["status"] == "D", path
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T02-SEA-old-onode: removed simple-fltree implementation was compiled in base but no production OnodeManager instantiated it; base create_ephemeral returned null, target uses staged FLTree."
    elif path == dummy:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T02-SEA-dummy: DummyNodeExtentManager changes test-only in-memory extent behavior; target production FLTree uses create_seastore, not create_dummy."
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
