#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 11 CephFS/MDS rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "11-cephfs-mds.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


TRIVIAL_RUNTIME = {
    "src/ceph_mds.cc": "CFS-THREAD: updates the pthread naming helper call only; daemon startup and signal behavior are unchanged.",
    "src/client/SyntheticClient.cc": "CFS-TESTCLIENT: moves synthetic-client thread naming into the spawned thread; production client semantics are unchanged.",
    "src/mds/BatchOp.h": "CFS-CONST: makes the diagnostic print interface const only.",
    "src/mds/Capability.h": "CFS-TYPE: spells an internal capability state word as uint32_t with the same width and encoding.",
    "src/mds/MDSCacheObject.h": "CFS-CONST: makes diagnostic print methods const and inlines the equivalent stream operator.",
    "src/mds/MetricsHandler.cc": "CFS-THREAD: names the metrics updater thread only.",
    "src/mds/OpenFileTable.h": "CFS-TYPE: spells the persisted-count member as uint32_t with the same width.",
    "src/mds/SimpleLock.cc": "CFS-DUMP: changes admin/debug lock dump fields only, not lock state transitions.",
    "src/messages/MMDSScrub.h": "CFS-TYPE: replaces native int/unsigned with equivalent 32-bit wire member types without changing encoding order.",
    "src/messages/MMDSScrubStats.h": "CFS-TYPE: replaces unsigned epoch with equivalent uint32_t wire type.",
    "src/mount/conf.cc": "CFS-CLEANUP: constructs the same monitor address string in one expression.",
}


META_FILES = {
    "src/mds/CDentry.cc", "src/mds/CDentry.h", "src/mds/CDir.cc", "src/mds/CDir.h",
    "src/mds/CInode.cc", "src/mds/CInode.h", "src/mds/SnapRealm.cc", "src/mds/SnapRealm.h",
    "src/mds/mdstypes.cc", "src/mds/mdstypes.h", "src/mds/snap.cc", "src/mds/snap.h",
    "src/mds/events/EMetaBlob.h", "src/mds/fscrypt.h", "src/include/cephfs/types.h",
}

JOURNAL_FILES = {
    "src/mds/DamageTable.cc", "src/mds/DamageTable.h", "src/mds/LogSegment.h",
    "src/mds/MDCache.cc", "src/mds/MDCache.h", "src/mds/MDLog.cc", "src/mds/journal.cc",
    "src/mds/Mutation.cc", "src/mds/Mutation.h", "src/mds/OpenFileTable.cc",
    "src/mds/PurgeQueue.cc", "src/mds/PurgeQueue.h", "src/mds/ScrubStack.cc",
    "src/mds/StrayManager.cc", "src/mds/StrayManager.h",
}

SESSION_FILES = {
    "src/mds/Beacon.cc", "src/mds/Beacon.h", "src/mds/Locker.cc", "src/mds/Locker.h",
    "src/mds/MDSAuthCaps.cc", "src/mds/MDSAuthCaps.h", "src/mds/MDSDaemon.cc",
    "src/mds/MDSDaemon.h", "src/mds/MDSRank.cc", "src/mds/MDSRank.h", "src/mds/Server.cc",
    "src/mds/Server.h", "src/mds/SessionMap.cc", "src/mds/SessionMap.h", "src/mds/locks.c",
    "src/mds/MDSMetaRequest.h",
}

BALANCE_FILES = {
    "src/mds/FSMap.cc", "src/mds/FSMap.h", "src/mds/FSMapUser.cc", "src/mds/FSMapUser.h",
    "src/mds/MDBalancer.cc", "src/mds/MDBalancer.h", "src/mds/MDSMap.cc", "src/mds/MDSMap.h",
    "src/mds/Mantle.cc", "src/mds/Migrator.cc",
}

METRIC_FILES = {
    "src/mds/MetricAggregator.cc", "src/mds/MetricAggregator.h", "src/messages/MMDSBeacon.h",
}

CLIENT_FILES = {
    "src/client/Client.cc", "src/client/Client.h", "src/client/ClientSnapRealm.h",
    "src/client/Dentry.h", "src/client/Inode.cc", "src/client/Inode.h",
    "src/client/MetaRequest.cc", "src/client/MetaRequest.h", "src/client/fuse_ll.cc",
    "src/include/cephfs/libcephfs.h", "src/libcephfs.cc",
    "src/pybind/cephfs/c_cephfs.pxd", "src/pybind/cephfs/cephfs.pyx",
    "src/pybind/cephfs/mock_cephfs.pxi",
}


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if path.startswith("qa/suites/fs/upgrade/"):
        irrelevant_from_selectors = (
            "/tasks/0-from/reef/",
            "/tasks/0-from/pacific.yaml",
            "/tasks/0-from/v16.2.4.yaml",
            "/tasks/0-from/nautilus.yaml",
        )
        if any(marker in path for marker in irrelevant_from_selectors):
            return trivial(
                "CFS-VAL-OTHER: source-version selector belongs to a different CephFS hop; it is not selected for v17.2.7 to v18.2.7."
            )
        return affect(
            "CFSVAL-001",
            "Changes the CephFS Quincy-to-Reef MDS/client upgrade matrix, fail_fs sequencing, mixed client feature eviction, concurrent workload, or final post-upgrade checks; suite source is not an executed exact-tag result.",
        )

    if path.startswith("qa/"):
        return trivial(
            "CFS-QA: component, fscrypt, NFS, mirror, functional, stress, or generic CephFS test source outside the selected exact-hop suite; it was not executed and does not itself change production rollout behavior.",
        )
    if path.startswith("doc/"):
        return trivial(
            "CFS-DOC: documentation/manpage source only; it can describe target behavior but is not the runtime path or an executed upgrade result.",
        )
    if path.startswith("src/test/") or "/tests/" in path:
        return trivial(
            "CFS-UNIT: unit/integration test source only; supporting evidence is not an executed exact-hop acceptance result.",
        )
    if path in TRIVIAL_RUNTIME:
        return trivial(TRIVIAL_RUNTIME[path])

    if path in CLIENT_FILES:
        return affect(
            "CFSCLIENT-001, CFSWIRE-001, CFSSNAP-001, CFSCRYPT-001",
            "Changes libcephfs/FUSE client session feature refresh, request/reply handling, caps/auth, snapshots/snapdiff, fscrypt metadata, quota and public APIs used by mixed-version clients.",
        )
    if path in {
        "src/mount.fuse.ceph", "src/mount/mount.ceph.c",
    }:
        return affect(
            "CFSMOUNT-001",
            "Changes user/kernel mount option parsing and mount-device construction; existing automation must be replayed against the target helper.",
        )

    if path in META_FILES:
        return affect(
            "CFSMETA-001, CFSSNAP-001, CFSCRYPT-001",
            "Changes persisted metadata/cache encoding and replay fields for snaprealm v7, directory entries, inode fscrypt state, damage cleanup, snapshot traces, truncate and rename paths.",
        )
    if path in JOURNAL_FILES:
        return affect(
            "CFSJOURNAL-001",
            "Changes MDS journal open/replay/expiration, metadata cache recovery, truncate, damage/scrub, purge/open-file and stray lifecycle paths exercised by MDS restart/failover.",
        )
    if path in SESSION_FILES:
        return affect(
            "CFSSESSION-001, CFSWIRE-001, CFSFAIL-001",
            "Changes MDS session/cap authorization and reconnect, root_squash feature checks, laggy-OSD eviction deferral, client refusal, rank dispatch and failover behavior.",
        )
    if path in BALANCE_FILES:
        return affect(
            "CFSBAL-001, CFSFAIL-001",
            "Changes FS/MDS map encoding and flags, standby selection, rank mask, fragmentation/export balancing and rank migration used during and after MDS rollout.",
        )
    if path in METRIC_FILES:
        return affect(
            "CFSMETRIC-001",
            "Changes MDS metric aggregation, rank refresh/removal and beacon metric schema/priority used for upgrade observability.",
        )
    if path == "src/mds/cephfs_features.cc" or path == "src/mds/cephfs_features.h":
        return affect(
            "CFSWIRE-001",
            "Adds negotiated CephFS client feature bits for new snaprealm info, owner uid/gid and MDS auth-cap checking; mixed clients do not advertise the same capability set.",
        )
    if path.startswith("src/messages/"):
        return affect(
            "CFSWIRE-001, CFSCRYPT-001, CFSSNAP-001",
            "Changes CephFS client/MDS wire message payloads and feature-gated fields for sessions, requests/replies, caps, fscrypt and snapshot operations.",
        )

    if path.startswith("src/pybind/mgr/nfs/"):
        return affect(
            "CFSNFS-001",
            "Changes NFS cluster/export CLI return contracts, export apply/error aggregation, RADOS discovery and ingress keepalive/PROXY-protocol rendering; existing automation and services require canary validation.",
        )
    if path.startswith("src/pybind/mgr/snap_schedule/"):
        return affect(
            "CFSSCHED-001",
            "Changes the snap-schedule SQLite schema/version, adds group/subvolume path resolution, and changes schedule/retention validation and pruning behavior.",
        )
    if path.startswith("src/pybind/mgr/volumes/"):
        return affect(
            "CFSVOL-001",
            "Changes persisted subvolume metadata/version upgrade gating, clone queue/state/error handling, group deletion, trash/purge locking and volume command behavior.",
        )

    if path.startswith("src/tools/cephfs_mirror/"):
        return affect(
            "CFSMIRROR-001",
            "Changes mirror watcher/blocklist restart timing, peer replay failure propagation and per-filesystem/peer snapshot-sync metrics used by running CephFS mirror daemons.",
        )
    if path in {
        "src/tools/cephfs/DataScan.cc", "src/tools/cephfs/JournalTool.cc",
        "src/tools/cephfs/JournalTool.h", "src/tools/cephfs/first-damage.py",
        "src/tools/cephfs/first-damage.sh",
    }:
        return affect(
            "CFSREPAIR-001",
            "Changes offline/admin CephFS journal, data-scan, and first-damage tooling; only applies when these tools are invoked and must be rehearsed on cloned metadata.",
        )
    if path in {
        "src/tools/cephfs/shell/cephfs-shell", "src/tools/cephfs/top/cephfs-top",
    }:
        return affect(
            "CFSADMIN-001",
            "Changes CephFS operator shell/top commands and observability output used during rollout validation.",
        )

    raise RuntimeError(f"owner 11 has an unreviewed row: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 573:
        raise RuntimeError(f"owner 11 expected 573 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 11 CSV contains duplicate paths")

    for row in rows:
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = verdict(row)

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)

    affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
    trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
    print(f"Classified owner 11: affect={affect_count} trivial={trivial_count} unclassified=0")


if __name__ == "__main__":
    main()
