"""Record hunk and commit reviewed classic PG, peering, and recovery changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/osd/PG.cc": (
        "OSD-012",
        "PG recovery queue cost uses average object size/priority; scrub excludes snaptrim PG and publishes schedule state.",
    ),
    "src/osd/PG.h": (
        "OSD-012",
        "PG interface and stats change for recovery cost and scrub scheduling/status publication.",
    ),
    "src/osd/PeeringState.cc": (
        "OSD-013;OSD-014",
        "Peering always emits v2 PG messages and asserts Octopus features; lease ack rechecks readability at expiry and recovery priorities distinguish PG states.",
    ),
    "src/osd/PeeringState.h": (
        "OSD-013;OSD-014",
        "Peering context removes legacy release selector and defines state-aware recovery priorities for mClock/WPQ.",
    ),
    "src/osd/PrimaryLogPG.cc": (
        "OSD-015;OSD-016;OSD-017;OSD-019",
        "Pool EIO reply/drop semantics, manifest refcount/rollback handling, sparse-read truncation, numeric xattr parsing and object-class gather change.",
    ),
    "src/osd/PrimaryLogPG.h": (
        "OSD-016;OSD-019",
        "Manifest/refcount, copy, rollback and object-class gather interfaces and state change with PrimaryLogPG implementation.",
    ),
    "src/osd/ReplicatedBackend.cc": (
        "OSD-018",
        "Pull completion queues recovery work with estimated push-byte cost; Octopus clean-region recovery path becomes unconditional.",
    ),
}
trivial = {
    "src/osd/ReplicatedBackend.h": "Only changes string-keyed attrs map comparator to std::less<>; key order and values remain unchanged.",
}
all_paths = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in all_paths} == all_paths
for row in rows:
    name = row["path"]
    if name in affect:
        assert row["upgrade_impact"] in ("", "affect")
        ids, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = ids
        row["impact_reason"] = f"{ids}: {reason}"
    elif name in trivial:
        assert row["upgrade_impact"] in ("", "trivial")
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-PG: {trivial[name]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
