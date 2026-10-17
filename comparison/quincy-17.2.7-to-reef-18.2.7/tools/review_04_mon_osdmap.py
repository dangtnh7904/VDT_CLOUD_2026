#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 04 MON/OSDMap/CRUSH rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "04-mon-osdmap-crush.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str, ids: str = "") -> tuple[str, str, str]:
    return "trivial", ids, reason


AFFECT = {
    "src/messages/MMonCommand.h": affect(
        "MON-008",
        "Adds a copy path that preserves command tid and data for Crimson MON-client retry; "
        "this conditionally changes command retry fidelity rather than only type spelling.",
    ),
    "src/mon/AuthMonitor.cc": affect(
        "MON-002, MON-008",
        "Auth mutations now acknowledge after Paxos commit, and fs authorize/authentication "
        "handling changes accepted capability and failure behavior during leader churn.",
    ),
    "src/mon/ConfigMap.cc": affect(
        "MON-004",
        "Config dump/display emits each stored localized option spelling instead of the normalized "
        "schema name, changing CLI/JSON output consumed by audits and automation.",
    ),
    "src/mon/ConfigMap.h": affect(
        "MON-004",
        "MaskedOption persists the localized option name used by ConfigMap output, forming the data "
        "path for the externally visible config-name change.",
    ),
    "src/mon/ConfigMonitor.cc": affect(
        "MON-002, MON-004",
        "Loads the original stored option spelling into ConfigMap and changes successful config "
        "commands to reply after commit, affecting output and failover-time acknowledgements.",
    ),
    "src/mon/ConnectionTracker.cc": affect(
        "MON-003",
        "Connectivity elections now discard negative-rank reports and expose reports/scores as JSON "
        "arrays, changing stretch-election state hygiene and the admin-socket schema.",
    ),
    "src/mon/ElectionLogic.cc": affect(
        "MON-003",
        "A stretch tiebreaker ignores proposals from monitors marked down by stretch recovery, so "
        "leader selection differs in the affected failure topology.",
    ),
    "src/mon/ElectionLogic.h": affect(
        "MON-003",
        "Extends the election-owner contract with stretch tiebreaker and marked-down checks used by "
        "the changed connectivity election decision.",
    ),
    "src/mon/Elector.cc": affect(
        "MON-003",
        "Implements stretch tiebreaker/marked-down membership checks and rejects invalid rank state "
        "used by connectivity election tracking.",
    ),
    "src/mon/Elector.h": affect(
        "MON-003",
        "Exposes the stretch-election checks and unsigned rank-removal contract consumed by the new "
        "election path.",
    ),
    "src/mon/FSCommands.cc": affect(
        "MON-005",
        "Adds Reef FSMap flags and max_xattr_size, fs swap, batched OSD/FSMap proposals, and health "
        "guards for fs fail; CephFS administration and failover prerequisites change.",
    ),
    "src/mon/FSCommands.h": affect(
        "MON-005",
        "Adds batched-proposal and pool-overlay contracts plus the unhealthy-MDS refusal text used by "
        "the changed CephFS command path.",
    ),
    "src/mon/HealthMonitor.cc": affect(
        "MON-002, MON-006",
        "MON_DOWN now waits for both mkfs and monitor-uptime grace, mute TTL parsing/expiry changes, "
        "and successful mutations acknowledge after commit; health gates can differ after restart.",
    ),
    "src/mon/KVMonitor.cc": affect(
        "MON-002",
        "KV mutations now reply after the next committed proposal and assert writeability for OSD "
        "credential cleanup, changing acknowledgement behavior around elections.",
    ),
    "src/mon/LogMonitor.cc": affect(
        "CFG-008, MON-002",
        "Implements the unified mon_cluster_log_level for all external sinks and moves log command "
        "acknowledgements to commit, changing target MON log filtering and command timing.",
    ),
    "src/mon/LogMonitor.h": affect(
        "CFG-008",
        "Replaces separate file/syslog level maps and observed keys with the unified log-level map "
        "used by target MON external logging.",
    ),
    "src/mon/MDSMonitor.cc": affect(
        "MON-002, MON-005",
        "CephFS commands now use commit acknowledgement and scoped batching, and MDS/fs fail refuses "
        "unsafe failover on trim/cache health warnings unless explicitly confirmed.",
    ),
    "src/mon/MDSMonitor.h": affect(
        "MON-005",
        "Adds the MDS-health query consumed by Reef failover guards, so it participates in the new "
        "operator command contract.",
    ),
    "src/mon/MgrMap.h": affect(
        "MON-007",
        "Bumps MgrMap encoding and persists/dumps FLAG_DOWN, creating a new cluster-state field that "
        "suppresses active-manager selection.",
    ),
    "src/mon/MgrMonitor.cc": affect(
        "MON-002, MON-007",
        "Adds mgr set down, blocks active promotion while the flag is set, logs promotion, and uses "
        "commit acknowledgements; manager availability can be intentionally held down.",
    ),
    "src/mon/MgrMonitor.h": affect(
        "MON-007",
        "Adopts CommandHandler for the new persisted mgr set down command path rather than a compile-"
        "only interface cleanup.",
    ),
    "src/mon/MgrStatMonitor.h": affect(
        "MON-010",
        "Adds mgrstat first/last committed fields to monitor dump output, changing an admin/diagnostic "
        "schema that upgrade tooling may parse.",
    ),
    "src/mon/MonClient.cc": affect(
        "MON-008",
        "Prioritizes MON client dispatch, honors mon_client_target_rank on reconnect, and converts "
        "failed fast-auth setup into EACCES, changing connection/retry behavior.",
    ),
    "src/mon/MonCommands.h": affect(
        "MON-005, MON-007, MON-011, MON-012, MON-013",
        "Publishes new Reef command contracts for CephFS, mgr down, require-osd-release reef, primary "
        "upmap/read balancing, snapshot repair, Crimson, and stronger destructive confirmations.",
    ),
    "src/mon/MonMap.cc": affect(
        "MON-008",
        "Falls back to an address converted to legacy form when a MON has no explicit v1 address, "
        "preserving discovery for older clients/monitors in mixed compatibility cases.",
    ),
    "src/mon/Monitor.cc": affect(
        "MON-001, MON-003, MON-006, MON-008, MON-010",
        "Adds the Reef on-disk incompat feature, stretch disallowed-leader rules, uptime/status fields, "
        "ok-to-stop validation, store provenance output, and hard failure for invalid fast auth.",
    ),
    "src/mon/Monitor.h": affect(
        "MON-001, MON-006, MON-008",
        "Defines the Reef monitor incompat bit and the uptime/authentication contracts used by the "
        "new rollback boundary and health/auth paths.",
    ),
    "src/mon/MonitorDBStore.h": affect(
        "MON-009",
        "Newly created or rebuilt monitor stores record creator version and creation time, which then "
        "appears in MON metadata and changes recovery/provenance evidence.",
    ),
    "src/mon/MonmapMonitor.cc": affect(
        "MON-001, MON-002, MON-003",
        "Persists newly quorum-supported MON features/min release, restructures mutating commands to "
        "reply after commit, and coordinates stretch monmap proposals; rollback and failover behavior change.",
    ),
    "src/mon/OSDMonitor.cc": affect(
        "MON-002, MON-011, MON-012, MON-013",
        "Adds Reef OSD release/boot gates, primary-upmap and Crimson/pool/snapshot command contracts, "
        "safer destructive confirmations, and commit-based acknowledgements across OSDMap mutations.",
    ),
    "src/mon/OSDMonitor.h": affect(
        "MON-011, MON-012, MON-013",
        "Extends OSDMonitor state and helpers for per-pool trim floors, snapshot removal, Crimson pool "
        "creation, and primary-upmap parsing used by the new persisted behavior.",
    ),
    "src/mon/PGMap.cc": affect(
        "MON-010",
        "Adds stuck-peering reporting and BlueStore/block-device stalled/slow health summaries, which "
        "can change health-based stop/go and monitoring output after target daemons report them.",
    ),
    "src/mon/PGMap.h": affect(
        "MON-010",
        "Adds the STUCK_PEERING query bit consumed by the new externally visible PG stuck filter.",
    ),
    "src/mon/PaxosService.cc": affect(
        "MON-002",
        "Completes wait-for-commit callbacks only when last_committed advances and returns EAGAIN on "
        "leader loss/restart/shutdown, changing command completion semantics under churn.",
    ),
    "src/mon/PaxosService.h": affect(
        "MON-002",
        "Introduces the separate wait_for_commit callback queue used by mutating MON services, distinct "
        "from proposal-finished-and-active callbacks.",
    ),
    "src/mon/mon_types.h": affect(
        "MON-001",
        "Adds Reef to supported and persistent MON feature sets and release inference; once committed, "
        "the feature is a deliberate downgrade barrier.",
    ),
    "src/osd/OSDMap.cc": affect(
        "MON-003, MON-010, MON-011, MON-012",
        "Adds Reef OSDMap encoding/release detection, pg_upmap_primary and read-balance algorithms, "
        "new health signals, and stretch topology checks; persisted map and operator gates change.",
    ),
    "src/osd/OSDMap.h": affect(
        "MON-011, MON-012",
        "Adds persisted primary-upmap maps, Reef encoding helpers, read-balance data and APIs consumed "
        "by MON and osdmaptool.",
    ),
    "src/tools/monmaptool.cc": affect(
        "MON-009",
        "A newly created monmap without an explicit floor now defaults min_mon_release from Octopus "
        "to Pacific, changing bootstrap/recovery artifacts made by the target tool.",
    ),
    "src/tools/osdmaptool.cc": affect(
        "MON-012",
        "Adds offline read-primary balancing and emits pg-upmap-primary commands, providing a new "
        "post-upgrade placement workflow gated by Reef compatibility floors.",
    ),
}


TRIVIAL_RUNTIME = {
    "src/ceph_mon.cc": trivial(
        "MON-CODE-001: converts store/throttler lifetime to RAII and uses the shared random nonce API; "
        "the endpoint hunk does not change upgrade eligibility or store format by itself."
    ),
    "src/crush/CrushLocation.cc": trivial(
        "MON-CODE-002: namespace qualification cleanup only; parsed CRUSH location values and callers are unchanged."
    ),
    "src/crush/CrushLocation.h": trivial(
        "MON-CODE-003: namespace and fmt formatter declarations only; no CRUSH location or placement rule changes."
    ),
    "src/crush/sample.txt": trivial(
        "MON-CODE-004: removes an unreferenced sample CRUSH location text file; no build, runtime, or upgrade recipe consumes it."
    ),
    "src/messages/MMonCommandAck.h": trivial(
        "MON-CODE-005: namespace spelling changes only; the wire fields and encode/decode contract are identical."
    ),
    "src/mon/AuthMonitor.h": trivial(
        "MON-CODE-006: changes a private helper return type from int to void to match an already validated internal path; no caller consumes the old result."
    ),
    "src/mon/MonCap.cc": trivial(
        "MON-CODE-007: replaces a Boost umbrella include; capability grammar and parse behavior do not change in this row."
    ),
    "src/mon/MonMap.h": trivial(
        "MON-CODE-008: makes removed-rank bookkeeping unsigned and clarifies a stretch comment; serialized map meaning and election decisions are unchanged here."
    ),
    "src/mon/MonOpRequest.h": trivial(
        "MON-CODE-009: tracks the parent async-op descriptor method rename only; request contents and dispatch behavior are unchanged."
    ),
    "src/osd/OSDMapMapping.h": trivial(
        "MON-CODE-010: changes an accessor argument to unsigned to match the container index; mapping contents and calculation are unchanged."
    ),
    "src/tools/ceph_monstore_tool.cc": trivial(
        "MON-CODE-011: passes CephContext to the refactored OSDMap print signature; command selection and recovered map bytes are unchanged."
    ),
}


SUPPORT_IDS = {
    "doc/dev/mon-elections.rst": "MON-003",
    "doc/man/8/ceph-monstore-tool.rst": "MON-009",
    "doc/rados/operations/crush-map-edits.rst": "MON-012",
    "doc/rados/operations/crush-map.rst": "MON-012",
    "doc/rados/operations/monitoring.rst": "MON-010",
    "doc/rados/troubleshooting/troubleshooting-mon.rst": "MON-006, MON-009",
    "qa/standalone/mon-stretch/mon-stretch-uneven-crush-weights.sh": "MON-003, MON-010",
    "qa/standalone/mon/misc.sh": "MON-001",
    "qa/standalone/mon/mon-cluster-log.sh": "CFG-008",
    "qa/standalone/mon/osd-erasure-code-profile.sh": "MON-013",
    "qa/suites/netsplit/tests/mon_pool_ops.yaml": "MON-002, MON-003",
    "qa/tasks/mon_connection_score.py": "MON-003",
    "qa/workunits/mon/config.sh": "MON-002, MON-004",
    "qa/workunits/mon/rbd_snaps_ops.sh": "MON-013",
    "qa/workunits/mon/setup_stretch_cluster.sh": "MON-003",
    "src/test/cli/monmaptool/add-exists.t": "MON-009",
    "src/test/cli/monmaptool/add-many.t": "MON-009",
    "src/test/cli/monmaptool/clobber.t": "MON-009",
    "src/test/cli/monmaptool/create-print.t": "MON-009",
    "src/test/cli/monmaptool/create-with-add.t": "MON-009",
    "src/test/cli/monmaptool/feature-set-unset-list.t": "MON-001, MON-009",
    "src/test/cli/monmaptool/rm-nonexistent.t": "MON-009",
    "src/test/cli/monmaptool/rm.t": "MON-009",
    "src/test/common/test_json_formattable.cc": "MON-010",
    "src/test/common/test_json_formatter.cc": "MON-010",
    "src/test/common/test_mclock_priority_queue.cc": "CFG-009",
    "src/test/common/test_tableformatter.cc": "MON-010",
    "src/test/common/test_xmlformatter.cc": "MON-010",
    "src/test/crimson/test_monc.cc": "MON-008",
    "src/test/crush/CrushWrapper.cc": "MON-012",
    "src/test/mon/PGMap.cc": "MON-010",
    "src/test/mon/bench_commit.py": "MON-002",
    "src/test/mon/test_election.cc": "MON-003",
}


def support_verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]
    ids = SUPPORT_IDS.get(path, "")
    if row["file_type"] == "documentation":
        reason = (
            "MON-DOC: reviewed documentation prose, examples, or a standalone operational page; "
            "it supports the cited behavior where mapped but does not itself change binaries, "
            "persisted state, or this hop's executable upgrade acceptance path."
        )
    else:
        reason = (
            "MON-TEST: reviewed repository test/QA coverage or fixture maintenance; it supports the "
            "cited behavior where mapped but is not shipped cluster state and is not an executable "
            "acceptance step of this comparison suite."
        )
    if path == "qa/suites/netsplit/tests/mon_pool_ops.yaml":
        reason = (
            "MON-TEST: removes one generic netsplit QA scenario; this changes upstream coverage but "
            "not a validation selector or required acceptance step in the v17.2.7→v18.2.7 suite."
        )
    elif path == "src/test/common/test_mclock_priority_queue.cc":
        reason = (
            "CFG-009 support: removes a common mClock unit test after implementation restructuring; "
            "the scheduler/default runtime impact is owned by CFG-009, not by this test artifact."
        )
    elif path == "qa/standalone/mon/osd-pool-create.sh":
        reason = (
            "MON-TEST: removes a Filestore-only expected_num_objects test; Filestore support and "
            "runtime removal are owned elsewhere, and this test is not a hop acceptance gate."
        )
    return trivial(reason, ids)


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    runtime_paths = {
        row["path"] for row in rows if row["file_type"] == "runtime/source"
    }
    expected_runtime = set(AFFECT) | set(TRIVIAL_RUNTIME)
    if runtime_paths != expected_runtime:
        missing = sorted(runtime_paths - expected_runtime)
        extra = sorted(expected_runtime - runtime_paths)
        raise RuntimeError(
            f"owner 04 runtime row set changed: missing={missing!r}, extra={extra!r}"
        )

    for row in rows:
        path = row["path"]
        if path in AFFECT:
            verdict = AFFECT[path]
        elif path in TRIVIAL_RUNTIME:
            verdict = TRIVIAL_RUNTIME[path]
        elif row["file_type"] in {"documentation", "test/QA"}:
            verdict = support_verdict(row)
        else:
            raise RuntimeError(
                f"owner 04 has an unreviewed row category: {path!r} "
                f"({row['file_type']!r})"
            )
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
        f"Classified owner 04: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
