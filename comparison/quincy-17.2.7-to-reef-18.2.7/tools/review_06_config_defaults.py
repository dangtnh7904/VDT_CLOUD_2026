#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 06 config/default rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "06-config-defaults.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str, ids: str = "") -> tuple[str, str, str]:
    return "trivial", ids, reason


VERDICTS = {
    "doc/rados/configuration/bluestore-config-ref.rst": trivial(
        "CFG-DOC-001: corrects the reshard example and documents SPDK transport syntax; "
        "the document is supporting evidence and does not itself change daemon or rollout behavior."
    ),
    "doc/rados/configuration/ceph-conf.rst": trivial(
        "CFG-DOC-002: editorial clarification of configuration concepts only; no option, "
        "command, executable recipe, or acceptance path changes in this file."
    ),
    "doc/rados/configuration/common.rst": trivial(
        "CFG-DOC-003: removes obsolete Filestore setup prose and tightens device wording; "
        "runtime support is established by code/package rows owned elsewhere."
    ),
    "doc/rados/configuration/demo-ceph.conf": trivial(
        "CFG-DOC-004: repairs invalid sample key spelling and updates the illustrative PG "
        "autoscaling example; this documentation fixture is not consumed by deployment code."
    ),
    "doc/rados/configuration/filestore-config-ref.rst": trivial(
        "CFG-DOC-005: documents that Filestore is unsupported in Reef and fixes a confval "
        "name; it supports the storage finding but does not independently remove the backend."
    ),
    "doc/rados/configuration/journal-ref.rst": trivial(
        "CFG-DOC-006: adds a Filestore deprecation warning only; no executable upgrade or "
        "validation step is changed by the hunk."
    ),
    "doc/rados/configuration/mclock-config-ref.rst": trivial(
        "CFG-009 support: explains the new HDD shard/thread defaults and low IOPS thresholds, "
        "while the effective values and scheduler behavior come from runtime option/code rows.",
        "CFG-009",
    ),
    "doc/rados/configuration/mon-config-ref.rst": trivial(
        "CFG-DOC-007: grammar, underscore-form examples, and a stale confval reference change "
        "only; no monitor configuration value is changed here."
    ),
    "doc/rados/configuration/mon-lookup-dns.rst": trivial(
        "CFG-DOC-008: documents an alternate SRV lookup name and adds a cross-link; this page "
        "does not implement or execute discovery during the upgrade."
    ),
    "doc/rados/configuration/mon-osd-interaction.rst": trivial(
        "CFG-DOC-009: fixes one index typo with no configuration or runtime effect."
    ),
    "doc/rados/configuration/msgr2.rst": trivial(
        "CFG-DOC-010: removes a stale Quincy dual-stack limitation note; the hunk contains no "
        "protocol, bind default, or executable validation change."
    ),
    "doc/rados/configuration/network-config-ref.rst": trivial(
        "CFG-DOC-011: corrects firewall guidance to the already-configured 6800:7568 range and "
        "removes stale prose; the runtime bind option itself is unchanged in this row."
    ),
    "doc/rados/configuration/osd-config-ref.rst": trivial(
        "CFG-009 support: documents scrub and mClock worker behavior but does not independently "
        "change OSD scheduling, recovery, or acceptance execution.",
        "CFG-009",
    ),
    "doc/rados/configuration/pool-pg-config-ref.rst": trivial(
        "CFG-DOC-012: restructures PG configuration guidance and sample commands; it is not an "
        "upgrade recipe executed by the suite and changes no pool automatically."
    ),
    "doc/rados/configuration/pool-pg.conf": trivial(
        "CFG-DOC-013: fixes sample option spelling and removes redundant pgp_num guidance; the "
        "literal include is documentation, not a deployed configuration artifact."
    ),
    "doc/rados/configuration/storage-devices.rst": trivial(
        "CFG-DOC-014: adds a Filestore warning only; actual backend availability is owned and "
        "validated outside this documentation row."
    ),
    "src/common/config_cacher.h": trivial(
        "CFG-001 support: moves the tracked key from a function-local static array to each "
        "cacher instance; the exact endpoint has only size_t and bool instantiations, so no "
        "same-template key collision is present in this tree.",
        "CFG-001",
    ),
    "src/common/config_obs_mgr.h": affect(
        "CFG-001",
        "Observer registrations change from raw pointers to shared/weak lifetime tokens and "
        "removal returns a weak token; this participates in the target's wait-until-callback-"
        "release contract for dynamic config observers.",
    ),
    "src/common/config_proxy.h": affect(
        "CFG-001",
        "ConfigProxy replaces the recursive-lock/CallGate design with mutex-protected observer "
        "collection, callbacks outside the lock, and condition-variable removal waits; daemon "
        "config reload and observer teardown concurrency therefore differs after restart."
    ),
    "src/common/options.h": trivial(
        "CFG-CODE-001: adds Option::str_to_level, but the exact v18.2.7 tree has no caller of "
        "this helper; option values, validation, and update semantics are unchanged by this row."
    ),
    "src/common/options/cephfs-mirror.yaml.in": affect(
        "CFG-002",
        "Adds cephfs_mirror_perf_stats_prio with default 5; target mirror code uses it for new "
        "filesystem, peer, byte, latency, and failure counters, changing rollout observability "
        "when CephFS mirroring is deployed."
    ),
    "src/common/options/crimson.yaml.in": affect(
        "CFG-003",
        "Changes the SeaStore device-size default from 100 GiB to 50 GiB and adds startup SMP, "
        "transaction-concurrency, device-type, journal, and tiering controls; Crimson/SeaStore "
        "creation and restart behavior is conditionally different."
    ),
    "src/common/options/global.yaml.in": affect(
        "CFG-004, CFG-005",
        "Changes effective global defaults/contracts used by normal daemons: BlueStore RocksDB "
        "options, discard workers and health alerts, OSD compression method selection, and "
        "requested-scrub priority; these activate on restart or the named feature path."
    ),
    "src/common/options/mds-client.yaml.in": affect(
        "CFG-006",
        "Marks client_dirsize_rbytes startup-only while its value still controls CephFS stat "
        "semantics; old and target clients can therefore react differently to a live config "
        "change during a rolling client upgrade."
    ),
    "src/common/options/mds.yaml.in": affect(
        "CFG-007",
        "Drops per-MDS mds_max_xattr_pairs_size as target MDS code reads MDSMap max_xattr_size, "
        "and adds prefetch/laggy-OSD controls; a custom old key must be reconciled before MDS "
        "rank movement to avoid a mixed-version xattr-limit change."
    ),
    "src/common/options/mon.yaml.in": affect(
        "CFG-008",
        "Removes separate file/syslog cluster-log level keys and adds mon_cluster_log_level; "
        "stored old overrides no longer control target MON log filtering, which can change "
        "upgrade diagnostics and alert input after monitor restart."
    ),
    "src/common/options/osd.yaml.in": affect(
        "CFG-009",
        "Changes HDD mClock layout from five shards/one worker to one shard/five workers, raises "
        "default concurrent scrubs from one to three, reduces deep-scrub chunk maximum, and adds "
        "reservation/low-capacity gates; recovery and scrub behavior changes on target restart."
    ),
    "src/common/options/rbd.yaml.in": trivial(
        "CFG-RBD-001: replaces isp2 with the equivalent std::has_single_bit validator and changes "
        "rbd_validate_pool's documentation level from advanced to dev; accepted values and RBD "
        "runtime behavior remain unchanged."
    ),
    "src/common/options/rgw.yaml.in": affect(
        "CFG-010",
        "Changes RGW defaults used by target code: ops logging moves from RADOS to a daemon file, "
        "data-change notifications default from 200 ms to disabled, LDAP placeholder becomes "
        "empty, and policy validation defaults to rejecting invalid principals."
    ),
}


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    paths = {row["path"] for row in rows}
    if paths != set(VERDICTS):
        missing = sorted(paths - set(VERDICTS))
        extra = sorted(set(VERDICTS) - paths)
        raise RuntimeError(f"owner 06 row set changed: missing={missing!r}, extra={extra!r}")

    for row in rows:
        impact, finding_id, reason = VERDICTS[row["path"]]
        row["upgrade_impact"] = impact
        row["finding_id"] = finding_id
        row["impact_reason"] = reason

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
        f"Classified owner 06: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
