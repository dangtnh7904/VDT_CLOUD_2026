"""Record reviewed PG support, object-class, and telemetry changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/osd/OSD.h": ("OSD-001;OSD-006;OSD-024", "OSD interfaces carry recovery cost/priority, ScrubQueue, and safe fast-shutdown state/entry point."),
    "src/osd/PGBackend.h": ("OSD-018", "PGBackend recovery work interface now carries scheduler cost, used by replicated and EC backends."),
    "src/osd/objclass.cc": ("OSD-019", "Classic OSD adds remote object-class gather API and collected read result/error delivery."),
    "src/osd/osd_perf_counters.cc": ("OSD-020", "OSD exports unreadable/degraded delay and per-recovery-message queue latency counters."),
    "src/osd/osd_perf_counters.h": ("OSD-020", "OSD perf counter IDs gain delay and per-recovery-message queue latency entries."),
    "src/osd/osd_tracer.cc": ("OSD-021", "Defines the new OSD tracing namespace tracer used by request/recovery paths."),
    "src/osd/osd_tracer.h": ("OSD-021", "Declares the new OSD tracing namespace tracer used by request/recovery paths."),
    "src/osd/osd_types.cc": ("OSD-022;OSD-023", "pg_stat_t wire version rises to 29 with scrub/trim/log metrics; mClock PullOp/PushReplyOp costs change."),
    "src/osd/osd_types.h": ("OSD-015;OSD-022;OSD-023", "Adds pool EIO flag, PG stat wire fields, Crimson denc helpers and recovery cost estimator."),
}
trivial = {
    "src/osd/PGBackend.cc": "Only scrub-store include relocation and std::less<> string-map comparator; attribute values and rollback writes stay the same.",
    "src/osd/PGTransaction.h": "setattrs changes string-map comparator and structured binding; iterates same ordered key/value pairs and rebuilds values as before.",
    "src/osd/osd_op_util.cc": "Extracts existing MOSDOp classification loop into vector overload and removes READ_DATA flag with no remaining consumer in target src tree.",
    "src/osd/osd_op_util.h": "Declares extracted vector overload and removes unused may_read_data/set_read_data accessors; classic MOSDOp path still calls same classifier.",
    "src/osd/osd_types_fmt.h": "New fmt::formatter specializations for OSD types support diagnostics only; no encoder, state transition or IO path is defined.",
}
all_paths = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in all_paths | {"src/osd/OSD.cc"}} == all_paths | {"src/osd/OSD.cc"}
for row in rows:
    name = row["path"]
    if name == "src/osd/OSD.cc":
        assert row["upgrade_impact"] == "affect" and "OSD-001" in row["finding_id"]
        if "OSD-024" not in row["finding_id"]:
            row["finding_id"] += ";OSD-024"
            row["impact_reason"] += " OSD-024: fast shutdown now drains queued work and umounts a null-manager store before exit."
    elif name in affect:
        assert row["upgrade_impact"] in ("", "affect")
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    elif name in trivial:
        assert row["upgrade_impact"] in ("", "trivial")
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-support: {trivial[name]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
