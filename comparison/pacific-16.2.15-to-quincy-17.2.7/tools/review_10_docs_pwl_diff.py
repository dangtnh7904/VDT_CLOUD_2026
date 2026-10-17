"""Classify RBD documentation, PWL endpoint deltas, and fast-diff behavior."""

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


# Quincy-side PWL fixes retained in the endpoint.
for commit in (
    "c4c4f7e763beeaf9d234d00ea198629e078ab1d5",
    "3407262de6e1b567c70ffe87b278f1d02b3683b2",
    "265cedbf360f4b87ee73b26ef16b19c3921e032b",
):
    only_in(commit, "v17.2.7", "v16.2.15")

# Later Pacific backports that are absent from the older Quincy endpoint.
for commit in (
    "2749dd34f1edddd33ba9b8c3d522d7df0e52eb90",
    "78bf5b166c33341316eda2065d58779ca0027d89",
    "557be66f34617cea0600755afa3ee45a40b54bb3",
    "a08c7da7dcc0e7f754f5e224c5cf79e25f097d71",
    "0c98b16b7933276c56c8be896cf72e3eb35df7e3",
    "79ff4c63fac378345885c70a793fb0b3697a1819",
):
    only_in(commit, "v16.2.15", "v17.2.7")

base_pwl = show("v16.2.15", "src/librbd/cache/pwl/AbstractWriteLog.cc")
target_pwl = show("v17.2.7", "src/librbd/cache/pwl/AbstractWriteLog.cc")
assert "aligned_read_bl.substr_of" in base_pwl
assert "sub_cmp_bl.substr_of(cw_req->cmp_bl, 0, cw_req->read_bl.length())" in target_pwl
assert "ceph_assert(cw_req->read_bl.length() <= cw_req->cmp_bl.length())" in target_pwl

base_rwl = show("v16.2.15", "src/librbd/cache/pwl/rwl/WriteLog.cc")
target_rwl = show("v17.2.7", "src/librbd/cache/pwl/rwl/WriteLog.cc")
assert base_rwl.index("auto entry = m_log_entries.front();") < base_rwl.index(
    "while (!m_log_entries.empty()"
)
assert "this->can_retire_entry(m_log_entries.front())" in target_rwl
assert "err_close_pool:" not in base_rwl
assert "err_close_pool:" in target_rwl
assert "pmemobj_close(m_log_pool);" in target_rwl

base_diff = show("v16.2.15", "src/librbd/api/DiffIterate.cc")
target_diff = show("v17.2.7", "src/librbd/api/DiffIterate.cc")
assert "calc_object_diff_range" in base_diff
assert "calc_object_diff_range" not in target_diff
assert "parent_extents[0].first" in base_diff
assert "DiffIterate diff_parent(*m_image_ctx.parent, {}, nullptr, 0, overlap" in target_diff

base_request = show("v16.2.15", "src/librbd/object_map/DiffRequest.cc")
target_request = show("v17.2.7", "src/librbd/object_map/DiffRequest.cc")
assert "m_start_object_no" in base_request
assert "m_start_object_no" not in target_request
assert "allow intermediate snaps to be skipped" not in target_request
assert "is_diff_iterate()" in base_request
assert "is_diff_iterate()" not in target_request

man_docs = {
    "doc/man/8/ceph-rbdnamer.rst",
    "doc/man/8/rbd-fuse.rst",
    "doc/man/8/rbd-ggate.rst",
    "doc/man/8/rbd-mirror.rst",
    "doc/man/8/rbd-nbd.rst",
    "doc/man/8/rbd-replay-many.rst",
    "doc/man/8/rbd-replay-prep.rst",
    "doc/man/8/rbd-replay.rst",
    "doc/man/8/rbd.rst",
    "doc/man/8/rbdmap.rst",
}
api_docs = {
    "doc/rados/api/index.rst",
    "doc/rados/api/librados-intro.rst",
    "doc/rados/api/objclass-sdk.rst",
    "doc/rados/api/python.rst",
    "doc/rbd/api/librbdpy.rst",
}
admin_docs = {
    "doc/rbd/iscsi-initiator-linux.rst",
    "doc/rbd/iscsi-initiators.rst",
    "doc/rbd/iscsi-target-ansible.rst",
    "doc/rbd/iscsi-target-cli-manual-install.rst",
    "doc/rbd/iscsi-target-cli.rst",
    "doc/rbd/rbd-config-ref.rst",
    "doc/rbd/rbd-encryption.rst",
    "doc/rbd/rbd-exclusive-locks.rst",
    "doc/rbd/rbd-integrations.rst",
    "doc/rbd/rbd-kubernetes.rst",
    "doc/rbd/rbd-mirroring.rst",
    "doc/rbd/rbd-nomad.rst",
    "doc/rbd/rbd-openstack.rst",
    "doc/rbd/rbd-operations.rst",
    "doc/rbd/rbd-persistent-write-log-cache.rst",
    "doc/rbd/rbd-snapshot.rst",
    "doc/rbd/rbd-windows.rst",
}
assert len(man_docs) == 10 and len(api_docs) == 5 and len(admin_docs) == 17

pwl_affect = {
    "src/librbd/cache/pwl/AbstractWriteLog.cc": (
        "RADOS-002",
        "RADOS-002: Quincy PWL compare-and-write compares the read extent against an equal-length prefix of the compare buffer and bounds mismatch scanning; Pacific uses a conditional aligned-read buffer and can follow different match/mismatch behavior when lengths differ.",
    ),
    "src/librbd/cache/pwl/rwl/WriteLog.cc": (
        "RADOS-003",
        "RADOS-003: Quincy RWL retirement checks m_log_entries before front() and closes the PMEM pool on initialization/layout errors; Pacific can dereference an empty list or retain the opened pool on those failure paths.",
    ),
}

pwl_trivial = {
    "src/librbd/cache/pwl/DiscardRequest.cc",
    "src/librbd/cache/pwl/ImageCacheState.cc",
    "src/librbd/cache/pwl/LogEntry.cc",
    "src/librbd/cache/pwl/LogMap.cc",
    "src/librbd/cache/pwl/LogOperation.cc",
    "src/librbd/cache/pwl/Request.cc",
    "src/librbd/cache/pwl/Request.h",
    "src/librbd/cache/pwl/SyncPoint.cc",
    "src/librbd/cache/pwl/Types.cc",
    "src/librbd/cache/pwl/Types.h",
    "src/librbd/cache/pwl/rwl/Request.cc",
    "src/librbd/cache/pwl/ssd/Request.cc",
    "src/librbd/cache/pwl/ssd/Types.h",
    "src/librbd/cache/pwl/ssd/WriteLog.cc",
}
assert len(pwl_trivial) == 14

fast_diff_affect = {
    "src/librbd/ObjectMap.h",
    "src/librbd/api/DiffIterate.cc",
    "src/librbd/api/DiffIterate.h",
    "src/librbd/object_map/DiffRequest.cc",
    "src/librbd/object_map/DiffRequest.h",
    "src/librbd/object_map/Types.h",
}
fast_diff_reason = (
    "RADOS-004: Pacific 16.2.15 contains later fast-diff backports for ranged and parent diff, grown/shrunk images and intermediate snapshots that are absent from Quincy 17.2.7. The same RBD image can therefore produce a different diff extent/state set after client replacement."
)

support_tests = {
    "src/test/librbd/cache/pwl/test_WriteLogMap.cc",
    "src/test/librbd/object_map/test_mock_DiffRequest.cc",
}

trivial_reasons = {}
for path in man_docs:
    trivial_reasons[path] = (
        "RADOS-DOC-MAN-01: RST man-page text documents commands/options or updates links; it is not executed by the upgrade, and the corresponding CLI/runtime source is screened separately."
    )
for path in api_docs:
    trivial_reasons[path] = (
        "RADOS-DOC-API-02: API documentation/sample prose only; no exported symbol, binding implementation, package input or runtime acceptance recipe changes in this row."
    )
for path in admin_docs:
    trivial_reasons[path] = (
        "RADOS-DOC-ADMIN-03: RBD/iSCSI/integration/configuration guidance only. It may explain target features but is not an executed Pacific-to-Quincy upgrade recipe; implementation differences are classified in source rows."
    )
for path in pwl_trivial:
    trivial_reasons[path] = (
        "RADOS-PWL-MECHANICAL-04: Endpoint hunk is namespace/std::filesystem qualification, logging/comment formatting, diagnostic wait-state removal, test-instance qualification or an equivalent error-label rename. PWL state and I/O branching are unchanged here; behavioral exceptions are RADOS-002/003."
    )
for path in support_tests:
    trivial_reasons[path] = (
        "RADOS-TEST-SUPPORT-05: Unit/mock coverage supporting PWL or object-map diff behavior; it does not define an upgrade recipe or production acceptance gate and is cited only as source evidence."
    )

affect = dict(pwl_affect)
for path in fast_diff_affect:
    affect[path] = ("RADOS-004", fast_diff_reason)

expected = set(affect) | set(trivial_reasons)
assert len(affect) == 8 and len(trivial_reasons) == 48 and len(expected) == 56

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert expected <= set(by_path)

# Keep the evidence script safely rerunnable after later owner-10 batches.
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
assert affect_count >= 12 and trivial_count >= 58
assert affect_count + trivial_count + blank_count == 320
print("Classified owner-10 docs/PWL/fast-diff batch: 8 affect, 48 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
