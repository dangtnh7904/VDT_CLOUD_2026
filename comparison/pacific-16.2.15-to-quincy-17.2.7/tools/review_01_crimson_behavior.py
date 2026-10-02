"""Record reviewed CyanStore and Crimson OSD state/context behavior."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/crimson/os/cyanstore/cyan_object.h": (
        "OSD-032", "CyanStore xattr values switch from bufferptr to bufferlist, matching the changed get/set path."
    ),
    "src/crimson/os/cyanstore/cyan_store.cc": (
        "OSD-032", "CyanStore handles SETATTRS and RMATTRS, accepts SETALLOCHINT, overwrites existing omap keys and returns typed mount/mkfs errors."
    ),
    "src/crimson/os/cyanstore/cyan_store.h": (
        "OSD-032", "CyanStore mount/mkfs and get_attr signatures change and RMATTRS helper is declared."
    ),
    "src/crimson/osd/state.h": (
        "OSD-033", "Crimson OSDState now shares a promise for when_active and fails waiting operations on stopping; peering_event calls the new gate."
    ),
    "src/crimson/osd/object_context.cc": (
        "OSD-034", "ObjectContextRegistry destructor drains LRU cache to release context references on shutdown."
    ),
    "src/crimson/osd/object_context.h": (
        "OSD-034", "ObjectContext gains interruptible lock wrappers, intrusive list tracking and head accessors; used by PG object load path."
    ),
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in affect} == set(affect)
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
