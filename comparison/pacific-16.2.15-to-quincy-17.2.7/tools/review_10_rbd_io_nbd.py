"""Classify owner-10 RBD core I/O, Python, migration, and NBD deltas."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "10-rados-rbd-clients.csv"
readme_path = root / "README.md"
plan_path = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"


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


def between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def only_in(commit: str, included: str, excluded: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, included, check=False).returncode == 0
    assert git("merge-base", "--is-ancestor", commit, excluded, check=False).returncode != 0


def replace_known(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old in text:
        assert text.count(old) == expected
        text = text.replace(old, new)
        path.write_text(text, encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected


# Endpoint ancestry is checked in both directions because Pacific 16.2.15
# contains several later backports that Quincy 17.2.7 does not contain.
for commit in (
    "2ecd52888b4",  # compare-and-write vector C API
    "9eb2ddbde37",  # make C++ compare-and-write obey len
    "3016e16199e",  # permit stripe-unit compare-and-write and split journals
    "20c0a96ab96",  # invalidate ObjectCacher after compare-and-write
    "4a287e8fcd1",  # make rbd bench I/O counter 64-bit
):
    only_in(commit, "v17.2.7", "v16.2.15")

for commit in (
    "2749dd34f1e",  # preserve object map during diff-iterate
    "0d32001b830",  # do not decode async mirror info on error
    "68637d3e5e5",  # move rbd-nbd resize work out of update callback
):
    only_in(commit, "v16.2.15", "v17.2.7")

base_librbd = show("v16.2.15", "src/librbd/librbd.cc")
target_librbd = show("v17.2.7", "src/librbd/librbd.cc")
assert "static int get_iovec_length" in base_librbd
assert "static int get_iovec_length" in target_librbd
assert "bl.length() < len || cmp_bl.length() < len" not in base_librbd
assert "bl.length() < len || cmp_bl.length() < len" in target_librbd
assert "rbd_aio_compare_and_writev" not in base_librbd
assert "rbd_aio_compare_and_writev" in target_librbd

base_header = show("v16.2.15", "src/include/rbd/librbd.h")
target_header = show("v17.2.7", "src/include/rbd/librbd.h")
assert "LIBRBD_SUPPORTS_COMPARE_AND_WRITE_IOVEC" not in base_header
assert "LIBRBD_SUPPORTS_COMPARE_AND_WRITE_IOVEC" in target_header

base_journal = show("v16.2.15", "src/librbd/Journal.cc")
target_journal = show("v17.2.7", "src/librbd/Journal.cc")
assert "append_compare_and_write_event" not in base_journal
assert "append_compare_and_write_event" in target_journal
assert "max_compare_and_write_data_size /= 2" in target_journal

base_cache = show("v16.2.15", "src/librbd/cache/ObjectCacherObjectDispatch.cc")
target_cache = show("v17.2.7", "src/librbd/cache/ObjectCacherObjectDispatch.cc")
assert "if compare succeeds, discard the cache state" not in base_cache
assert "if compare succeeds, discard the cache state" in target_cache

base_request = show("v16.2.15", "src/librbd/io/ImageRequest.cc")
target_request = show("v17.2.7", "src/librbd/io/ImageRequest.cc")
assert "reflect changes in object_extents back to m_image_extents" in base_request
assert "reflect changes in object_extents back to m_image_extents" in target_request

base_image_ctx = show("v16.2.15", "src/librbd/ImageCtx.h")
target_image_ctx = show("v17.2.7", "src/librbd/ImageCtx.h")
assert "diff_iterate_lock_timestamp" in base_image_ctx
assert "diff_iterate_lock_timestamp" not in target_image_ctx

base_pybind = show("v16.2.15", "src/pybind/rbd/rbd.pyx")
target_pybind = show("v17.2.7", "src/pybind/rbd/rbd.pyx")
base_async_mirror_info = between(
    base_pybind, "def aio_mirror_image_get_info", "def mirror_image_get_mode")
target_async_mirror_info = between(
    target_pybind, "def aio_mirror_image_get_info", "def mirror_image_get_mode")
assert "return_value = _completion_v.get_return_value()" in base_async_mirror_info
assert "return_value = _completion_v.get_return_value()" not in target_async_mirror_info

base_nbd = show("v16.2.15", "src/tools/rbd_nbd/rbd-nbd.cc")
target_nbd = show("v17.2.7", "src/tools/rbd_nbd/rbd-nbd.cc")
assert "handle_notify_thread" in base_nbd
assert "handle_notify_thread" not in target_nbd
assert "--snap-id" not in base_nbd
assert "--snap-id" in target_nbd
assert "--notrim" not in base_nbd
assert "--notrim" in target_nbd

base_bench = show("v16.2.15", "src/tools/rbd/action/Bench.cc")
target_bench = show("v17.2.7", "src/tools/rbd/action/Bench.cc")
assert "unsigned ios = 0;" in base_bench
assert "uint64_t ios = 0;" in target_bench

base_qcow = show("v16.2.15", "src/librbd/migration/QCOWFormat.cc")
target_qcow = show("v17.2.7", "src/librbd/migration/QCOWFormat.cc")
assert "be64toh" in base_qcow
assert "big_to_native" in target_qcow

base_trash = show("v16.2.15", "src/librbd/api/Trash.cc")
target_trash = show("v17.2.7", "src/librbd/api/Trash.cc")
assert "std::experimental::erase_if" in base_trash
assert "std::find_if" in target_trash


affect: dict[str, tuple[str, str]] = {
    "src/include/rbd/librbd.h": (
        "RADOS-012",
        "RADOS-012: Quincy adds the rbd_aio_compare_and_writev C symbol/support macro; consumers built against it cannot roll back to Pacific without a compatibility check, while the compare-and-write implementation also changes request-size and cache/journal behavior.",
    ),
    "src/librbd/Journal.cc": (
        "RADOS-012",
        "RADOS-012: Quincy journals compare-and-write as dedicated, size-bounded entries and splits compare/write payloads, enabling aligned requests up to the stripe unit instead of the Pacific single-sector limit.",
    ),
    "src/librbd/Journal.h": (
        "RADOS-012",
        "RADOS-012: the internal journal contract gains append_compare_and_write_event and changes event extent tracking to support larger compare-and-write requests; this is part of the runtime behavior change, not a header-only cleanup.",
    ),
    "src/librbd/cache/ObjectCacherObjectDispatch.cc": (
        "RADOS-012",
        "RADOS-012: after a successful OSD-side compare-and-write, Quincy discards the overlapping ObjectCacher state; Pacific can retain stale cached data under writeback or writethrough cache policy.",
    ),
    "src/librbd/io/ImageRequest.h": (
        "RADOS-012",
        "RADOS-012: Quincy changes the internal request contract to slice both compare and write buffers by the requested extent and to append size-bounded compare-and-write journal events; the up-to-date snap-context fix is already present at both endpoints under different backports.",
    ),
    "src/librbd/io/ImageRequest.cc": (
        "RADOS-012",
        "RADOS-012: Quincy slices compare and write buffers by len, permits aligned compare-and-write up to the stripe unit and emits split journal entries. The snap-context and adjusted-discard journal fixes are already present at both endpoints under different backports.",
    ),
    "src/librbd/librbd.cc": (
        "RADOS-012",
        "RADOS-012: Quincy makes C++ compare-and-write validate the compare buffer and honor len, and implements the new vector C API; Pacific already has the iovec-overflow fix under a different backport SHA, so that logic is intentionally excluded.",
    ),
    "src/librbd/ImageCtx.h": (
        "RADOS-004",
        "RADOS-004: Quincy lacks Pacific's later diff-iterate object-map preservation backport, including the ImageCtx lock timestamp used by that path; this row belongs to the existing snapshot-diff regression finding rather than namespace/allocator cleanup.",
    ),
    "src/pybind/rbd/rbd.pyx": (
        "RADOS-013",
        "RADOS-013: Pacific checks the async mirror-info completion result before decoding; Quincy lacks that backport and may decode invalid memory on errors such as client blocklisting instead of returning info=None.",
    ),
    "src/tools/rbd_nbd/rbd-nbd.cc": (
        "RADOS-014",
        "RADOS-014: Quincy lacks Pacific's backport that moves image resize inspection out of the update-watch callback; disabling an image feature while mapped through rbd-nbd can deadlock in refresh_if_required. New snap-id/notrim options are secondary opt-in additions.",
    ),
    "src/tools/rbd/action/Bench.cc": (
        "RADOS-015",
        "RADOS-015: Quincy changes the rbd bench operation counter from unsigned to uint64_t, preventing wraparound after more than 2^32 I/Os and changing long-run operation/IOPS reporting used for performance validation.",
    ),
}

trivial_reasons: dict[str, str] = {
    "src/cls/cas/cls_cas_internal.h": "RADOS-MECH-28: std qualification and string-literal scoping only; CAS reference encoding, masks, counters, and serialized bytes are unchanged.",
    "src/cls/lock/cls_lock_ops.cc": "RADOS-MECH-28: adds explicit std type imports only; lock test-instance values and encode/dump behavior are unchanged.",
    "src/cls/test_remote_reads/cls_test_remote_reads.cc": "RADOS-TEST-29: adds a test/example object class used to exercise remote reads; it is not an existing production RBD/RADOS data or rollout path.",
    "src/include/rbd/librbd.hpp": "RADOS-DOC-30: adds documentation for the corrected C++ compare-and-write contract but no C++ declaration, symbol, or executable behavior in this row; runtime changes are RADOS-012.",
    "src/librbd/BlockGuard.h": "RADOS-MECH-28: changes std qualification and diagnostic formatting of a block extent only; overlap comparison, detention, and release logic are identical.",
    "src/librbd/api/Mirror.cc": "RADOS-MECH-28: endpoint hunks only qualify map/vector/string with std; mirror enable/disable, peer, and status control flow are unchanged.",
    "src/librbd/api/Trash.cc": "RADOS-EQUIV-31: replaces erase_if plus first() with find_if for the same interrupted user trash-move predicate; the selected image id and error paths are equivalent.",
    "src/librbd/migration/QCOWFormat.cc": "RADOS-EQUIV-31: replaces platform beXXtoh calls with boost::endian big_to_native; QCOW header, snapshot and lookup-table values undergo the same big-endian conversion.",
    "src/librbd/operation/TrimRequest.cc": "RADOS-MECH-28: std qualification and a range-for rewrite only; the same boundary extents are expanded and dispatched for discard.",
    "src/rbd_replay/Replayer.cc": "RADOS-MECH-28: std qualification only; replay scheduling, dependency waits, trace decoding and I/O execution are unchanged.",
    "src/tools/rbd/action/Nbd.cc": "RADOS-CLI-32: forwards the new opt-in --snap-id selector and reorganizes argument construction; existing name/device map, unmap, attach and detach defaults are unchanged.",
    "src/tools/rbd/action/Snap.cc": "RADOS-MECH-28: std qualification only; snapshot listing, creation, protection and purge behavior are unchanged.",
    "src/tools/rbd_wnbd/rbd_wnbd.cc": "RADOS-CLI-32: improves a Windows map error message and adopts the new argv adapter/std imports; WNBD mapping and I/O behavior are unchanged at the endpoints.",
    "src/tools/rbd_wnbd/wnbd_handler.cc": "RADOS-ADAPTER-33: adapts the synchronous AdminSocket hook to the added input-buffer parameter, which is unused; stats retrieval and WNBD dispatch are unchanged.",
    "src/tools/rbd_wnbd/wnbd_handler.h": "RADOS-ADAPTER-33: declaration-only counterpart of the AdminSocket input-buffer signature adaptation; no WNBD data-path behavior changes.",
}

expected = set(affect) | set(trivial_reasons)
assert len(affect) == 11
assert len(trivial_reasons) == 15
assert len(expected) == 26

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert expected <= set(by_path)

# Preserve later batches and fail rather than overwriting a conflicting verdict.
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
totals = (affect_count, trivial_count, blank_count)
assert totals in {
    (48, 135, 137), (48, 188, 84), (48, 257, 15), (58, 262, 0)
}
if totals == (48, 135, 137):
    replace_known(
        readme_path,
        "1.411 hàng `affect`. 1.357 hàng `trivial`. 1.411 hàng chưa phân loại.",
        "1.422 hàng `affect`. 1.372 hàng `trivial`. 1.385 hàng chưa phân loại.",
    )
    replace_known(readme_path, "RADOS-001–011", "RADOS-001–015", expected=2)
    replace_known(
        readme_path,
        "libcryptsetup và quan sát `dirty-cache`",
        "libcryptsetup, quan sát `dirty-cache`, compare-and-write, lỗi Python async mirror-info, deadlock `rbd-nbd` và bộ đếm benchmark",
    )
    replace_known(
        readme_path,
        "minimum libcryptsetup và output `dirty-cache`",
        "minimum libcryptsetup, output `dirty-cache`, compare-and-write, lỗi Python async mirror-info, deadlock `rbd-nbd` và bộ đếm benchmark",
    )
    replace_known(readme_path, "vì 1.411 hàng còn thiếu nhãn và lý do",
                  "vì 1.385 hàng còn thiếu nhãn và lý do")
    replace_known(
        plan_path,
        "`affect 1.411`, `trivial 1.357`, còn **1.411 hàng chưa phân loại**",
        "`affect 1.422`, `trivial 1.372`, còn **1.385 hàng chưa phân loại**",
    )
    replace_known(
        plan_path,
        "owner 10 hiện `37 affect`, `120 trivial`, `163` chưa phân loại",
        "owner 10 hiện `48 affect`, `135 trivial`, `137` chưa phân loại",
    )
print("Classified owner-10 core I/O/Python/NBD batch: 11 affect, 15 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
