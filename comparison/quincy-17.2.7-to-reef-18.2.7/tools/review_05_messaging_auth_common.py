#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 05 messaging/auth/common rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "05-messaging-auth-common.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str, ids: str = "") -> tuple[str, str, str]:
    return "trivial", ids, reason


CLUSTERS: dict[str, tuple[set[str], str]] = {
    "MSG-001": (
        {
            "src/common/ceph_releases.h",
            "src/common/ceph_strings.cc",
            "src/include/ceph_features.h",
            "src/include/rados.h",
        },
        "Defines Reef's release number and SERVER_REEF feature and includes it in supported/default feature masks; peer and release-floor decisions can therefore differ across this hop.",
    ),
    "MSG-002": (
        {
            "src/msg/Dispatcher.h",
            "src/msg/Messenger.h",
        },
        "Adds explicit dispatcher priority ordering and changes fast-authentication to a boolean success contract, altering which consumer sees messages/auth events first during reconnect and MON-client setup.",
    ),
    "MSG-003": (
        {
            "src/msg/Messenger.cc",
            "src/msg/async/AsyncConnection.cc",
            "src/msg/async/AsyncConnection.h",
            "src/msg/async/AsyncMessenger.cc",
            "src/msg/async/PosixStack.cc",
            "src/msg/async/ProtocolV1.cc",
            "src/msg/async/ProtocolV1.h",
            "src/msg/async/ProtocolV2.cc",
            "src/msg/async/Stack.h",
            "src/msg/async/rdma/RDMAConnectedSocketImpl.cc",
            "src/msg/async/rdma/RDMAStack.h",
        },
        "Changes classic AsyncMessenger identity, partial-send/requeue handling, shutdown wait, MON socket priority, timeout/encryption counters, and RDMA priority plumbing; connection continuity and rollout diagnostics can differ.",
    ),
    "MSG-004": (
        {
            "src/msg/async/Event.cc",
            "src/msg/async/Event.h",
            "src/msg/async/EventPoll.cc",
            "src/msg/async/EventPoll.h",
        },
        "Adds a poll/WSAPoll event backend and selects it on Windows; delivery and connection event processing change when target binaries are run on that platform.",
    ),
    "MSG-005": (
        {
            "src/common/buffer_seastar.cc",
            "src/common/ceph_mutex.h",
            "src/crimson/common/gated.h",
            "src/crimson/common/local_shared_foreign_ptr.h",
            "src/crimson/common/smp_helpers.h",
            "src/include/buffer.h",
            "src/msg/Message.cc",
            "src/msg/Message.h",
            "src/crimson/net/Connection.h",
            "src/crimson/net/Dispatcher.h",
            "src/crimson/net/FrameAssemblerV2.cc",
            "src/crimson/net/FrameAssemblerV2.h",
            "src/crimson/net/Fwd.h",
            "src/crimson/net/Interceptor.h",
            "src/crimson/net/Messenger.cc",
            "src/crimson/net/Messenger.h",
            "src/crimson/net/Protocol.cc",
            "src/crimson/net/Protocol.h",
            "src/crimson/net/ProtocolV2.cc",
            "src/crimson/net/ProtocolV2.h",
            "src/crimson/net/Socket.cc",
            "src/crimson/net/Socket.h",
            "src/crimson/net/SocketConnection.cc",
            "src/crimson/net/SocketConnection.h",
            "src/crimson/net/SocketMessenger.cc",
            "src/crimson/net/SocketMessenger.h",
            "src/crimson/net/chained_dispatchers.cc",
            "src/crimson/net/chained_dispatchers.h",
            "src/crimson/net/io_handler.cc",
            "src/crimson/net/io_handler.h",
        },
        "Reworks Crimson msgr2 into frame assembly plus cross-shard I/O handling, including banner/auth negotiation, replacement, reset, resend, keepalive, socket shutdown, and dispatch ownership; mixed-peer continuity changes when Crimson is deployed.",
    ),
    "MSG-006": (
        {"src/common/CommandTable.h"},
        "Adds multi-target command IDs and completion tracking used by the CephFS client to fan commands across ranks, changing admin-command completion and validation output on multi-rank filesystems.",
    ),
    "OBS-001": (
        {
            "src/common/Formatter.cc",
            "src/common/Formatter.h",
            "src/common/HTMLFormatter.cc",
            "src/common/OpQueue.h",
            "src/common/PrioritizedQueue.h",
            "src/common/StackStringStream.h",
            "src/common/TrackedOp.cc",
            "src/common/TrackedOp.h",
            "src/common/WeightedPriorityQueue.h",
            "src/common/ceph_json.cc",
            "src/common/ceph_json.h",
            "src/common/mempool.cc",
            "src/common/perf_counters.cc",
            "src/common/perf_counters.h",
            "src/common/perf_counters_collection.cc",
            "src/common/perf_counters_collection.h",
            "src/common/perf_counters_key.cc",
            "src/common/perf_counters_key.h",
            "src/crimson/common/perf_counters_collection.cc",
            "src/crimson/common/perf_counters_collection.h",
            "src/crimson/common/throttle.cc",
            "src/crimson/common/throttle.h",
            "src/include/mempool.h",
        },
        "Changes JSON/XML/table formatting, null and boolean types, non-truncating formatted output, slow-op/queue/mempool names, and labeled counter schemas; automation and stop/go dashboards can observe different keys or value types.",
    ),
    "OBS-002": (
        {
            "src/common/Thread.cc",
            "src/common/Thread.h",
            "src/common/assert.cc",
            "src/common/ceph_timer.h",
            "src/common/code_environment.cc",
            "src/common/compat.cc",
            "src/common/subsys.h",
            "src/log/Entry.h",
            "src/log/Log.cc",
            "src/log/Log.h",
        },
        "Captures thread names at log-entry time, preserves recent name history, fixes recent-log capacity, and changes subsystem names; crash evidence and log-filter assumptions used during rollout can differ.",
    ),
    "OBS-003": (
        {
            "src/common/tracer.cc",
            "src/common/tracer.h",
        },
        "Switches Jaeger export to a configured port and batch processor and changes noop span handling; trace timing/completeness differs when tracing is part of upgrade validation.",
    ),
    "RUNTIME-001": (
        {
            "src/common/SubProcess.cc",
            "src/common/fork_function.h",
            "src/global/global_init.cc",
        },
        "Uses close_range for child FD cleanup and changes daemon initialization, privilege retention, /dev/null reopening, and post-fork handling; restart behavior can differ under high FD counts or privilege-dropping configurations.",
    ),
    "DATA-001": (
        {"src/common/bit_vector.hpp"},
        "Fixes post-increment to advance the actual iterator and tightens const iteration; RBD object-map iteration can otherwise revisit the same entry and change object-map update correctness.",
    ),
    "NET-001": (
        {
            "src/common/pick_address.cc",
            "src/common/pick_address.h",
        },
        "Adds address-in-subnet validation used by target OSDMap stretch/network checks, changing whether configured public addresses pass topology validation.",
    ),
    "FS-001": (
        {
            "src/common/snap_types.cc",
            "src/common/snap_types.h",
            "src/include/ceph_fs.h",
            "src/include/encoding.h",
        },
        "Adds versioned CephFS snapshot metadata and request-head v3 fields/length skipping plus round-trip chrono encoding used by persisted metadata; old/new decoders and clients can observe different wire/state fields.",
    ),
    "STOR-001": (
        {
            "src/common/blkdev.cc",
            "src/common/blkdev.h",
        },
        "Removes built-in VDO statistics helpers as Reef introduces the external-block-device plugin path; VDO capacity/accounting behavior depends on the target plugin being built and loaded.",
    ),
    "CRIMSON-001": (
        {
            "src/crimson/common/config_proxy.h",
            "src/crimson/common/operation.cc",
            "src/crimson/common/operation.h",
        },
        "Changes Crimson cross-shard config observer delivery and OSD operation/pipeline tracking and exit barriers; live config application and in-flight operation behavior differ on Crimson OSDs.",
    ),
    "DEP-001": (
        {"src/crypto/isa-l/isa-l_crypto"},
        "Moves the ISA-L Crypto gitlink from 603529a4 to a6dc8696; it can change target crypto code/build output, but both submodule commits are absent from the shallow source so internal impact remains unresolved.",
    ),
}


def build_affect() -> dict[str, tuple[str, str, str]]:
    result: dict[str, tuple[str, str, str]] = {}
    for finding_id, (paths, reason) in CLUSTERS.items():
        for path in paths:
            if path in result:
                old = result[path]
                result[path] = affect(f"{old[1]}, {finding_id}", f"{old[2]} {reason}")
            else:
                result[path] = affect(finding_id, reason)
    # Mixed files implement more than one reviewed behavior.
    result["src/common/ceph_context.cc"] = affect(
        "OBS-001, RUNTIME-001",
        "Adds labeled/non-labeled counter commands and also changes post-fork watcher locking; both validation schemas and fork/restart behavior differ.",
    )
    result["src/common/ceph_context.h"] = affect(
        "OBS-001, RUNTIME-001",
        "Adds the injectable log-construction contract used by target logging and lifecycle paths, supporting changed observability and restart initialization.",
    )
    result["src/global/global_init.cc"] = affect(
        "RUNTIME-001, STOR-001",
        "Changes daemon privilege/FD/post-fork initialization and links the external-block-device plugin path; restart and VDO integration can differ.",
    )
    return result


AFFECT = build_affect()


def trivial_verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]
    if row["file_type"] == "test/QA":
        return trivial(
            "MSG-TEST: repository messenger test/benchmark coverage only; it supports runtime findings but is not an executed acceptance gate in this suite."
        )
    if path.startswith("src/common/win32/") or path.startswith("src/include/win32/"):
        return trivial(
            "COMMON-WIN: reviewed Windows portability/typing maintenance with no demonstrated change to the Linux Ceph daemon rollout evaluated by this suite."
        )
    if path.startswith("src/auth/"):
        return trivial(
            "AUTH-CODE: changes an internal CephX ticket flag assignment from integer zero to boolean false; ticket invalidation and wire/authentication behavior are identical."
        )
    if path.startswith("src/crimson/common/"):
        return trivial(
            "CRIMSON-CODE: reviewed template, iterator, formatter, logging-macro, or helper refactoring; unlike the promoted config/pipeline/network rows, this hunk has no independent rollout or persisted-state effect."
        )
    if path.startswith("src/msg/") or path.startswith("src/messages/"):
        return trivial(
            "MSG-CODE: reviewed dead-message declarations, formatting, optional-type, thread-name, or interface plumbing; active negotiation/retry/dispatch exceptions are promoted separately."
        )
    if path.startswith("src/include/"):
        return trivial(
            "INCLUDE-CODE: reviewed C++20 comparison/formatting/concept or convenience-API maintenance that preserves the existing encoded bytes and has no demonstrated upgrade execution path."
        )
    if path.startswith("src/common/"):
        return trivial(
            "COMMON-CODE: reviewed shared-runtime cleanup, unused helper/API addition, type modernization, or platform-neutral refactor; affecting output, lifecycle, data, and network exceptions are promoted separately."
        )
    if path.startswith("src/global/") or path.startswith("src/log/"):
        return trivial(
            "RUNTIME-CODE: reviewed signature or declaration maintenance with no independent daemon start/stop or validation effect beyond the promoted lifecycle/logging rows."
        )
    raise RuntimeError(f"owner 05 has an unreviewed trivial category: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    row_paths = {row["path"] for row in rows}
    unknown_affect = sorted(set(AFFECT) - row_paths)
    if unknown_affect:
        raise RuntimeError(f"owner 05 affect mapping has paths outside CSV: {unknown_affect!r}")
    if len(row_paths) != len(rows):
        raise RuntimeError("owner 05 CSV contains duplicate paths")

    for row in rows:
        verdict = AFFECT.get(row["path"])
        if verdict is None:
            verdict = trivial_verdict(row)
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = verdict

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
        f"Classified owner 05: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
