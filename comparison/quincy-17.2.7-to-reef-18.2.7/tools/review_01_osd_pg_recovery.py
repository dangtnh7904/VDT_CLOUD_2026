#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 01 OSD/PG/recovery rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "01-osd-pg-recovery.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


CLASSIC_AFFECT: dict[str, tuple[str, str, str]] = {
    "src/ceph_osd.cc": affect(
        "OSD-002",
        "Changes classic OSD startup by preloading the external block-device plugin and generating the daemon nonce with the target random helper; startup dependency and daemon identity behavior differ.",
    ),
    "src/os/ObjectStore.cc": affect(
        "FILESTORE-001",
        "Removes FileStore construction/probing from the ObjectStore factory; an OSD still backed by FileStore cannot start on the target binary.",
    ),
    "src/os/ObjectStore.h": affect(
        "FILESTORE-001, OSD-002",
        "Carries the target ObjectStore lifecycle/perf contract used after FileStore removal and by the changed OSD startup and shutdown paths.",
    ),
    "src/os/fs/btrfs_ioctl.h": affect(
        "FILESTORE-001",
        "Deletes the Btrfs ioctl helper that only supported the removed FileStore implementation, confirming that legacy FileStore media has no Reef activation path.",
    ),
    "src/osd/ECBackend.cc": affect(
        "RECOVERY-001, SCRUB-001",
        "Changes EC deep-scrub cache advice and propagates repair state into repaired-object accounting; recovery and scrub results can differ on EC pools.",
    ),
    "src/osd/ECBackend.h": affect(
        "RECOVERY-001, SCRUB-001",
        "Carries the changed EC repair/deep-scrub interface used by the target recovery and scrub implementations.",
    ),
    "src/osd/OSD.cc": affect(
        "OSD-001, OSD-002, SCHED-001, SCRUB-002",
        "Adds dual OSD-superblock recovery, changes startup/fast-shutdown handling, snapshots the scheduler configuration, and reports blocked scrub state; restart and rollout behavior differ.",
    ),
    "src/osd/OSD.h": affect(
        "OSD-001, OSD-002, SCHED-001, SCRUB-002",
        "Defines the target OSD superblock, lifecycle, scheduler, and scrub-health contracts used by the changed implementation.",
    ),
    "src/osd/OpRequest.cc": affect(
        "OSDOBS-001",
        "Starts request latency tracking at receive time rather than the throttle timestamp, changing the latency observed during mixed and post-upgrade validation.",
    ),
    "src/osd/OpRequest.h": affect(
        "OSDOBS-001",
        "Carries the changed request tracking timestamp and event interface used by OSD latency telemetry.",
    ),
    "src/osd/PG.cc": affect(
        "PEERING-001, RECOVERY-001, SNAP-001",
        "Changes PG activation, peering/recovery coordination, missing-object handling, and purged-snap persistence; PG state transitions can differ after an OSD is upgraded.",
    ),
    "src/osd/PG.h": affect(
        "PEERING-001, RECOVERY-001, SNAP-001",
        "Carries the target PG peering, recovery, and snap-management interfaces used by the changed runtime path.",
    ),
    "src/osd/PGBackend.cc": affect(
        "RECOVERY-001, SCRUB-001",
        "Moves the classic scrub backend out of PGBackend and changes recovery/scrub integration; target repair and object comparison behavior uses the new backend.",
    ),
    "src/osd/PGBackend.h": affect(
        "RECOVERY-001, SCRUB-001",
        "Changes the backend interface consumed by target recovery and the extracted scrub implementation.",
    ),
    "src/osd/PGLog.cc": affect(
        "RECOVERY-001",
        "Changes missing-set reconstruction and log processing, including the paged metadata path used by Crimson; restart peering can rebuild recovery state differently.",
    ),
    "src/osd/PGLog.h": affect(
        "RECOVERY-001",
        "Defines the changed PG-log and missing-set rebuild contract used during peering and recovery.",
    ),
    "src/osd/PeeringState.cc": affect(
        "PEERING-001, RECOVERY-001",
        "Adds a past-interval-bounds bypass and prevents asynchronous EC recovery from violating pool min_size; peering admission and shard selection differ under the documented conditions.",
    ),
    "src/osd/PeeringState.h": affect(
        "PEERING-001, RECOVERY-001",
        "Carries target peering checks and EC asynchronous-recovery selection state.",
    ),
    "src/osd/PrimaryLogPG.cc": affect(
        "IO-001, SCRUB-001, SNAP-001",
        "Changes extent-compare iteration, truncate digest invalidation, scrub integration, and snap handling; object results and repair inputs can differ.",
    ),
    "src/osd/PrimaryLogPG.h": affect(
        "IO-001, SCRUB-001, SNAP-001",
        "Carries the changed object-operation, scrub-backend, and snap-management interfaces used by PrimaryLogPG.",
    ),
    "src/osd/SnapMapper.cc": affect(
        "SNAP-001",
        "Changes SnapMapper traversal and purged-snap recording while making the driver reusable by Crimson; cleanup and restart-visible snap metadata can differ.",
    ),
    "src/osd/SnapMapper.h": affect(
        "SNAP-001",
        "Defines the changed SnapMapper driver, traversal, and purged-snap persistence contract.",
    ),
    "src/osd/Watch.cc": affect(
        "WATCH-001",
        "Registers a watch timeout even when the connection session is already absent, changing stale-watch cleanup and reconnect behavior.",
    ),
    "src/osd/osd_op_util.cc": affect(
        "IO-001",
        "Classifies operations that may read data so preceding writes are flushed before watch and read-capable operations; ordering and returned data can differ.",
    ),
    "src/osd/osd_op_util.h": affect(
        "IO-001",
        "Exposes the target may-read-data classification used to enforce object-operation ordering.",
    ),
    "src/osd/osd_perf_counters.cc": affect(
        "OSDOBS-001",
        "Promotes op_before_queue_op_lat from debug-only priority, changing the metric set visible to rollout monitoring.",
    ),
    "src/osd/osd_types.cc": affect(
        "SCRUB-001, SCRUB-002, SCHED-001",
        "Fixes ScrubMap flag swapping and carries target blocked-scrub and scheduler state; scrub findings and queue behavior can differ.",
    ),
    "src/osd/osd_types.h": affect(
        "OSD-001, SCRUB-001, SCRUB-002, SCHED-001, CRIMSONCTRL-001",
        "Adds the OSD-superblock omap key, blocked-scrub state, scheduler types, and Crimson pool flag while changing runtime OSD state contracts.",
    ),
    "src/tools/ceph_objectstore_tool.cc": affect(
        "OSD-001",
        "Adds get/set-superblock support and changes offline objectstore recovery actions; recovery runbooks and superblock repair must use the target command set.",
    ),
}


CLASSIC_TRIVIAL = {
    "src/os/DBObjectMap.cc",
    "src/os/DBObjectMap.h",
    "src/os/SequencerPosition.h",
    "src/osd/OSDCap.cc",
    "src/osd/ReplicatedBackend.cc",
    "src/osd/ReplicatedBackend.h",
    "src/osd/objclass.cc",
    "src/osd/object_state_fmt.h",
    "src/osd/osd_internal_types.h",
    "src/osd/osd_types_fmt.h",
    "src/osd/recovery_types.h",
    "src/tools/ceph_osdomap_tool.cc",
}


def crimson_verdict(path: str) -> tuple[str, str, str]:
    if path == "src/crimson/osd/lsan_suppressions.cc":
        return trivial(
            "CRIMSON-DEV: leak-sanitizer suppression coverage only; it is not loaded by a production Crimson OSD and does not change the upgrade path."
        )

    if path.startswith("src/crimson/tools/"):
        return trivial(
            "CRIMSON-DEV: reviewed benchmark or NBD development-tool adaptation; it is outside daemon activation, persisted compatibility, and the defined rollout acceptance path."
        )

    if path.startswith("src/crimson/admin/"):
        return affect(
            "CRIMSONOBS-001",
            "Changes Crimson admin-socket and PG command validation/output; Crimson rollout diagnostics and operator-visible commands differ.",
        )

    if path.startswith((
        "src/crimson/auth/",
        "src/crimson/crush/",
        "src/crimson/mgr/",
        "src/crimson/mon/",
    )):
        return affect(
            "CRIMSONCTRL-001",
            "Changes Crimson authentication, monitor/mgr connection handling, configuration exchange, or CRUSH-location discovery; daemon activation and control-plane behavior differ when Crimson is deployed.",
        )

    if path.startswith("src/crimson/os/"):
        return affect(
            "CRIMSONSTORE-001",
            "Changes the AlienStore/CyanStore/FuturizedStore collection, lifecycle, threading, and transaction interfaces consumed by Crimson OSD; backend activation and I/O behavior differ.",
        )

    if not path.startswith("src/crimson/osd/"):
        raise RuntimeError(f"owner 01 has an unreviewed Crimson row: {path!r}")

    rel = path.removeprefix("src/crimson/osd/")

    if rel.startswith("scheduler/"):
        return affect(
            "CRIMSONIO-001, SCHED-001",
            "Changes Crimson mClock queueing and request scheduling; latency and admission order can differ for Crimson pools.",
        )

    if rel.startswith("osd_operations/"):
        if rel.startswith((
            "osd_operations/background_recovery",
            "osd_operations/compound_peering_request",
            "osd_operations/logmissing_request",
            "osd_operations/peering_event",
            "osd_operations/pg_advance_map",
            "osd_operations/recovery_subrequest",
            "osd_operations/replicated_request",
            "osd_operations/snaptrim_event",
        )):
            return affect(
                "CRIMSONRECOVERY-001",
                "Changes a Crimson peering, map-advance, log-missing, recovery, replication, backfill, or snaptrim operation pipeline; PG convergence differs when Crimson is deployed.",
            )
        return affect(
            "CRIMSONIO-001",
            "Changes Crimson client/internal request sequencing, interruption, or PG pipeline stages; request ordering and completion behavior differ.",
        )

    if rel.startswith((
        "backfill_state",
        "ec_backend",
        "pg_recovery",
        "recovery_backend",
        "replicated_backend",
        "replicated_recovery_backend",
    )):
        return affect(
            "CRIMSONRECOVERY-001",
            "Changes Crimson recovery/backfill or replicated/EC backend state and transfer behavior; degraded PG convergence differs when Crimson is deployed.",
        )

    if rel.startswith((
        "objclass",
        "object_context",
        "ops_executer",
        "osd_operation",
        "pg_backend",
        "watch",
    )):
        return affect(
            "CRIMSONIO-001",
            "Changes Crimson object context, class execution, operation tracking/backend, or watch handling; client-visible I/O behavior differs when Crimson is deployed.",
        )

    return affect(
        "CRIMSONCTRL-001, CRIMSONRECOVERY-001",
        "Changes Crimson daemon startup/heartbeat, OSD-map gating, PG lifecycle/meta, shard services, or shutdown; activation and PG convergence differ when Crimson is deployed.",
    )


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if row["file_type"] == "documentation":
        return trivial(
            "OSD-DOC: documentation-only endpoint edit; it supplies operator context but does not execute or alter cluster state during this hop."
        )

    if row["file_type"] == "test/QA":
        return trivial(
            "OSD-TEST: repository test, fixture, suite selector, or workload edit only; it supports the promoted findings but is not an executed acceptance result for this comparison."
        )

    if path in CLASSIC_AFFECT:
        return CLASSIC_AFFECT[path]

    if path in CLASSIC_TRIVIAL:
        return trivial(
            "OSD-CODE: reviewed include/formatter/logging/API-addition or diagnostic-tool refactor; no persisted format, wire contract, rollout action, or existing daemon behavior changes in this row."
        )

    if path.startswith("src/messages/"):
        return affect(
            "WIRE-001",
            "Changes OSD operation/peering feature propagation or removes legacy PGCreate/Scrub message classes; mixed-version compatibility depends on the supported-release floor and v2 message path.",
        )

    if path.startswith("src/crimson/"):
        return crimson_verdict(path)

    if path.startswith("src/osd/scheduler/"):
        return affect(
            "SCHED-001",
            "Changes classic OSD scheduler selection, strict-priority bypass, queue counters, or mClock costing; request and recovery/scrub ordering can differ.",
        )

    if path.startswith("src/osd/scrubber/") or path == "src/osd/scrubber_common.h":
        return affect(
            "SCRUB-001, SCRUB-002",
            "Reworks the scrub backend/state machine, scheduling, dynamic costing, blocked-object handling, and reporting; scrub findings, repair, and health visibility can differ.",
        )

    raise RuntimeError(f"owner 01 has an unreviewed row: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 350:
        raise RuntimeError(f"owner 01 expected 350 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 01 CSV contains duplicate paths")

    for row in rows:
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = verdict(row)

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=header,
            delimiter=";",
            lineterminator="\r\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
    trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
    print(
        f"Classified owner 01: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
