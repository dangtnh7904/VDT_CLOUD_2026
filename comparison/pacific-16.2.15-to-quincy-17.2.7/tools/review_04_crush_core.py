"""Record reviewed CRUSH format, OSDMap placement, and OSDMonitor gates."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "04-mon-osdmap-crush.csv"
clusters = {
    "MON-006": {
        "src/crush/CrushCompiler.cc",
        "src/crush/CrushWrapper.cc",
        "src/crush/CrushWrapper.h",
        "src/crush/builder.c",
        "src/crush/builder.h",
        "src/crush/crush.h",
        "src/crush/grammar.h",
        "src/crush/mapper.c",
        "src/crush/mapper.h",
    },
    "MON-007": {
        "src/osd/OSDMap.cc",
        "src/osd/OSDMap.h",
    },
    "MON-008": {
        "src/mon/OSDMonitor.cc",
        "src/mon/OSDMonitor.h",
    },
}
reasons = {
    "MON-006": "CRUSH rule mask/ruleset and min/max size checks are removed; encoding remains feature-aware, while decode rejects legacy ruleset!=ruleid.",
    "MON-007": "OSDMap placement uses direct CRUSH rule IDs, relaxes min/max checks, changes upmap calculation and reports Quincy OSD release checkpoint.",
    "MON-008": "OSDMonitor switches to direct CRUSH rule IDs and per-rule PG limits, changes CRUSH command validation and Quincy release handling.",
}
all_paths = set().union(*clusters.values())
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in all_paths} == all_paths
for row in rows:
    p = row["path"]
    if p in all_paths:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        fid = next(fid for fid, paths in clusters.items() if p in paths)
        row["upgrade_impact"] = "affect"
        if p == "src/mon/OSDMonitor.cc":
            row["finding_id"] = "MON-001; MON-008"
            row["impact_reason"] = (
                "MON-001; MON-008: Quincy require-osd-release checkpoint; "
                + reasons[fid]
            )
        else:
            row["finding_id"] = fid
            row["impact_reason"] = f"{fid}: {reasons[fid]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
