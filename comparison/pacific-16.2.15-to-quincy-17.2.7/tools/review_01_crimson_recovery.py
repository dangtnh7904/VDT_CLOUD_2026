"""Record reviewed Crimson recovery scheduling, stale-message and lifetime hunks."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/crimson/osd/osd_operations/background_recovery.cc": (
        "OSD-039", "Recovery may delay before throttle acquisition and now runs with PG interval/shutdown interruption."
    ),
    "src/crimson/osd/osd_operations/background_recovery.h": (
        "OSD-039", "Adds recovery delay and interruptible future to urgent, PG-log and backfill operations."
    ),
    "src/crimson/osd/osd_operations/recovery_subrequest.cc": (
        "OSD-039", "Inbound recovery subrequest is wrapped in PG interruption and stops when interval/shutdown invalidates it."
    ),
    "src/crimson/osd/osd_operations/replicated_request.cc": (
        "OSD-039", "Replica write request handling is interrupted when PG interval changes or shutdown begins."
    ),
    "src/crimson/osd/osd_operations/replicated_request.h": (
        "OSD-039", "Replica request stages use the new exclusive pipeline and handle type used by interruptible work."
    ),
    "src/crimson/osd/pg_recovery.cc": (
        "OSD-039;OSD-041", "PG-log recovery gets a small delay and interruptible waiters; on_local_recover now aborts on unsupported LOST_REVERT branch."
    ),
    "src/crimson/osd/pg_recovery.h": (
        "OSD-039", "Recovery waiters, push/delete vectors and backfill messages use interruptible futures and unique message ownership."
    ),
    "src/crimson/osd/recovery_backend.cc": (
        "OSD-039;OSD-040", "Recovery/scan becomes interruptible; stale backfill/scan and removable replica messages are discarded before processing."
    ),
    "src/crimson/osd/recovery_backend.h": (
        "OSD-039", "Recovery backend API and wait-for-object blocker use PG interval interruption."
    ),
    "src/crimson/osd/shard_services.cc": (
        "OSD-042", "Peering/recovery messages transfer unique ownership through send_to_osd and context dispatch; lifecycle is coordinated with registry."
    ),
    "src/crimson/osd/shard_services.h": (
        "OSD-042", "start_operation retains operation until asynchronous start future completes, avoiding dangling request lifetime."
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
