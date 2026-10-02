"""Record reviewed Crimson request, interruption, peering and watch hunks."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
groups = {
    "OSD-035": {
        "src/crimson/osd/osd_operation.cc": "Moves operation/pipeline implementation to common layer; generic pipeline replaces the old ordered phase API.",
        "src/crimson/osd/osd_operation.h": "OperationT inherits interruptible operation and the old ordered phase is replaced by generic pipeline types.",
        "src/crimson/osd/osd_connection_priv.h": "Adds per-connection, per-PG OpSequencers for client request replay.",
        "src/crimson/osd/osd_operation_sequencer.h": "New sequencing gate preserves same-session same-PG order across interval resets and aborts blocked requests on primary loss.",
        "src/crimson/osd/osd_operations/client_request.cc": "Client requests use interruptible pipeline, per-PG sequencer and split submitted/completed futures; replay/abort behavior changes.",
        "src/crimson/osd/osd_operations/client_request.h": "Client request pipeline gains concurrent wait_repop and ordered send_reply phases plus sequencing state.",
        "src/crimson/osd/osd_operations/client_request_common.cc": "Shared request path starts urgent recovery for missing objects and decides retry/abort for acting-set or shutdown exceptions.",
        "src/crimson/osd/osd_operations/client_request_common.h": "Declares shared recover-missing and retry/abort decision used by client and internal requests.",
        "src/crimson/osd/osd_operations/osdop_params.h": "Operation parameters carry req_id/mtime instead of retaining MOSDOp reference; metadata lifetime changes with request path.",
        "src/crimson/osd/osd_operations/common/pg_pipeline.h": "Introduces shared exclusive PG stages used by external and internal client requests.",
    },
    "OSD-036": {
        "src/crimson/osd/osd_operations/internal_client_request.cc": "New internal request executes OSD ops through PG active/recovery/object-lock pipeline with interruption/retry.",
        "src/crimson/osd/osd_operations/internal_client_request.h": "Defines internal OSD request abstraction used by WatchTimeoutRequest.",
    },
    "OSD-037": {
        "src/crimson/osd/pg_interval_interrupt_condition.cc": "Captures PG epoch and detects interval creation, stopping and primary state to interrupt in-flight work.",
        "src/crimson/osd/pg_interval_interrupt_condition.h": "Defines acting-set-changed and system-shutdown interruption results for PG work.",
        "src/crimson/osd/osd_operations/peering_event.cc": "Peering event uses interruptible stages; remote event waits for OSD ACTIVE before PG lookup/message dispatch.",
        "src/crimson/osd/osd_operations/peering_event.h": "Peering pipeline gains await_active stage and interruptible completion path.",
    },
    "OSD-038": {
        "src/crimson/osd/watch.cc": "Watch ping and notify timers now expire, issue internal UNWATCH, send timed-out completion and disconnect.",
        "src/crimson/osd/watch.h": "Adds watch/notify timers and changes notify_reply_t encoding by removing DENC preamble.",
    },
}
affect = {name: (fid, reason) for fid, items in groups.items() for name, reason in items.items()}
assert len(affect) == sum(map(len, groups.values()))
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
