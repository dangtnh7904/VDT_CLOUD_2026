"""Classify owner-10 client API, snapshot-diff, QoS, and mechanical deltas."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "10-rados-rbd-clients.csv"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, path: str) -> str:
    return git("show", f"{tag}:{path}").stdout


def only_in(commit: str, included: str, excluded: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, included, check=False).returncode == 0
    assert git("merge-base", "--is-ancestor", commit, excluded, check=False).returncode != 0


# Pacific contains post-Quincy fixes that disappear at the requested target.
for commit in (
    "319ada6774d5e6f4fdf0b06eace63da7f82941b7",  # reliable selfmanaged-snap query
    "32d4a7a620c2ed73e649d94755117c1dfc9b7b95",  # no new hole vs hole
    "df8ecf3dda1b6b6eaa79f8f82f5470c0c4e2cc2b",  # valid end_size only
    "d2ee564a78f480b3261338bbab67fac418de6e3a",  # whole-object fallback
    "10a45d3a5e17e811f5737dad2ffcf18a2f3dcbae",  # whole-object flag semantics
):
    only_in(commit, "v16.2.15", "v17.2.7")

# Quincy-only client features retained in the endpoint.
for commit in (
    "da5d4c813ff",  # Python iterator uses explicit string lengths
    "0ea387dd941",  # public sparse_read truncate_size/truncate_seq arguments
    "e87e1806d86",  # per-operation QoS exclusion
):
    only_in(commit, "v17.2.7", "v16.2.15")

base_python = show("v16.2.15", "src/pybind/rados/rados.pyx")
target_python = show("v17.2.7", "src/pybind/rados/rados.pyx")
assert "rados_nobjects_list_next(self.ctx" in base_python
assert "decode_cstr(key_)" in base_python
assert "rados_nobjects_list_next2(self.ctx" in target_python
assert "decode_cstr(key_[:key_size_])" in target_python

base_hpp = show("v16.2.15", "src/include/rados/librados.hpp")
target_hpp = show("v17.2.7", "src/include/rados/librados.hpp")
assert "int pool_is_in_selfmanaged_snaps_mode" in base_hpp
assert "int pool_is_in_selfmanaged_snaps_mode" not in target_hpp
assert "uint64_t truncate_size = 0" not in base_hpp
assert "uint64_t truncate_size = 0" in target_hpp

base_client = show("v16.2.15", "src/librados/RadosClient.cc")
target_client = show("v17.2.7", "src/librados/RadosClient.cc")
assert "int r = wait_for_osdmap();" in base_client
assert "return -ENOENT;" in base_client
assert "bool librados::RadosClient::get_pool_is_selfmanaged_snaps_mode" in target_client
assert "if (poolid >= 0)" in target_client

base_rados_tool = show("v16.2.15", "src/tools/rados/rados.cc")
target_rados_tool = show("v17.2.7", "src/tools/rados/rados.cc")
assert "failed to query pool " in base_rados_tool
assert "failed to query pool " not in target_rados_tool
assert "get_pool_is_selfmanaged_snaps_mode(src_pool)" in target_rados_tool

base_snap_diff = show("v16.2.15", "src/librados/snap_set_diff.cc")
target_snap_diff = show("v17.2.7", "src/librados/snap_set_diff.cc")
assert base_snap_diff.index("if (end <= b)") < base_snap_diff.index("*end_size = r->size;")
assert target_snap_diff.index("*end_size = r->size;") < target_snap_diff.index("if (end < a)")
assert "ran out of clones before reaching end" in base_snap_diff
assert "ran out of clones before reaching end" not in target_snap_diff

target_image_ctx = show("v17.2.7", "src/librbd/ImageCtx.cc")
target_qos = show("v17.2.7", "src/librbd/io/QosImageDispatch.cc")
target_io_ops = show("v17.2.7", "src/librbd/io/IoOperations.cc")
assert "rbd_qos_exclude_ops" in target_image_ctx
for operation in ("READ", "WRITE", "DISCARD", "WRITE_SAME", "COMPARE_AND_WRITE"):
    assert f"m_qos_exclude_ops & RBD_IO_OPERATION_{operation}" in target_qos
assert "rbd_io_operations_from_string" in target_io_ops
assert "RBD_IO_OPERATION_NAME_COMPARE_AND_WRITE" in target_io_ops


affect: dict[str, tuple[str, str]] = {}

for path in (
    "src/librados/snap_set_diff.cc",
    "src/librbd/io/ObjectRequest.cc",
    "src/librbd/deep_copy/ImageCopyRequest.cc",
):
    affect[path] = (
        "RADOS-004",
        "RADOS-004: Pacific has later snapshot-delta/fast-diff fixes that are absent from Quincy 17.2.7, including correct non-existence, end-size and whole-object handling. Diff/export-diff or deep-copy can therefore report or copy different extents after client replacement.",
    )

for path in ("src/pybind/rados/c_rados.pxd", "src/pybind/rados/rados.pyx"):
    affect[path] = (
        "RADOS-005",
        "RADOS-005: Quincy Python rados ObjectIterator switches to rados_nobjects_list_next2 and explicit lengths, preserving embedded NUL bytes in object, locator and namespace strings instead of truncating at the first NUL.",
    )

selfmanaged_reason = (
    "RADOS-006: Pacific backports the error-returning pool_is_in_selfmanaged_snaps_mode API and makes rados cppool/mksnap wait for an OSDMap and fail on query errors. Quincy 17.2.7 lacks that symbol and can collapse a fresh-map or missing-pool error to false."
)
for path in (
    "src/librados/RadosClient.cc",
    "src/librados/RadosClient.h",
    "src/tools/rados/rados.cc",
):
    affect[path] = ("RADOS-006", selfmanaged_reason)

affect["src/include/rados/librados.hpp"] = (
    "RADOS-006;RADOS-007",
    "RADOS-006;RADOS-007: Quincy removes Pacific's error-returning selfmanaged-snapshot query and changes ObjectReadOperation::sparse_read from five to seven C++ parameters (the new two have source defaults), removing the Pacific mangled symbols expected by already-built clients.",
)
affect["src/librados/librados_cxx.cc"] = (
    "RADOS-006;RADOS-007",
    "RADOS-006;RADOS-007: implementation drops the reliable int selfmanaged-snapshot method and exports only the seven-argument sparse_read wrapper, so Pacific-built C++ clients using either Pacific symbol require rebuild or compatibility verification.",
)

qos_reason = (
    "RADOS-008: Quincy implements rbd_qos_exclude_ops; selected read/write/discard/write-same/compare-and-write operations bypass configured RBD token-bucket QoS. Pacific throttles those operations because the option and dispatch mask do not exist."
)
for path in (
    "src/librbd/ImageCtx.cc",
    "src/librbd/io/ImageDispatcher.cc",
    "src/librbd/io/ImageDispatcher.h",
    "src/librbd/io/ImageDispatcherInterface.h",
    "src/librbd/io/QosImageDispatch.cc",
    "src/librbd/io/QosImageDispatch.h",
    "src/librbd/io/IoOperations.cc",
    "src/librbd/io/IoOperations.h",
    "src/librbd/io/Types.h",
):
    affect[path] = ("RADOS-008", qos_reason)


namespace_or_include = {
    "src/cls/timeindex/cls_timeindex_types.cc",
    "src/librados/IoCtxImpl.cc",
    "src/librados/IoCtxImpl.h",
    "src/librados/librados_c.cc",
    "src/libradosstriper/RadosStriperImpl.cc",
    "src/libradosstriper/RadosStriperImpl.h",
    "src/librbd/AsyncObjectThrottle.cc",
    "src/librbd/Utils.cc",
    "src/librbd/Watcher.h",
    "src/librbd/api/PoolMetadata.h",
    "src/librbd/cache/ObjectCacherWriteback.cc",
    "src/librbd/image/CreateRequest.cc",
    "src/librbd/managed_lock/ReleaseRequest.cc",
    "src/librbd/object_map/ResizeRequest.h",
    "src/librbd/operation/Request.h",
    "src/librbd/operation/SnapshotRemoveRequest.cc",
    "src/osdc/Journaler.cc",
    "src/rbd_replay/actions.cc",
    "src/tools/immutable_object_cache/Types.cc",
}

equivalent_api = {
    "src/include/rados/librados.h",
    "src/librbd/crypto/BlockCrypto.cc",
    "src/librbd/managed_lock/BreakRequest.cc",
    "src/librbd/operation/ResizeRequest.cc",
    "src/neorados/RADOS.cc",
}

diagnostic_or_adapter = {
    "src/librbd/ImageWatcher.cc",
    "src/librbd/LibrbdAdminSocketHook.cc",
    "src/librbd/LibrbdAdminSocketHook.h",
    "src/librbd/image_watcher/NotifyLockOwner.cc",
}

binding_support = {
    "src/pybind/rados/mock_rados.pxi",
    "src/pybind/rados/setup.py",
    "src/pybind/rbd/setup.py",
}

trivial_reasons: dict[str, str] = {}
for path in namespace_or_include:
    trivial_reasons[path] = (
        "RADOS-MECH-09: endpoint hunk only qualifies standard-library names, removes an unused declaration/include, or adds a direct include; the executed branch, serialized data and client-visible result are unchanged."
    )
for path in equivalent_api:
    trivial_reasons[path] = (
        "RADOS-MECH-10: endpoint hunk substitutes an equivalent constant/constructor/parse or optional spelling (plus comments where present); values and control flow remain the same in this row."
    )
for path in diagnostic_or_adapter:
    trivial_reasons[path] = (
        "RADOS-MECH-11: adds debug logging or adapts to the AdminSocket bufferlist parameter without consuming it; no RBD state transition or I/O result changes."
    )
for path in binding_support:
    trivial_reasons[path] = (
        "RADOS-BINDING-SUPPORT-12: Python build/mock support only (future-print removal or mock declaration matching next2); production iterator behavior is classified separately as RADOS-005."
    )

expected = set(affect) | set(trivial_reasons)
assert len(affect) == 19
assert len(trivial_reasons) == 31
assert len(expected) == 50

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert expected <= set(by_path)

# Idempotence also protects classifications from accidental later overwrite.
for path, (finding_id, reason) in affect.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == finding_id
        assert row["impact_reason"] == reason
for path, reason in trivial_reasons.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial"
        assert not row["finding_id"]
        assert row["impact_reason"] == reason

for path, (finding_id, reason) in affect.items():
    row = by_path[path]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = finding_id
    row["impact_reason"] = reason

for path, reason in trivial_reasons.items():
    row = by_path[path]
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert (affect_count, trivial_count, blank_count) == (31, 89, 200)
print("Classified owner-10 client API/QoS batch: 19 affect, 31 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
