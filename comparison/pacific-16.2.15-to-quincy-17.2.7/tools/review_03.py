"""Record the reviewed owner-03 endpoint-diff clusters in its component CSV."""

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "03-rocksdb-block-device.csv"

# Each path is covered by the endpoint hunk, responsible commit, and caller
# review described in 03-rocksdb-block-device.md. Keep this explicit so an
# unexpected new row cannot inherit a verdict by path prefix.
REVIEW = {
    "src/blk/BlockDevice.cc": ("affect", "KV-002", "KV-002: device fallback and BlueFS IOContext reap lifecycle differ; inspect no-AIO builds and OSD restart."),
    "src/blk/BlockDevice.h": ("affect", "KV-002", "KV-002/KV-003: IOContext cache flag and zoned-device interface affect block read and SMR activation paths."),
    "src/blk/kernel/KernelDevice.cc": ("affect", "KV-002", "KV-002: read buffers can use configured hugepage pool; open hook, fd selection, and error reporting change OSD block IO."),
    "src/blk/kernel/KernelDevice.h": ("affect", "KV-002", "KV-002/KV-003: custom read alignment and child open/close hooks affect block and zoned-device activation."),
    "src/blk/kernel/io_uring.cc": ("trivial", "", "T03-namespace: hunk only adds std::list/make_unique using declarations; commit is build-without-namespace cleanup, no IO path change."),
    "src/blk/pmem/PMEMDevice.cc": ("trivial", "", "T03-namespace-log: explicit std types and hexdump newline only; PMEM open/read/write behavior unchanged in endpoint hunk."),
    "src/blk/pmem/PMEMDevice.h": ("trivial", "", "T03-namespace: explicit standard headers and std::map qualification only; no PMEM interface or persistence change."),
    "src/blk/spdk/NVMEDevice.cc": ("affect", "KV-002", "KV-002: SPDK completion thread no longer reaps IOContexts; BlueFS now deletes after aio_wait in target."),
    "src/blk/spdk/NVMEDevice.h": ("affect", "KV-002", "KV-002: SPDK queue-count/reap state removed with BlueFS IOContext lifetime change."),
    "src/blk/zoned/HMSMRDevice.cc": ("affect", "KV-003", "KV-003: HMSMR now inherits KernelDevice, opens libzbd in post-open, and changes zone reset/report behavior."),
    "src/blk/zoned/HMSMRDevice.h": ("affect", "KV-003", "KV-003: zoned block interface and KernelDevice inheritance change SMR OSD activation and cleanup."),
    "src/key_value_store/cls_kvs.cc": ("trivial", "", "T03-namespace: commit fixes missing std qualification; endpoint hunk has no class method or OMAP behavior change."),
    "src/key_value_store/key_value_structure.h": ("trivial", "", "T03-namespace: all changed tokens qualify existing string/map/set types; no data format or method logic change."),
    "src/key_value_store/kv_flat_btree_async.cc": ("trivial", "", "T03-namespace: reviewed namespace repair cluster; types/make_pair qualify std with unchanged algorithm and RADOS calls."),
    "src/key_value_store/kv_flat_btree_async.h": ("trivial", "", "T03-namespace: reviewed declarations qualify existing std types; no changed encoding or persisted layout."),
    "src/key_value_store/kvs_arg_types.h": ("trivial", "", "T03-namespace: only std::string/map/set qualification in argument fields; types and wire layout unchanged."),
    "src/kv/KeyValueDB.h": ("affect", "KV-004", "KV-004: empty-prefix iterator now seeks entire DB; diagnostic histogram and any empty-prefix caller can enumerate keys."),
    "src/kv/KeyValueHistogram.cc": ("affect", "KV-004", "KV-004: new histogram computes per-prefix key/value sizes for offline store validation."),
    "src/kv/KeyValueHistogram.h": ("affect", "KV-004", "KV-004: histogram result schema supports new offline KV diagnostic path."),
    "src/kv/MemDB.cc": ("trivial", "", "T03-stdlib: hunk selects std::filesystem rather than experimental fallback in dev-only MemDB; no production store migration path."),
    "src/kv/RocksDBStore.cc": ("affect", "KV-005", "KV-005: approximate-size call drops INCLUDE_FILES flag and RocksDB get counter is removed; capacity/monitoring signals can differ."),
    "src/kv/RocksDBStore.h": ("affect", "KV-005", "KV-005: RocksDB get counter ID removed from perf schema, changing rollout telemetry; remaining hunks qualify std types."),
    "src/kv/rocksdb_cache/BinnedLRUCache.cc": ("affect", "KV-006", "KV-006: age-bin accounting and cache allocation requests change BlueStore/RocksDB memory pressure during stabilization."),
    "src/kv/rocksdb_cache/BinnedLRUCache.h": ("affect", "KV-006", "KV-006: age-bin storage and cache API implement revised memory allocation behavior."),
    "src/kv/rocksdb_cache/ShardedCache.cc": ("affect", "KV-006", "KV-006: cache iteration/deleter support changes RocksDB API integration for active cache."),
    "src/kv/rocksdb_cache/ShardedCache.h": ("affect", "KV-006", "KV-006: import_bins/set_bins called by BlueStore changes priority cache distribution."),
    "src/os/kstore/KStore.cc": ("trivial", "", "T03-comparator: transparent std::less comparator preserves std::string ordering; hunk changes no KStore getattrs body."),
    "src/os/kstore/KStore.h": ("trivial", "", "T03-comparator: getattrs map comparator signature follows ObjectStore interface; no stored attr format change."),
    "src/os/kstore/kstore_types.h": ("trivial", "", "T03-comparator: in-memory attrs map gains transparent comparator; std::string key ordering and encoding remain same."),
    "src/test/cli/ceph-kvstore-tool/help.t": ("trivial", "", "T03-test: CLI expected help gains histogram; corroborates KV-004 but does not alter executed upgrade or acceptance path."),
    "src/test/crimson/test_fixed_kv_node_layout.cc": ("trivial", "", "T03-test: test fixture uses equivalent brace initialization of little-endian fields; runtime layout code unchanged."),
    "src/test/kv_store_bench.cc": ("trivial", "", "T03-test: benchmark adapts argv_to_vec signature; no production KV or upgrade path change."),
    "src/tools/ceph_kvstore_tool.cc": ("affect", "KV-004", "KV-004: CLI exposes histogram on an offline KV store, enabling size-distribution validation during recovery."),
    "src/tools/kvstore_tool.cc": ("affect", "KV-004", "KV-004: histogram iterates KV keys and values to report sizes; tool behavior differs for recovery diagnostics."),
    "src/tools/kvstore_tool.h": ("affect", "KV-004", "KV-004: declares new histogram diagnostic invoked by ceph-kvstore-tool."),
}

with CSV.open(encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
paths = {row["path"] for row in rows}
assert paths == set(REVIEW) | {"src/kv/KeyValueDB.cc", "src/kv/LevelDBStore.cc", "src/kv/LevelDBStore.h"}
for row in rows:
    verdict = REVIEW.get(row["path"])
    if verdict:
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = verdict
with CSV.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
print(Counter(row["upgrade_impact"] for row in rows))
