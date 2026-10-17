#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 02 storage rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "02-bluestore-bluefs.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


BLUESTORE_AFFECT: dict[str, tuple[str, str, str]] = {
    "src/os/bluestore/Allocator.cc": affect(
        "BS-001, BS-005",
        "Changes the fragmentation score and adds a free-extent histogram command; allocator health thresholds and rollout diagnostics therefore use different calculations/output.",
    ),
    "src/os/bluestore/Allocator.h": affect(
        "BS-005",
        "Defines the target free-state histogram buckets and aligned-unit accounting exposed by the new allocator diagnostic command.",
    ),
    "src/os/bluestore/AvlAllocator.cc": affect(
        "BS-001",
        "Stops re-aligning candidate extent starts during allocation; placement, extent selection, and ENOSPC/fragmentation behavior can differ after an OSD runs the target allocator.",
    ),
    "src/os/bluestore/BlueFS.cc": affect(
        "BS-002, BS-005",
        "Changes BlueFS replay accounting, log runway extension/compaction, truncate and release ordering, allocation sizing, discard handling, locking, and counters; mount/replay durability and DB/WAL space behavior differ.",
    ),
    "src/os/bluestore/BlueFS.h": affect(
        "BS-002, BS-005",
        "Changes the BlueFS volume-selector accounting contract, log-extension interface, extent iteration, allocation latency state, and alerts used by the target persistence path.",
    ),
    "src/os/bluestore/BlueRocksEnv.cc": affect(
        "BS-002",
        "Always truncates a RocksDB writable file to its logical position before fsync on close, changing how preallocated BlueFS extents are released and persisted.",
    ),
    "src/os/bluestore/BlueRocksEnv.h": affect(
        "BS-002",
        "Adapts the BlueFS RocksDB environment contract for target path registration and explicitly unsupported reopen/random-RW/truncate operations, affecting DB open compatibility with the target RocksDB API.",
    ),
    "src/os/bluestore/BlueStore.cc": affect(
        "BS-003, BS-004, BS-005",
        "Changes discard/release and fast-shutdown allocator persistence, BlueFS volume selection, device expansion, deferred replay/flush handling, collection listing, shared-blob/statfs accounting, slow-op alerts, and SPDK transport setup.",
    ),
    "src/os/bluestore/BlueStore.h": affect(
        "BS-003, BS-004, BS-005",
        "Carries the target BlueStore lifecycle, cache/mempool, transaction rollback, async compaction, slow-op, and BlueFS volume-selector contracts used by the changed implementation.",
    ),
    "src/os/bluestore/BtreeAllocator.cc": affect(
        "BS-001",
        "Changes candidate alignment and fixes range-tree removal/iterator ordering; free-space selection and reuse can differ for OSDs configured with this allocator.",
    ),
    "src/os/bluestore/StupidAllocator.cc": affect(
        "BS-001",
        "Removes per-candidate alignment adjustment and allocates from the recorded start; allocation success, returned extents, and fragmentation differ for this allocator.",
    ),
    "src/os/bluestore/StupidAllocator.h": affect(
        "BS-001",
        "Removes the aligned-length helper as part of the changed StupidAllocator extent-selection behavior.",
    ),
    "src/os/bluestore/bluefs_types.cc": affect(
        "BS-002",
        "Adds bounded BlueFS transaction sizing used to reserve log runway before encoding and tightens extent seek bounds; replay/log-extension safety changes.",
    ),
    "src/os/bluestore/bluefs_types.h": affect(
        "BS-002",
        "Clears the derived extent index before rebuilding it and exposes bounded transaction sizing, preventing stale offsets and supporting safe log extension.",
    ),
    "src/os/bluestore/bluestore_tool.cc": affect(
        "BS-005",
        "Renames the offline fragmentation action and forces the target volume-selection policy for bluefs-stats; existing automation and diagnostic output paths must be updated.",
    ),
    "src/os/bluestore/bluestore_types.cc": affect(
        "BS-004, BS-005",
        "Moves shared-blob allocations into a dedicated mempool that is included by target cache accounting, changing memory telemetry and autotuning input.",
    ),
    "src/os/bluestore/bluestore_types.h": affect(
        "BS-004",
        "Fixes shared-blob auxiliary lookup bounds while preserving compression-header optional encoding; shared-blob scan/accounting correctness can differ on target.",
    ),
    "src/os/bluestore/fastbmap_allocator_impl.cc": affect(
        "BS-001",
        "Stops rounding a free interval start in the fast bitmap allocator and aligns only its length; selected free extents and allocation success can differ.",
    ),
}


def seastore_verdict(path: str) -> tuple[str, str, str]:
    rel = path.removeprefix("src/crimson/os/seastore/")

    if rel == "logging.h":
        return affect(
            "SS-005",
            "Changes SeaStore log macros to include transaction IDs and removes non-transaction forms; target incident and replay diagnostics have a different schema.",
        )

    if rel in {"seastore.cc", "seastore.h"}:
        return affect(
            "SS-001, SS-002, SS-003, SS-004",
            "Rewires SeaStore mkfs/mount and object operations around grouped devices, new journals, persistent backrefs, extent placement, and cleaner/cache ownership; an existing SeaStore store cannot be assumed in-place compatible.",
        )

    if rel.startswith((
        "backref/",
        "backref_manager",
        "btree/",
        "collection_manager/",
        "lba_manager",
        "omap_manager",
        "onode",
        "root_block",
    )):
        return affect(
            "SS-003",
            "Changes or introduces persistent SeaStore metadata trees, backrefs, root ownership, onode/omap/LBA layout, delta replay, or mutation rules; target mount and metadata compatibility are conditional on this format.",
        )

    if rel.startswith((
        "journal/",
        "journal.",
        "record_scanner",
        "transaction_manager",
    )) or rel in {"transaction.h", "ordering_handle.h"}:
        return affect(
            "SS-002",
            "Changes SeaStore journal format/submission, scan/replay, transaction commit ordering, or trim-tail ownership; crash recovery and restart semantics differ on the target implementation.",
        )

    if rel.startswith((
        "device.",
        "random_block_manager",
        "randomblock_manager_group",
        "segment_manager",
        "segment_seq_allocator",
        "seastore_types",
    )):
        return affect(
            "SS-001",
            "Changes SeaStore device/address/layout abstractions, segment metadata, random-block allocation, or ZNS-to-ZBD backend handling; persisted addresses and device activation differ.",
        )

    if rel.startswith((
        "async_cleaner",
        "cache.",
        "cached_extent",
        "extent_placement_manager",
        "extent_reader",
        "object_data_handler",
        "segment_cleaner",
    )):
        return affect(
            "SS-004",
            "Changes SeaStore cache/extent lifecycle, placement, cleaner/rewrite, or object-data handling; live-space accounting and recovery behavior differ when Crimson SeaStore is deployed.",
        )

    raise RuntimeError(f"owner 02 has an unreviewed SeaStore source row: {path!r}")


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if path in BLUESTORE_AFFECT:
        return BLUESTORE_AFFECT[path]

    if path in {
        "src/os/bluestore/BitmapFreelistManager.cc",
        "src/os/bluestore/HybridAllocator.cc",
        "src/os/bluestore/fastbmap_allocator_impl.h",
    }:
        return trivial(
            "BS-CODE: reviewed C++20 bit-helper/include migration; the power-of-two checks and allocator contract are unchanged, and behavior-changing companion implementation rows are promoted separately."
        )

    if path.startswith("src/os/filestore/"):
        return affect(
            "FILESTORE-001",
            "Deletes a FileStore backend, journal, index, throttle, or xattr implementation from Reef; an OSD still using FileStore has no target backend and must be migrated/reprovisioned before this hop.",
        )

    if path.startswith("src/os/memstore/"):
        return trivial(
            "MEMSTORE-TEST: reviewed debug/test-store logging, failure-injection, and no-op perf-interface plumbing; it does not change the supported BlueStore OSD upgrade path."
        )

    if path.startswith("src/crimson/os/seastore/"):
        return seastore_verdict(path)

    if row["file_type"] == "test/QA":
        return trivial(
            "STORE-TEST: repository unit/fixture/benchmark coverage or removal only; it supports the promoted storage findings but is not an executed acceptance result for this suite."
        )

    raise RuntimeError(f"owner 02 has an unreviewed row: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 220:
        raise RuntimeError(f"owner 02 expected 220 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 02 CSV contains duplicate paths")

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
        f"Classified owner 02: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
