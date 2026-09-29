"""Record reviewed remaining MON/CRUSH source and recovery tools."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "04-mon-osdmap-crush.csv"
clusters = {
    "MON-010": {"src/mon/FSCommands.h"},
    "MON-018": {"src/crush/CrushLocation.cc"},
    "MON-019": {"src/messages/MMonJoin.h"},
    "MON-020": {
        "src/crush/CrushTester.cc",
        "src/crush/CrushTester.h",
        "src/tools/crushtool.cc",
    },
    "MON-021": {"src/tools/ceph_monstore_tool.cc"},
    "MON-022": {"src/tools/crushdiff"},
    "MON-023": {"src/tools/monmaptool.cc"},
    "MON-024": {"src/tools/osdmaptool.cc"},
}
reasons = {
    "MON-010": "FS command handler drops batched_propose hook as MDSMonitor moves plug/unplug to prepare_update and tick.",
    "MON-018": "Crimson without alien now aborts if crush_location_hook is configured; classic subprocess path remains.",
    "MON-019": "MMonJoin drops pre-Nautilus wire encoding/decoding and asserts on legacy message version or peer feature.",
    "MON-020": "CrushTester/crushtool remove ruleset/min-max-derived defaults and require explicit replica range for mapping tests.",
    "MON-021": "MON store recovery tool switches to scope guards and early returns, changing cleanup/error paths for store operations.",
    "MON-022": "New crushdiff tool compares CRUSH map changes and estimated PG/object/byte movement using osdmaptool and PG stats.",
    "MON-023": "monmaptool create now defaults unspecified min_mon_release to Octopus rather than unknown.",
    "MON-024": "osdmaptool gains deterministic upmap seed and changes PG mapping dump/count behavior used for validation.",
}
trivial = {
    "src/mon/KVMonitor.cc": "Only command-format helper and boost::optional to std::optional/reset; both optional encoders use identical present-byte/value layout in v17.2.7 encoding.h.",
    "src/mon/KVMonitor.h": "Only std qualification and boost::optional to std::optional; encoded pending value layout is unchanged by encoding.h overloads.",
    "src/mon/MDSMonitor.h": "Only std::ostream qualification in existing FS summary wrapper.",
    "src/mon/MgrStatMonitor.h": "Only boost::optional to std::optional API parameter; both carry the same pool ID/absence and encoded layout.",
    "src/osd/OSDMapMapping.h": "Moves full-map update helper to private and friends OSDMapTest; production mapping path is unchanged.",
    "src/tools/rebuild_mondb.cc": "Only adds using namespace std declaration; no rebuild command behavior change.",
}
all_paths = set().union(*clusters.values())
assert all_paths.isdisjoint(trivial)
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in all_paths | trivial.keys()} == all_paths | trivial.keys()
for row in rows:
    p = row["path"]
    if p in all_paths:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        fid = next(fid for fid, paths in clusters.items() if p in paths)
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reasons[fid]}"
    elif p in trivial:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T04-source: {trivial[p]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
