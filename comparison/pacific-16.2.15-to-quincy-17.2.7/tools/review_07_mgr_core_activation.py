"""Classify inspected MGR activation, OSD metadata and retry-clock hunks."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/mgr/Mgr.cc": ("MGR-001;MGR-011", "Target registers Ceph SQLite VFS during MGR init and aborts if setup fails; unlike late Pacific base it retains out-and-down existing OSDs in daemon metadata set, affecting upgrade observability."),
    "src/mgr/MgrStandby.cc": ("MGR-010", "Target MGR chooses ms_public_type when configured and strips positional=false from command descriptors sent to pre-Quincy MON; affects mixed-version activation and MGR connectivity."),
    "src/mgr/MgrClient.h": ("MGR-012", "MGR client reconnect retry timestamp changes from wall clock to monotonic clock, altering retry timing under host time adjustments during rollout."),
}
trivial = {
    "src/ceph_mgr.cc": "T07-mgr-entrypoint: Namespace qualifiers and argv vector helper refactor; startup defaults and argument decisions unchanged.",
    "src/messages/MMgrBeacon.h": "T07-beacon-old-protocol: Removes encode/decode support below SERVER_NAUTILUS/v8; Pacific/Quincy endpoint MGR-MON pairing uses the newer format, so no causal path within this upgrade scope.",
    "src/mgr/Mgr.h": "T07-mgr-admin-signature: Adds unused admin-socket input-buffer argument to interface; command body ignores it, so same result for existing commands.",
    "src/mgr/MgrClient.cc": "T07-mgr-report-copy: Constructs metric report in place instead of local copy; serialized payload and send call unchanged.",
    "src/mgr/MgrStandby.h": "T07-mgr-standby-typing: Qualifies vector type in method declaration; no altered startup or beacon behavior.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = set(affect) | set(trivial)
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        ids, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = ids
        row["impact_reason"] = f"{ids}: {reason}"
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
