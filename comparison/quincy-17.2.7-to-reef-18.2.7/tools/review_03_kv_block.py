#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 03 KV/block-device rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "03-rocksdb-block-device.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str, ids: str = "") -> tuple[str, str, str]:
    return "trivial", ids, reason


VERDICTS = {
    "src/blk/BlockDevice.cc": affect(
        "KV-002, KV-003, KV-004",
        "Block-device endpoint behavior adds dynamic discard/queue interfaces, stalled-read "
        "health alerts and extended-device state; these alter OSD I/O execution and stop/go "
        "observability when the corresponding config/device path is active.",
    ),
    "src/blk/BlockDevice.h": affect(
        "KV-002, KV-003, KV-004",
        "Public BlockDevice contracts change for discard, stalled-read alerts and external "
        "block-device state, feeding BlueStore/BlueFS callers during restart and operation.",
    ),
    "src/blk/aio/aio.cc": affect(
        "KV-001",
        "AIO submission is rewritten to chunk libaio work by max_iodepth and retry partial "
        "submissions; the exact target POSIX-AIO branch also contains a syntax error and "
        "changes the single-entry call from aio_read to aio_write.",
    ),
    "src/blk/aio/aio.h": affect(
        "KV-001",
        "The submit_batch contract drops the uint16_t size argument and is part of the AIO "
        "submission behavior change exercised by each block-device implementation.",
    ),
    "src/blk/kernel/KernelDevice.cc": affect(
        "KV-001, KV-002, KV-003, KV-004",
        "KernelDevice changes AIO submission, runtime discard thread management, VDO/plugin "
        "state, and stalled-read event generation; all lie on the normal BlueStore block path.",
    ),
    "src/blk/kernel/KernelDevice.h": affect(
        "KV-001, KV-002, KV-003, KV-004",
        "KernelDevice state and interfaces now include config-observed discard workers and an "
        "external block-device plugin reference, supporting runtime behavior changed in the cc file.",
    ),
    "src/blk/kernel/io_uring.cc": affect(
        "KV-001",
        "io_uring adopts the new submit_batch contract used by KernelDevice; this is part of "
        "the target block-I/O submission cluster even though the local hunk is a signature update.",
    ),
    "src/blk/kernel/io_uring.h": affect(
        "KV-001",
        "io_uring declaration changes with the block-I/O submission contract and must match "
        "the target artifact selected for an OSD.",
    ),
    "src/blk/pmem/PMEMDevice.cc": affect(
        "KV-005",
        "Target detects devdax character devices, changes pmem mapping flags/metadata, and uses "
        "DML copy operations when built with libdml; PMEM open/read/write behavior is conditional "
        "on device type and build feature.",
    ),
    "src/blk/pmem/PMEMDevice.h": affect(
        "KV-005",
        "PMEMDevice tracks devdax state and disables supported_bdev_label for that device type, "
        "changing activation/label assumptions for a PMEM-backed OSD.",
    ),
    "src/blk/spdk/NVMEDevice.cc": affect(
        "KV-006",
        "Target accepts non-PCIe SPDK transports, configures keep-alive and processes admin "
        "completions in a dedicated thread; SPDK attach and lifecycle differ for remote NVMe.",
    ),
    "src/blk/zoned/HMSMRDevice.h": trivial(
        "KV-002 support: the old zoned-device discard override returned success without issuing "
        "I/O; after its removal the new base try_discard returns false, so this header hunk alone "
        "preserves the no-discard outcome and only adapts the interface.",
        "KV-002",
    ),
    "src/kv/KeyValueDB.cc": affect(
        "KV-007",
        "Target removes the memdb factory and test-init branches, so a configured/experimental "
        "memdb backend can no longer be created after replacing the binary.",
    ),
    "src/kv/MemDB.cc": affect(
        "KV-007",
        "The complete MemDB implementation is deleted; this is backend removal rather than a "
        "mechanical refactor and changes restart/open capability when memdb was selected.",
    ),
    "src/kv/MemDB.h": affect(
        "KV-007",
        "The complete MemDB type and transaction/iterator contracts are deleted together with "
        "the factory path, establishing removal of the experimental backend.",
    ),
    "src/kv/RocksDBStore.cc": affect(
        "KV-008",
        "Compact-on-deletion collector placement moves from column-family options to DB options "
        "while the default remains enabled, and compaction counters are replaced; compaction "
        "behavior and rollout observability can differ after restart.",
    ),
    "src/kv/RocksDBStore.h": affect(
        "KV-008",
        "RocksDB perf-counter schema changes from compact_range to running/completed/last-duration, "
        "which can break monitoring and stop/go queries across mixed OSD cohorts.",
    ),
    "src/os/kstore/KStore.cc": affect(
        "KV-009",
        "Target optionally throws and unwinds the queued transaction instead of aborting on "
        "submission failure when objectstore_debug_throw_on_failed_txc is enabled, changing the "
        "failure-injection/validation path for KStore.",
    ),
    "src/os/kstore/KStore.h": affect(
        "KV-009",
        "KStore adds undo_queue required by the target exception path; the remaining formatter "
        "and compact signature edits are supporting interface changes in the same file.",
    ),
    "src/test/kv_store_bench.cc": trivial(
        "KV-BENCH-001: moves selected std names into the implementation after removal of a header "
        "using-directive; benchmark workload and acceptance behavior are unchanged.",
    ),
    "src/test/kv_store_bench.h": trivial(
        "KV-BENCH-001: replaces header-wide using-directives with explicit std/ceph qualifications; "
        "types and benchmark operations remain equivalent.",
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
        raise RuntimeError(f"owner 03 row set changed: missing={missing!r}, extra={extra!r}")

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
        f"Classified owner 03: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
