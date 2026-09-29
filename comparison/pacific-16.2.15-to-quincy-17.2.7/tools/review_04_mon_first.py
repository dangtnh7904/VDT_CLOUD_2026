"""Record reviewed MON quorum, auth, discovery, and command changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "04-mon-osdmap-crush.csv"
affect = {
    "MON-002": {
        "src/mon/Monitor.cc",
        "src/mon/Monitor.h",
        "src/mon/mon_types.h",
    },
    "MON-003": {
        "src/mon/AuthMonitor.cc",
        "src/mon/AuthMonitor.h",
        "src/messages/MMonUsedPendingKeys.h",
        "src/mon/MonCommands.h",
    },
    "MON-004": {
        "src/mon/MonMap.cc",
        "src/mon/MonMap.h",
    },
    "MON-005": {
        "src/mon/MonmapMonitor.cc",
    },
}
reasons = {
    "MON-002": "Quincy persistent MON feature and on-disk incompat bit become quorum requirements; Monitor also changes init, signal, and command paths.",
    "MON-003": "Pending-key rotation commands and MON-to-MON message are gated by min_mon_release quincy; command definitions also change other operator APIs.",
    "MON-004": "Crimson MonMap discovery now honors mon_host_override before monmap file, mon_host, config file or DNS SRV.",
    "MON-005": "mon feature ls --with-value changes command parser from CephChoices to CephBool compatibility handling.",
}
trivial = {
    "src/messages/MMonElection.h": "Only trailing whitespace in friend declaration; no wire or election behavior change.",
    "src/messages/MMonPing.h": "Only qualifies ostream with std namespace; no wire or ping behavior change.",
    "src/mon/ElectionLogic.h": "Adds set include and std qualification to existing virtual return type; no election algorithm change.",
    "src/mon/Elector.h": "Only qualifies existing map/set types with std namespace; no election algorithm or state change.",
    "src/mon/MonmapMonitor.h": "Only qualifies existing stringstream/string/set declarations with std namespace; no command implementation change.",
}
all_affect = set().union(*affect.values())
assert all_affect.isdisjoint(trivial)
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in all_affect | trivial.keys()} == all_affect | trivial.keys()
for row in rows:
    p = row["path"]
    if p in all_affect:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        fid = next(fid for fid, paths in affect.items() if p in paths)
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reasons[fid]}"
    elif p in trivial:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T04-MON: {trivial[p]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
