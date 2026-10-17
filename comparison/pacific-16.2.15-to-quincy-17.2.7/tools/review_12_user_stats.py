"""Verify and classify RGW user-stats behavior and adjacent mechanical rows."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


def is_ancestor(commit: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, tag],
        check=False,
    )
    assert result.returncode in (0, 1)
    return result.returncode == 0


def between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


# Quincy contains the fix that checks user metadata before reading the cls_user
# header. Pacific only reads <uid>.buckets, so it cannot distinguish a valid
# zero-bucket user from a missing user/stale header in the same way.
stats_commit = "c1c4da3804bd37e43830d062d3feb193adb2ec6f"
message = subprocess.check_output(
    ["git", "-C", str(repo), "show", "-s", "--format=%B", stats_commit],
    text=True,
    encoding="utf-8",
)
assert "when radosgw-admin stating user, add user exists judging" in message
assert "53172" in message
assert not is_ancestor(stats_commit, "v16.2.15")
assert is_ancestor(stats_commit, "v17.2.7")
changed = subprocess.check_output(
    ["git", "-C", str(repo), "diff-tree", "--no-commit-id", "--name-only", "-r", stats_commit],
    text=True,
    encoding="utf-8",
).splitlines()
assert changed == ["src/rgw/services/svc_user_rados.cc"]

base_user_rados = show("v16.2.15", "src/rgw/services/svc_user_rados.cc")
target_user_rados = show("v17.2.7", "src/rgw/services/svc_user_rados.cc")
start = "int RGWSI_User_RADOS::read_stats("
end = "class RGWGetUserStatsContext"
base_stats = between(base_user_rados, start, end)
target_stats = between(target_user_rados, start, end)
assert "read_user_info(ctx, user" not in base_stats
assert "read_user_info(ctx, user" in target_stats
assert "if (r < 0 && r != -ENOENT)" not in base_stats
assert "if (r < 0 && r != -ENOENT)" in target_stats
for token in (
    "stats->size = hs.total_bytes;",
    "stats->size_rounded = hs.total_bytes_rounded;",
    "stats->num_objects = hs.total_entries;",
    "*last_stats_sync = header.last_stats_sync;",
    "*last_stats_update = header.last_stats_update;",
):
    assert token in base_stats and token in target_stats

# The shared synchronous function is called by radosgw-admin/account stats and
# the user-quota cache. The endpoint callers retain their roles; the service
# implementation changes the missing-user/missing-header outcome beneath them.
for path, tokens in {
    "src/rgw/rgw_admin.cc": (
        "user stats",
        "read_stats(dpp()",
        "User has not been initialized or user does not exist",
    ),
    "src/rgw/rgw_op.cc": (
        "rgw_user_get_all_buckets_stats",
        "read_stats(this",
    ),
    "src/rgw/rgw_quota.cc": (
        "RGWUserStatsCache::fetch_stats_from_storage",
        "read_stats(dpp",
    ),
}.items():
    base = show("v16.2.15", path)
    target = show("v17.2.7", path)
    for token in tokens:
        assert token in base and token in target

# There is no dedicated regression test in the fixing commit. The existing
# target admin task covers positive stats after bucket activity, not the two
# boundary states above.
target_admin_test = show("v17.2.7", "qa/tasks/radosgw_admin.py")
assert "['user', 'stats','--uid', user1, '--sync-stats']" in target_admin_test
assert "'info-nosuch','user','info','non-existent user','fails'" in target_admin_test
assert "'stats-nosuch'" not in target_admin_test


# Adjacent small rows are screened separately. These assertions prove their
# endpoint changes are qualification, interface relocation, or method movement
# without a new request/state/schema behavior.
base_2pc = show("v16.2.15", "src/cls/2pc_queue/cls_2pc_queue_client.cc")
target_2pc = show("v17.2.7", "src/cls/2pc_queue/cls_2pc_queue_client.cc")
for token in ("TPC_QUEUE_GET_CAPACITY", "TPC_QUEUE_RESERVE", "TPC_QUEUE_LIST_ENTRIES"):
    assert token in base_2pc and token in target_2pc
assert "const string& queue_name" in base_2pc
assert "const std::string& queue_name" in target_2pc

base_queue_h = show("v16.2.15", "src/cls/queue/cls_queue_client.h")
target_queue_h = show("v17.2.7", "src/cls/queue/cls_queue_client.h")
for token in (
    "cls_queue_init",
    "cls_queue_get_capacity",
    "cls_queue_enqueue",
    "cls_queue_list_entries",
    "cls_queue_remove_entries",
):
    assert token in base_queue_h and token in target_queue_h
assert "vector<cls_queue_entry>" in base_queue_h
assert "std::vector<cls_queue_entry>" in target_queue_h

base_setup = show("v16.2.15", "src/pybind/rgw/setup.py")
target_setup = show("v17.2.7", "src/pybind/rgw/setup.py")
future_line = "from __future__ import print_function\n"
assert future_line in base_setup
assert future_line not in target_setup
assert base_setup.replace(future_line, "", 1) == target_setup

base_lock = show("v16.2.15", "src/rgw/rgw_object_lock.h")
target_lock = show("v17.2.7", "src/rgw/rgw_object_lock.h")
for token in (
    "ENCODE_START(1, 1, bl);",
    "retention_period_valid() const",
    "get_lock_until_date",
    "is_enabled() const",
):
    assert token in base_lock and token in target_lock
assert "string mode;" in base_lock
assert "std::string mode;" in target_lock

base_tag = show("v16.2.15", "src/rgw/rgw_tag.cc")
target_tag = show("v17.2.7", "src/rgw/rgw_tag.cc")
base_json = show("v16.2.15", "src/rgw/rgw_json_enc.cc")
target_json = show("v17.2.7", "src/rgw/rgw_json_enc.cc")
empty_guard = "if (input.empty())"
assert empty_guard in base_tag and empty_guard in target_tag
assert "void RGWObjTags::dump" not in base_tag
assert "void RGWObjTags::dump" in base_json
assert "void RGWObjTags::dump" in target_tag
assert "void RGWObjTags::dump" not in target_json

base_putobj = show("v16.2.15", "src/rgw/rgw_putobj.h")
target_putobj = show("v17.2.7", "src/rgw/rgw_putobj.h")
target_sal = show("v17.2.7", "src/rgw/rgw_sal.h")
for token in (
    "virtual ~DataProcessor() {}",
    "virtual int process(bufferlist&& data, uint64_t offset) = 0;",
):
    assert token in base_putobj and token in target_sal
assert "class Pipe : public DataProcessor" in base_putobj
assert "class Pipe : public rgw::sal::DataProcessor" in target_putobj
for token in ("ChunkProcessor", "StripeProcessor", "next->process(std::move(data), offset)"):
    assert token in base_putobj and token in target_putobj

base_user_h = show("v16.2.15", "src/rgw/services/svc_user.h")
target_user_h = show("v17.2.7", "src/rgw/services/svc_user.h")
base_user_rados_h = show("v16.2.15", "src/rgw/services/svc_user_rados.h")
target_user_rados_h = show("v17.2.7", "src/rgw/services/svc_user_rados.h")
for base, target in ((base_user_h, target_user_h), (base_user_rados_h, target_user_rados_h)):
    for token in ("read_user_info", "store_user_info", "read_stats", "read_stats_async"):
        assert token in base and token in target
    assert "map<string, bufferlist>" in base
    assert "std::map<std::string, bufferlist>" in target


new_rows = {
    "src/rgw/services/svc_user_rados.cc": (
        "affect",
        "RGW-041",
        "RGW-041: Quincy validates user metadata before synchronous stats reads and treats a missing <uid>.buckets header as zero stats; Pacific reads only that header, so zero-bucket and stale-header outcomes can differ.",
    ),
    "src/cls/2pc_queue/cls_2pc_queue_client.cc": (
        "trivial",
        "",
        "RGW-QUEUE-STD-01: Qualifies std::string in the same 2PC queue client methods; class operations, payloads, result decoding, and error returns are unchanged.",
    ),
    "src/cls/queue/cls_queue_client.h": (
        "trivial",
        "",
        "RGW-QUEUE-STD-01: Qualifies standard string/vector types in queue client declarations without changing operation signatures at the ABI/type level or queue behavior.",
    ),
    "src/pybind/rgw/setup.py": (
        "trivial",
        "",
        "RGW-PY3-CLEANUP-01: Removes only the Python 2 print_function future import; the extension build configuration and compiler/link checks are byte-identical otherwise.",
    ),
    "src/rgw/rgw_object_lock.h": (
        "trivial",
        "",
        "RGW-OBJECT-LOCK-STD-02: Qualifies std::string in object-lock declarations; encoding v1, retention validation, dates, modes, and legal-hold behavior are unchanged.",
    ),
    "src/rgw/rgw_tag.cc": (
        "trivial",
        "",
        "RGW-ENCODER-MOVE-02: Retains tag parsing including the empty-input guard and receives RGWObjTags::dump from rgw_json_enc.cc; no endpoint tag semantics change in this row.",
    ),
    "src/rgw/rgw_putobj.h": (
        "trivial",
        "",
        "RGW-PUTOBJ-SAL-02: Moves the identical DataProcessor interface to SAL and retargets the same Pipe/ChunkProcessor/StripeProcessor inheritance without changing processing logic.",
    ),
    "src/rgw/services/svc_user.h": (
        "trivial",
        "",
        "RGW-USER-SVC-STD-01: Qualifies standard-library types in the user service interface; metadata, bucket, stats, and async method contracts are unchanged.",
    ),
    "src/rgw/services/svc_user_rados.h": (
        "trivial",
        "",
        "RGW-USER-SVC-STD-01: Qualifies standard-library types in the RADOS user-service declaration; the RGW-041 behavior is implemented only in svc_user_rados.cc.",
    ),
}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for path, (impact, finding, reason) in new_rows.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified user-stats/adjacent rows: 1 affect, 8 trivial")
