"""Record reviewed PGMap, MON startup, configuration and capability changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "04-mon-osdmap-crush.csv"
clusters = {
    "MON-014": {"src/mon/PGMap.cc", "src/mon/PGMap.h"},
    "MON-015": {"src/mon/MonCap.cc"},
    "MON-016": {"src/ceph_mon.cc"},
    "MON-017": {
        "src/mon/ConfigMap.cc",
        "src/mon/ConfigMap.h",
        "src/mon/ConfigMonitor.cc",
        "src/mon/ConfigMonitor.h",
    },
}
reasons = {
    "MON-014": "PGMapDigest drops old decode/encode versions, pool free-space uses direct CRUSH rule IDs, and PG table columns change.",
    "MON-015": "MON caps for OSD/MGR profiles add config rm and telemetry heap/mempool commands.",
    "MON-016": "ceph-mon changes messenger bind/public address path and routes SIGHUP through Monitor handler.",
    "MON-017": "ConfigMonitor output uses canonical option names and changes optional pending/config storage types plus command formatting.",
}
trivial = {
    "src/messages/MMonCommand.h": "Only std::string qualification in command print path; no payload or command semantics change.",
    "src/messages/MMonCommandAck.h": "Only std::string qualification in ack print path; no payload or status change.",
    "src/mon/Session.h": "Only std::string/std::string_view qualification of existing CephFS cap helpers.",
    "src/mon/ConnectionTracker.h": "Only std::map qualification of existing fields and friend signature; no election report change.",
    "src/mon/MonCap.h": "Only std::string/std::string_view qualification of existing capability helper signatures.",
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
        row["impact_reason"] = f"T04-MON: {trivial[p]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
