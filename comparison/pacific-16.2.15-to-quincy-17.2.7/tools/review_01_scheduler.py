"""Record reviewed OSD entry point, scheduler, and scrub queue changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
clusters = {
    "OSD-002": {"src/ceph_osd.cc"},
    "OSD-003": {"src/osd/scheduler/OpScheduler.cc", "src/osd/scheduler/OpScheduler.h"},
    "OSD-004": {"src/osd/scheduler/mClockScheduler.cc", "src/osd/scheduler/mClockScheduler.h"},
    "OSD-005": {"src/osd/scheduler/OpSchedulerItem.cc", "src/osd/scheduler/OpSchedulerItem.h"},
    "OSD-006": {
        "src/osd/scrubber/osd_scrub_sched.cc",
        "src/osd/scrubber/osd_scrub_sched.h",
        "src/osd/scrubber_common.h",
    },
    "OSD-007": {
        "src/osd/scrubber/pg_scrubber.cc",
        "src/osd/scrubber/pg_scrubber.h",
    },
    "OSD-008": {
        "src/osd/SnapMapper.cc",
        "src/osd/SnapMapper.h",
        "src/osd/SnapMapReaderI.h",
    },
    "OSD-009": {"src/osd/ECBackend.cc"},
    "OSD-010": {"src/osd/PGLog.cc", "src/osd/PGLog.h"},
    "OSD-011": {"src/osd/OpRequest.cc", "src/osd/OpRequest.h"},
}
reasons = {
    "OSD-002": "OSD public messenger now binds public_bind_addrs while advertising public_addrs; heartbeat front bind follows bind address.",
    "OSD-003": "Scheduler factory forces wpq for FileStore OSDs even if mclock_scheduler is selected.",
    "OSD-004": "mClock changes cost/capacity units, built-in profiles, shared client identity, and QoS override reset behavior.",
    "OSD-005": "Recovery work/messages are assigned scheduler class from priority rather than uniformly background_recovery; queue latency counters added.",
    "OSD-006": "OSD scrub scheduling moves to ScrubQueue with eligibility/load/time/deadline selection and published schedule state.",
    "OSD-007": "PgScrubber changes abort/state handling and restarts blocked snap trimming on scrub completion or abort.",
    "OSD-008": "SnapMapper fixes conversion of legacy keys and adds scrub consistency checks for object-to-snap and snap-to-object mappings.",
    "OSD-009": "EC recovery read completion now supplies queue cost 1 when rescheduled during an OSDMap change.",
    "OSD-010": "Replicated PG log load sets rollback_info_trimmed_to to last_update when no on-disk rollback key exists, avoiding replay from an empty marker.",
    "OSD-011": "OpRequest dump duration now measures interval since previous event; tracing span storage is unconditional instead of HAVE_JAEGER gated.",
}
trivial = {
    "src/osd/ECBackend.h": "EC attribute maps change std::less<string> to transparent std::less<> only; string ordering and encoded entries are unchanged.",
    "src/osd/ECMsgTypes.h": "Nested EC read-reply attribute map changes comparator to std::less<> only; key ordering and message fields are unchanged.",
    "src/osd/ECTransaction.cc": "Local xattr map changes comparator to std::less<> only; key ordering and generated transaction entries are unchanged.",
    "src/osd/Watch.cc": "Missed watcher reply uses vector instead of list, preserving iteration order and identical length/element wire encoding in encoding.h.",
    "src/osd/Watch.h": "Removes unused get_last_ping getter; v16.2.15 src tree has no caller and Watch state remains unchanged.",
    "src/osd/recovery_types.cc": "Only qualifies existing BackfillInterval stream operator with std::ostream; no recovery data change.",
    "src/osd/osd_internal_types.h": "Watch attr cache comparator changes to transparent std::less<> only; string key ordering and values stay the same.",
}
all_paths = set().union(*clusters.values())
assert all_paths.isdisjoint(trivial)
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in all_paths | trivial.keys()} == all_paths | trivial.keys()
for row in rows:
    for fid, paths in clusters.items():
        if row["path"] in paths:
            assert row["upgrade_impact"] in ("", "affect")
            assert row["finding_id"] in ("", fid)
            row["upgrade_impact"] = "affect"
            row["finding_id"] = fid
            row["impact_reason"] = f"{fid}: {reasons[fid]}"
            break
    if row["path"] in trivial:
        assert row["upgrade_impact"] in ("", "trivial")
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-EC: {trivial[row['path']]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
