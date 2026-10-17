#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 10 RADOS/RBD client rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "10-rados-rbd-clients.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


AFFECT_EXACT: dict[str, tuple[str, str, str]] = {
    "src/include/rados/rgw_file.h": affect(
        "RADOSAPI-001",
        "Changes the public rgw_readdir callback return type from bool to int; external rgw_file clients must rebuild against the target header/ABI contract.",
    ),
    "src/include/rados/librados.h": affect(
        "RADOSAPI-001",
        "Adds nanosecond stat/write-operation entry points to the public C API while retaining legacy symbols; target-built clients can exercise a different timestamp contract.",
    ),
    "src/include/rados/librados.hpp": affect(
        "RADOSAPI-001",
        "Deprecates the boolean self-managed-snapshot query and adds an error-returning replacement, changing how target-built clients distinguish a missing pool from false.",
    ),
    "src/librados/RadosClient.cc": affect(
        "RADOSAPI-001",
        "Waits for the OSD map and returns explicit pool lookup errors for the target self-managed-snapshot query instead of collapsing them to false.",
    ),
    "src/librados/RadosClient.h": affect(
        "RADOSAPI-001",
        "Carries the error-returning self-managed-snapshot query used by the public target C++ client API.",
    ),
    "src/librados/librados_asio.h": affect(
        "RADOSAPI-001",
        "Changes Boost.Asio completion signatures to include object version and uses the generic error category; source consumers must adapt before rebuilding target clients.",
    ),
    "src/librados/librados_c.cc": affect(
        "RADOSAPI-001",
        "Implements the new nanosecond stat and write-operation APIs used by target-built librados clients while preserving the legacy entry points.",
    ),
    "src/librados/librados_cxx.cc": affect(
        "RADOSAPI-001",
        "Exposes explicit errors for the target self-managed-snapshot pool query; callers no longer need to infer missing-pool state from a boolean.",
    ),
    "src/librados/snap_set_diff.cc": affect(
        "RBDDIFF-001",
        "Changes snapshot-set diff boundaries across truncation and missing end clones; backup or validation callers can receive different extents for the same snapshot chain.",
    ),
    "src/libradosstriper/libradosstriper.cc": affect(
        "RADOSAPI-001",
        "Adds nanosecond stat entry points to libradosstriper, extending the target client ABI used by rebuilt striper consumers.",
    ),
    "src/include/rbd/librbd.h": affect(
        "RBDAPI-001, RBDDIFF-001, RBDCRYPT-001",
        "Raises the librbd API minor level and adds diff-by-snapshot-id plus generic/multi-spec encryption interfaces consumed by target clients and mapping tools.",
    ),
    "src/include/rbd/librbd.hpp": affect(
        "RBDAPI-001, RBDDIFF-001, RBDCRYPT-001",
        "Exposes the target C++ diff flags and multi-spec encryption contract used for parent-aware encrypted clones.",
    ),
    "src/librbd/Operations.cc": affect(
        "RBDAPI-001, RBDCRYPT-001",
        "Stops suppressing several idempotent operation errors and translates resize/flatten extents around crypto headers; existing automation can observe new return codes.",
    ),
    "src/librbd/api/Group.cc": affect(
        "RBDAPI-001",
        "Changes group/group-snapshot ID generation and rejects rollback when current membership differs from the completed group snapshot.",
    ),
    "src/librbd/api/Namespace.cc": affect(
        "RBDAPI-001",
        "Creates the namespace trash object during namespace initialization and rolls it back on failure, changing initialization prerequisites and failure cleanup.",
    ),
    "src/librbd/api/Pool.cc": affect(
        "RBDAPI-001",
        "Creates the RBD trash object during pool initialization; target rbd pool init can now fail at this additional step.",
    ),
    "src/librbd/api/Snapshot.cc": affect(
        "RBDAPI-001",
        "Returns ENOENT rather than asserting when a requested snapshot timestamp is absent, changing an existing error path visible to clients.",
    ),
    "src/librbd/api/Mirror.cc": affect(
        "RBDMIRROR-001",
        "Reads peer configuration from the default namespace for status summaries, fixing namespace-scoped mirror status and changing reported state.",
    ),
    "src/librbd/api/Trash.cc": affect(
        "RBDDIFF-001",
        "Routes trash purge allocation accounting through the new snapshot-ID diff engine; purge estimates inherit its target extent semantics.",
    ),
    "src/librbd/api/Utils.cc": affect(
        "RBDCRYPT-001",
        "Constructs generic auto-detect LUKS encryption formats and preserves per-format passphrases for the target multi-layer load path.",
    ),
    "src/librbd/librbd.cc": affect(
        "RBDAPI-001, RBDDIFF-001, RBDCRYPT-001",
        "Changes close lifecycle ordering and implements snapshot-ID diff plus multi-spec encryption entry points while retaining legacy wrappers.",
    ),
    "src/osdc/Objecter.cc": affect(
        "RADOSOBS-001",
        "Adds client-side OSD operation latency and in-flight counters used to judge target client health during mixed-version rollout.",
    ),
    "src/pybind/rados/rados.pyx": affect(
        "RADOSAPI-001",
        "Allows byte OMAP keys and changes iterator decoding selection in the Python binding; target applications can observe different key types.",
    ),
    "src/pybind/rbd/c_rbd.pxd": affect(
        "RBDAPI-001, RBDDIFF-001, RBDCRYPT-001",
        "Binds the target clone-format, diff-by-ID, and multi-spec encryption C interfaces into Python.",
    ),
    "src/pybind/rbd/rbd.pyx": affect(
        "RBDAPI-001, RBDDIFF-001, RBDCRYPT-001, RBDMIG-001",
        "Adds clone/flatten migration controls, snapshot-ID diff, generic multi-layer LUKS loading, and safe async mirror-info error handling to the Python API.",
    ),
    "src/pybind/rbd/setup.py": affect(
        "RBDPKG-001",
        "Imports packaging.version and adapts Cython 3 noexcept behavior; building the target Python binding requires the matching packaging/Cython environment.",
    ),
    "src/tools/immutable_object_cache/main.cc": affect(
        "RBDCACHE-001",
        "Corrects the immutable-object-cache process exit status, changing service-manager failure detection and restart behavior.",
    ),
    "src/tools/rados/rados.cc": affect(
        "RADOSCLI-001",
        "Changes existing rados command behavior and output paths used for object-level maintenance and client validation.",
    ),
    "src/tools/rbd/action/Bench.cc": affect(
        "RBDCLI-001",
        "Seeds the random workload before constructing the benchmark helper, changing target rbd bench access patterns used in validation.",
    ),
    "src/tools/rbd/action/MirrorImage.cc": affect(
        "RBDMIRROR-001, RBDCLI-001",
        "Uses the active namespace context for mirror peer lookup in image status, changing namespace-scoped CLI output.",
    ),
    "src/tools/rbd/action/MirrorPool.cc": affect(
        "RBDMIRROR-001, RBDCLI-001",
        "Changes pool mirror peer and site command paths used to prepare, inspect, or repair replication during the upgrade.",
    ),
}


TRIVIAL_EXACT: dict[str, str] = {
    "src/cls/cas/cls_cas_internal.h": "RADOS-MECH: initializes a local decode temporary; persisted encoding and upgrade behavior are unchanged.",
    "src/cls/rbd/cls_rbd.cc": "RBD-VARIANT: std::variant migration only; class method decisions and encoded snapshot namespace remain unchanged.",
    "src/cls/rbd/cls_rbd_types.cc": "RBD-VARIANT: replaces Boost visitation with std::variant visitation while retaining the versioned on-disk encoding.",
    "src/cls/rbd/cls_rbd_types.h": "RBD-VARIANT: in-memory variant/comparison modernization; no new on-disk feature bit or encoding version is introduced.",
    "src/cls/user/cls_user.cc": "CLS-ERROR: moves an output marker assignment after successful persistence; the method already returns an error when that persistence fails.",
    "src/librados/IoCtxImpl.cc": "RADOS-MECH: switches to the equivalent internal FULL_FORCE flag spelling for remove operations.",
    "src/librados/ListObjectImpl.h": "RADOS-MECH: replaces generated comparison operators with the C++20 default comparison.",
    "src/libradosstriper/RadosStriperImpl.cc": "RADOS-MECH: removes an unnecessary constructor template qualification with no runtime change.",
    "src/librbd/ExclusiveLock.cc": "RBD-LOG: debug log punctuation only.",
    "src/librbd/ImageWatcher.cc": "RBD-VARIANT: log formatting and std::variant access only; force-promotion selection is unchanged.",
    "src/librbd/ManagedLock.cc": "RBD-LOG: debug log formatting only.",
    "src/librbd/Utils.cc": "RBD-COMMENT: explanatory comment only.",
    "src/librbd/api/Migration.cc": "RBD-MECH: removes unreachable cleanup code after an existing direct return.",
    "src/librbd/cache/pwl/AbstractWriteLog.cc": "RBD-MECH: adapts to the target perf-dump function signature without changing cache I/O.",
    "src/librbd/io/ReadResult.cc": "RBD-MECH: passes an extent vector by const reference instead of by value.",
    "src/librbd/io/ReadResult.h": "RBD-MECH: declaration companion for the const-reference change.",
    "src/librbd/migration/FileStream.cc": "RBD-LOG: migration file-stream error wording only.",
    "src/librbd/migration/RawSnapshot.cc": "RBD-LOG: adds punctuation to an existing migration error message.",
    "src/librbd/migration/S3Stream.cc": "RBD-BUILD: removes local fmt header-only macros; runtime migration semantics are unchanged by this row.",
    "src/librbd/mirror/GetInfoRequest.cc": "RBD-VARIANT: std::variant access only; promotion-state logic is unchanged.",
    "src/librbd/mirror/snapshot/CreatePrimaryRequest.cc": "RBD-VARIANT: std::variant access only; snapshot-peer unlink logic is unchanged.",
    "src/librbd/mirror/snapshot/UnlinkPeerRequest.cc": "RBD-VARIANT: std::variant access only; mirror snapshot selection is unchanged.",
    "src/librbd/mirror/snapshot/Utils.cc": "RBD-VARIANT: std::variant access and equivalent guards only; promotion eligibility is unchanged.",
    "src/librbd/object_map/LockRequest.cc": "RBD-MODELINE: editor modeline changes C to C++ only.",
    "src/librbd/object_map/LockRequest.h": "RBD-MODELINE: editor modeline changes C to C++ only.",
    "src/librbd/object_map/RefreshRequest.cc": "RBD-MODELINE: editor modeline changes C to C++ only.",
    "src/librbd/object_map/RefreshRequest.h": "RBD-MODELINE: editor modeline changes C to C++ only.",
    "src/librbd/object_map/UnlockRequest.cc": "RBD-MODELINE: editor modeline changes C to C++ only.",
    "src/librbd/object_map/UnlockRequest.h": "RBD-MODELINE: editor modeline changes C to C++ only.",
    "src/librbd/operation/SnapshotCreateRequest.cc": "RBD-VARIANT: std::variant access only; mirror image-state creation conditions are unchanged.",
    "src/librbd/operation/SnapshotRemoveRequest.cc": "RBD-VARIANT: std::variant access only; mirror image-state removal conditions are unchanged.",
    "src/neorados/RADOS.cc": "RADOS-MECH: imports standard literal operators only.",
    "src/osdc/Striper.cc": "RADOS-ASSERT: reorders zero-length buffer assertions without changing non-empty striped read assembly.",
    "src/pybind/rbd/mock_rbd.pxi": "RBD-TEST: generated/mock binding support only; production Python calls are classified separately.",
    "src/tools/rbd/action/Rename.cc": "RBD-HELP: command help wording only.",
    "src/tools/rbd_ggate/ggate_drv.c": "RBD-MODELINE: editor modeline changes C to C++ only.",
    "src/tools/rbd_ggate/ggate_drv.h": "RBD-MODELINE: editor modeline changes C to C++ only.",
    "src/tools/rbd_mirror/image_replayer/snapshot/ApplyImageStateRequest.cc": "RBD-VARIANT: std::variant access only; snapshot state application is unchanged.",
    "src/tools/rbd_mirror/image_replayer/snapshot/Utils.cc": "RBD-VARIANT: std::variant access only; remote snapshot ID selection is unchanged.",
}


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if path in AFFECT_EXACT:
        return AFFECT_EXACT[path]
    if path in TRIVIAL_EXACT:
        return trivial(TRIVIAL_EXACT[path])

    if path.startswith("doc/"):
        return trivial(
            "RBD-DOC: documentation-only row; it describes target client behavior but does not execute or validate this upgrade."
        )
    if path.startswith("qa/"):
        return trivial(
            "RBD-QA: QA task or workunit only; it supports nearby findings but is not an executed acceptance result for this comparison."
        )
    if path.startswith("src/test/"):
        return trivial(
            "RBD-TEST: unit/integration fixture or test code only; it was inspected as evidence but is not a production path or a recorded test result."
        )

    if path.startswith("src/librbd/crypto/"):
        return affect(
            "RBDCRYPT-001",
            "Reworks the active encryption dispatch/load/format path for generic LUKS detection, ancestor-specific credentials, crypto-header areas, or encrypted clone flattening.",
        )
    if path.startswith("src/librbd/object_map/") or path.startswith(
        "src/librbd/api/DiffIterate"
    ):
        return affect(
            "RBDDIFF-001",
            "Changes fast-diff object-range calculation, object-map locking/state, or parent extent reporting used by backups, copies, and allocation validation.",
        )
    if path.startswith("src/librbd/migration/"):
        return affect(
            "RBDMIG-001",
            "Changes an active migration source, stream, format, or dispatch path; prepared/imported images can be read or materialized differently on the target client.",
        )
    if path.startswith("src/librbd/deep_copy/"):
        return affect(
            "RBDMIG-001, RBDCRYPT-001",
            "Changes deep-copy object/parent extent handling for snapshot ranges and encrypted image areas, affecting copy or migration results.",
        )
    if path.startswith("src/librbd/io/"):
        return affect(
            "RBDIO-001, RBDCRYPT-001",
            "Changes live image/object dispatch, copyup, parent overlap, or area mapping so data and crypto-header extents take the target I/O path.",
        )
    if path.startswith("src/librbd/cache/"):
        return affect(
            "RBDCACHE-001, RBDCRYPT-001",
            "Changes active cache/writeback handling for parent reads, persistent write-log buffers, or crypto-header bypass behavior.",
        )
    if path.startswith("src/librbd/journal/"):
        return affect(
            "RBDIO-001, RBDMIRROR-001",
            "Changes journal event extent handling or replay used by live clients and journal-based mirroring.",
        )
    if path in {
        "src/librbd/ImageCtx.cc",
        "src/librbd/ImageCtx.h",
        "src/librbd/Journal.cc",
        "src/librbd/Journal.h",
        "src/librbd/ObjectMap.cc",
        "src/librbd/ObjectMap.h",
        "src/librbd/internal.cc",
        "src/librbd/internal.h",
    }:
        return affect(
            "RBDIO-001, RBDCRYPT-001",
            "Changes core image size/area, parent overlap, journal, object-map, or close/read semantics exercised by existing target librbd clients.",
        )
    if path == "src/librbd/api/Image.cc" or path == "src/librbd/api/Image.h":
        return affect(
            "RBDCRYPT-001, RBDAPI-001",
            "Changes encryption format/load behavior for cloned images and multi-layer credentials in the public image API.",
        )
    if path == "src/librbd/api/Io.cc":
        return affect(
            "RBDIO-001, RBDCRYPT-001",
            "Routes all public image I/O through explicit DATA-area mapping, separating client data from target crypto headers.",
        )
    if path.startswith("src/librbd/operation/FlattenRequest"):
        return affect(
            "RBDCRYPT-001, RBDMIG-001",
            "Adds format-specific crypto-header flattening after data copyup for encrypted clones.",
        )
    if path in {
        "src/librbd/operation/SparsifyRequest.cc",
        "src/librbd/operation/TrimRequest.cc",
    }:
        return affect(
            "RBDIO-001, RBDCRYPT-001",
            "Changes sparsify/shrink parent-overlap decisions so crypto headers and data areas are not trimmed or removed incorrectly.",
        )
    if path.startswith("src/tools/rbd_mirror/"):
        return affect(
            "RBDMIRROR-001",
            "Changes active rbd-mirror peer reconciliation, namespace handling, replay synchronization, callouts, or labeled performance counters.",
        )
    if path.startswith("src/tools/rbd_nbd/"):
        return affect(
            "RBDMAP-001, RBDCRYPT-001",
            "Changes Linux NBD mapping defaults, resize handling, netlink identity, and multi-passphrase encrypted clone loading.",
        )
    if path.startswith("src/tools/rbd_wnbd/"):
        return affect(
            "RBDMAP-001",
            "Changes Windows mapping/service lifecycle, error signs, resize watch handling, and optional adapter recovery monitoring.",
        )
    if path.startswith("src/tools/rbd/action/") or path.startswith(
        "src/tools/rbd/ArgumentTypes"
    ) or path.startswith("src/tools/rbd/Utils"):
        ids = "RBDCLI-001"
        if "Encryption" in path:
            ids += ", RBDCRYPT-001"
        return affect(
            ids,
            "Changes an existing rbd CLI argument, validation, or action path used to inspect or mutate images during maintenance.",
        )

    raise RuntimeError(f"owner 10 has an unreviewed row: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 421:
        raise RuntimeError(f"owner 10 expected 421 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 10 CSV contains duplicate paths")

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
        f"Classified owner 10: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
