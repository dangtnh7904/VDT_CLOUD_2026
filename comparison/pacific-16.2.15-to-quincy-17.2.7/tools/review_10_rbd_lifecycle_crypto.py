"""Classify owner-10 RBD lifecycle, crypto, cls/rbd, and CLI deltas."""

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


# These commits explain the remaining endpoint differences. Several other
# Quincy commits inspected for this batch are already present in Pacific under
# different backport SHAs, so they are intentionally excluded here.
for commit in (
    "c210005ea62",  # honor the requested snapshot namespace internally
    "8de47b212ba",  # require libcryptsetup >= 2.0.5
    "72a5993da70",  # fixed-width sparse_size on wire/notify paths
    "b2a8d13a1a4",  # expose dirty-cache in rbd info
):
    only_in(commit, "v17.2.7", "v16.2.15")

base_image = show("v16.2.15", "src/librbd/api/Image.cc")
target_image = show("v17.2.7", "src/librbd/api/Image.cc")
assert "get_snap_id(cls::rbd::UserSnapshotNamespace{}" in base_image
assert "get_snap_id(snap_namespace, snap_name)" in target_image
# All endpoint callers of the namespace-taking internal overload pass the user
# namespace; public callers using non-user snapshots select by id instead.
for text in (base_image, target_image):
    assert "io::FLUSH_SOURCE_INTERNAL" in text
    assert "spec.state == cls::rbd::TRASH_IMAGE_STATE_MOVING" in text
snap_callers = git(
    "grep", "-n", "api::Image<>::snap_set", "v17.2.7", "--", "src"
).stdout.splitlines()
assert snap_callers
assert all(
    "src/librbd/librbd.cc" in line or "src/test/" in line
    for line in snap_callers
)
target_librbd = show("v17.2.7", "src/librbd/librbd.cc")
assert target_librbd.count("cls::rbd::UserSnapshotNamespace(), snap_name") >= 2

base_internal = show("v16.2.15", "src/librbd/internal.cc")
target_internal = show("v17.2.7", "src/librbd/internal.cc")
assert "io::FLUSH_SOURCE_INTERNAL" in base_internal
assert "io::FLUSH_SOURCE_INTERNAL" in target_internal

base_crypto_pool = show("v16.2.15", "src/librbd/crypto/CryptoContextPool.h")
target_crypto_pool = show("v17.2.7", "src/librbd/crypto/CryptoContextPool.h")
assert "get_key_length() const override" in base_crypto_pool
assert "get_key_length() const override" in target_crypto_pool
assert "get_key() const override" in target_crypto_pool

base_header = show("v16.2.15", "src/librbd/crypto/luks/Header.cc")
target_header = show("v17.2.7", "src/librbd/crypto/luks/Header.cc")
assert "LIBCRYPTSETUP_LEGACY_DATA_ALIGNMENT" in base_header
assert "LIBCRYPTSETUP_LEGACY_DATA_ALIGNMENT" not in target_header
assert "crypt_format(\n          m_cd, type, alg, cipher_mode, NULL, key" in base_header
assert "crypt_format(\n          m_cd, type, alg, cipher_mode, NULL, key" in target_header

base_cls = show("v16.2.15", "src/cls/rbd/cls_rbd.cc")
target_cls = show("v17.2.7", "src/cls/rbd/cls_rbd.cc")
assert "size_t sparse_size;" in base_cls
assert "uint64_t sparse_size;" in target_cls
assert "last_read = vals.rbegin()->first;" in base_cls
assert "last_read = vals.rbegin()->first;" in target_cls
assert "mirror_image.state != cls::rbd::MIRROR_IMAGE_STATE_ENABLED" in base_cls
assert "mirror_image.state != cls::rbd::MIRROR_IMAGE_STATE_ENABLED" in target_cls

base_watch = show("v16.2.15", "src/librbd/WatchNotifyTypes.h")
target_watch = show("v17.2.7", "src/librbd/WatchNotifyTypes.h")
assert "size_t sparse_size = 0;" in base_watch
assert "uint64_t sparse_size = 0;" in target_watch

base_trash = show("v16.2.15", "src/tools/rbd/action/Trash.cc")
target_trash = show("v17.2.7", "src/tools/rbd/action/Trash.cc")
assert "rbd.trash_purge_with_progress" in base_trash
assert "rbd.trash_purge_with_progress" in target_trash
assert "pc.fail();\n    return r;" in base_trash
assert "pc.fail();\n    return r;" in target_trash

base_kernel = show("v16.2.15", "src/tools/rbd/action/Kernel.cc")
target_kernel = show("v17.2.7", "src/tools/rbd/action/Kernel.cc")
assert "image.config_list(&options);" in base_kernel
assert "image.config_list(&options);" in target_kernel
assert "const char *endptr;" in base_kernel
assert "const char *endptr;" not in target_kernel

base_args = show("v16.2.15", "src/tools/rbd/ArgumentTypes.cc")
target_args = show("v17.2.7", "src/tools/rbd/ArgumentTypes.cc")
assert "RBD_FEATURE_DIRTY_CACHE" not in base_args
assert "RBD_FEATURE_DIRTY_CACHE" in target_args


affect: dict[str, tuple[str, str]] = {
    "src/librbd/crypto/luks/Header.cc": (
        "RADOS-010",
        "RADOS-010: Quincy drops the legacy libcryptsetup alignment branch and always expresses LUKS data alignment in 512-byte sectors, paired with a build minimum of libcryptsetup 2.0.5; custom delivery against older libraries is no longer supported.",
    ),
    "src/cls/rbd/cls_rbd.cc": (
        "RADOS-009",
        "RADOS-009: Quincy decodes cls/rbd sparsify sparse_size as uint64_t instead of architecture-sized size_t, stabilizing the object-class wire field for 32-bit/64-bit interoperability; the other endpoint hunk is log wording only.",
    ),
    "src/cls/rbd/cls_rbd_client.cc": (
        "RADOS-009",
        "RADOS-009: Quincy cls/rbd client wrappers encode sparsify sparse_size as uint64_t instead of size_t, matching the fixed-width object-class decoder across architectures.",
    ),
    "src/cls/rbd/cls_rbd_client.h": (
        "RADOS-009",
        "RADOS-009: cls/rbd sparsify declarations change sparse_size from architecture-sized size_t to uint64_t, aligning callers with the fixed-width encoded field and changing the internal C++ signature.",
    ),
    "src/librbd/WatchNotifyTypes.h": (
        "RADOS-009",
        "RADOS-009: SparsifyPayload changes its encoded field and constructor from size_t to uint64_t, making notify payload width stable across 32-bit and 64-bit RBD clients.",
    ),
    "src/tools/rbd/ArgumentTypes.cc": (
        "RADOS-011",
        "RADOS-011: Quincy includes RBD_FEATURE_DIRTY_CACHE in the feature mapping used by rbd info/help; Pacific omits it, so feature inventory and scripts parsing that output receive a different validation signal after client replacement.",
    ),
}

mechanical = {
    "src/cls/lua/cls_lua.cc",
    "src/librbd/api/Namespace.cc",
    "src/cls/cas/cls_cas_internal.cc",
    "src/librbd/api/Image.cc",
    "src/librbd/internal.h",
    "src/librbd/internal.cc",
    "src/librbd/cache/ParentCacheObjectDispatch.cc",
    "src/librbd/crypto/CryptoContextPool.h",
    "src/tools/rbd/action/MergeDiff.cc",
    "src/tools/rbd/action/List.cc",
    "src/librbd/api/Snapshot.cc",
    "src/librbd/api/Group.cc",
    "src/tools/rados/RadosImport.cc",
    "src/rbd_replay/rbd-replay.cc",
    "src/tools/rados/PoolDump.cc",
    "src/tools/immutable_object_cache/main.cc",
    "src/tools/immutable_object_cache/ObjectCacheStore.cc",
    "src/tools/immutable_object_cache/ObjectCacheStore.h",
    "src/tools/rbd/action/Import.cc",
    "src/librbd/journal/Types.h",
    "src/osdc/Journaler.h",
    "src/tools/rbd_ggate/main.cc",
    "src/tools/rbd/Utils.cc",
}
cli_nonupgrade = {
    "src/tools/rbd/action/Copy.cc",
    "src/tools/rbd/action/Device.cc",
    "src/tools/rbd/Shell.cc",
    "src/tools/rbd/action/Kernel.cc",
    "src/tools/rbd/action/Trash.cc",
}

trivial_reasons: dict[str, str] = {}
for path in mechanical:
    trivial_reasons[path] = (
        "RADOS-MECH-20: endpoint hunk is std namespace/include/filesystem/argv adapter cleanup, an equivalent parser/comparator, a typo, or a helper move; serialized values and executed RBD/RADOS behavior are unchanged in this row."
    )
for path in cli_nonupgrade:
    trivial_reasons[path] = (
        "RADOS-CLI-21: optional CLI options/help text or command-dispatch/front-end fixes add convenience without changing existing image data, defaults, wire compatibility, or an established rollout/rollback path; the feature-inventory exception is RADOS-011."
    )
trivial_reasons["src/librbd/api/Image.cc"] = (
    "RADOS-INTERNAL-25: the internal name-based snap_set overload now honors its namespace parameter, but every endpoint production caller reaches it through librbd.cc with UserSnapshotNamespace; non-user selection uses the id overload, so no reachable endpoint upgrade path was demonstrated."
)
trivial_reasons["src/tools/rbd/action/Kernel.cc"] = (
    "RADOS-PARSE-26: replaces the end-pointer entity_addr_t parse with the full-string string_view overload; both reject trailing input and return the same normalized address, while map-option/default logic is identical at the endpoints."
)
trivial_reasons["src/tools/rbd/action/Trash.cc"] = (
    "RADOS-CLI-27: only prints the requested non-'now' trash expiration after a successful move; purge/remove return paths and persistent trash state are identical at the two endpoints."
)
trivial_reasons["src/cls/rbd/cls_rbd.h"] = (
    "RADOS-DUMP-22: adds snapshot namespace and timestamp only to the developer/test Formatter dump; on-disk encode/decode versions and production snapshot metadata are unchanged by this row."
)
trivial_reasons["src/tools/rbd/action/Export.cc"] = (
    "RADOS-EXPORT-23: corrects the declared format-2 protection-record length from 8 to 1 and adds switch recognition, but the paired exporter/importer already writes and reads one bool byte regardless of that length; the commit explicitly documents the endpoint bug as harmless."
)
trivial_reasons["src/tools/rbd/action/Create.cc"] = (
    "RADOS-CREATE-24: removes a redundant process-local rbd_discard_on_zeroed_write_same override after thick provisioning switched to RBD_WRITE_ZEROES_FLAG_THICK_PROVISION; final allocation semantics and persistent config are unchanged."
)

expected = set(affect) | set(trivial_reasons)
assert len(affect) == 6
assert len(trivial_reasons) == 31
assert len(expected) == 37

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
assert (affect_count, trivial_count, blank_count) == (37, 120, 163)
print("Classified owner-10 lifecycle/crypto/cls/CLI batch: 6 affect, 31 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
