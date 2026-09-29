"""Record reviewed MON service state, CephFS operations, and key rotation."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "04-mon-osdmap-crush.csv"
clusters = {
    "MON-009": {"src/mon/LogMonitor.cc", "src/mon/LogMonitor.h"},
    "MON-010": {"src/mon/MDSMonitor.cc", "src/mon/FSCommands.cc"},
    "MON-011": {"src/mon/MonClient.cc", "src/mon/MonClient.h"},
    "MON-012": {"src/mon/HealthMonitor.cc"},
    "MON-013": {"src/mon/MgrMonitor.cc"},
}
reasons = {
    "MON-009": "LogMonitor changes persisted log summary/incremental format and external logging replay/trim; Quincy reader has legacy commit branch.",
    "MON-010": "MDSMonitor changes Paxos proposal batching and exposes fs lsflags; FSCommands adds fs rename with OSD pool metadata and client auth implications.",
    "MON-011": "MonClient adds rotate-key admin socket hook to replace live Cephx key and changes auth timeout clock.",
    "MON-012": "HealthMonitor changes tick change detection and health mute duration validation; alters health command behavior.",
    "MON-013": "MgrMonitor changes always-on module release mapping and mgr module command output/force parsing.",
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
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reasons[fid]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
