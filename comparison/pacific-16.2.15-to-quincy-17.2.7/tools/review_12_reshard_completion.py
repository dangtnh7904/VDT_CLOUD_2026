"""Verify the RGW async index-completion/reshard endpoint delta."""

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


def commit_message(commit: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", "-s", "--format=%B", commit],
        text=True,
        encoding="utf-8",
    )


# Both release branches contain the general decommissioned-shard fix, but as
# independent backports. The endpoint comparison, not hash ancestry alone, is
# therefore the primary evidence.
base_guard = "b11c10acc9026d92b90cfb88f6a3381274ccb9bc"
target_guard = "0a09d78f0f834db0ff803040b9c44d290762ac4b"
for commit in (base_guard, target_guard):
    assert "object puts could write to decommissioned shard" in commit_message(commit)
assert is_ancestor(base_guard, "v16.2.15")
assert not is_ancestor(base_guard, "v17.2.7")
assert not is_ancestor(target_guard, "v16.2.15")
assert is_ancestor(target_guard, "v17.2.7")

# Each endpoint also has its own backport of the completion-manager rewrite.
# Pacific's later conflict resolution preserves assert_exists() in the retry
# operation, while Quincy's earlier one does not.
base_completion = "32f87a92565277110931c261e2ee34f5c11b3583"
target_completion = "cd69db3cb2f7bd1183e9284dd8329f2256cd4d2f"
for commit in (base_completion, target_completion):
    assert "prevent spurious/lost notifications in the index completion thread" in commit_message(commit)
assert is_ancestor(base_completion, "v16.2.15")
assert not is_ancestor(base_completion, "v17.2.7")
assert not is_ancestor(target_completion, "v16.2.15")
assert is_ancestor(target_completion, "v17.2.7")

base_rados = show("v16.2.15", "src/rgw/rgw_rados.cc")
target_rados = show("v17.2.7", "src/rgw/rgw_rados.cc")


def completion_retry_body(source: str) -> str:
    start = source.index("void RGWIndexCompletionManager::process()")
    end = source.index("void RGWIndexCompletionManager::create_completion", start)
    return source[start:end]


base_retry = completion_retry_body(base_rados)
target_retry = completion_retry_body(target_rados)
assert "o.assert_exists(); // bucket index shard must exist" in base_retry
assert "o.assert_exists(); // bucket index shard must exist" not in target_retry
for token in (
    "cls_rgw_guard_bucket_resharding(o, -ERR_BUSY_RESHARDING)",
    "cls_rgw_bucket_complete_op(o, c->op",
    "store->svc.datalog_rados->add_entry",
):
    assert token in base_retry and token in target_retry

# The initial prepare/complete operations retain the assertion in both tags.
# The net difference is restricted to the retry after ERR_BUSY_RESHARDING.
for source in (base_rados, target_rados):
    prepare_start = source.index("int RGWRados::cls_obj_prepare_op(")
    complete_start = source.index("int RGWRados::cls_obj_complete_op(", prepare_start)
    next_start = source.index("int RGWRados::cls_obj_complete_add(", complete_start)
    assert "o.assert_exists(); // bucket index shard must exist" in source[prepare_start:complete_start]
    assert "o.assert_exists(); // bucket index shard must exist" in source[complete_start:next_start]
    assert "r != -ERR_BUSY_RESHARDING && r != -ENOENT" in source

# Initialization-order fixes and the other reshard maintenance features exist
# at both endpoints; they must not be misreported as Quincy-only behavior.
for commit, tag in (
    ("38de5d734835d990c1a79e2b67aa69fb7860aa79", "v16.2.15"),
    ("9cd0ee4448c0aad33dfbab49ecdf79b8d9566bd9", "v17.2.7"),
):
    assert "initialize RGWIndexCompletionManager thread after related members" in commit_message(commit)
    assert is_ancestor(commit, tag)

base_reshard = show("v16.2.15", "src/rgw/rgw_reshard.cc")
target_reshard = show("v17.2.7", "src/rgw/rgw_reshard.cc")
for token in (
    "entry.type == BIIndexType::OLH && key.empty()",
    "store->svc()->bi->clean_index(dpp, bucket_info)",
    "cls_rgw_reshard_list",
):
    assert token in base_reshard and token in target_reshard

base_admin = show("v16.2.15", "src/rgw/rgw_admin.cc")
target_admin = show("v17.2.7", "src/rgw/rgw_admin.cc")
for token in ("BUCKET_CHECK_OLH", "BUCKET_CHECK_UNLINKED"):
    assert token in base_admin and token in target_admin

# Quincy adds a foreground PUT-during-reshard regression case, but the case
# only checks that put_object() returns; it does not inspect old shard objects,
# bucket-index state, bilog/datalog, or notification delivery after the async
# completion retry.
base_test = show("v16.2.15", "qa/workunits/rgw/test_rgw_reshard.py")
target_test = show("v17.2.7", "qa/workunits/rgw/test_rgw_reshard.py")
case_marker = "# TESTCASE 'check that PUT succeeds during reshard'"
assert case_marker not in base_test
assert case_marker in target_test
case_start = target_test.index(case_marker)
case_end = target_test.index("# TESTCASE", case_start + len(case_marker))
case = target_test[case_start:case_end]
assert "put_object(Key='put_during_reshard'" in case
for absent in ("bi list", "bilog", "datalog", "notification"):
    assert absent not in case


new_rows = {
    "qa/workunits/rgw/test_rgw_reshard.py": (
        "trivial",
        "",
        "RGW-RESHARD-QA-01: Adds a delayed foreground PUT regression case, but both endpoints already contain the general decommissioned-shard fix and the case does not inspect the async retry's old-shard/index/log/notification outcome tracked by RGW-043.",
    ),
    "src/rgw/rgw_reshard.cc": (
        "trivial",
        "",
        "RGW-RESHARD-MECH-01: Endpoint behavior for empty-name OLH pruning, old-index cleanup, locking and reshard-log operations is unchanged; the net hunks are SAL rename, DPP logging context, namespace/style and spelling cleanup.",
    ),
    "src/rgw/rgw_reshard.h": (
        "trivial",
        "",
        "RGW-RESHARD-MECH-01: Declarations follow the RadosStore rename, std qualification and DPP logging parameter without changing reshard state, lock timing or shard-selection contracts.",
    ),
}

existing_additions = {
    "src/rgw/rgw_rados.cc": (
        "RGW-043",
        "RGW-043: Pacific preserves assert_exists() when retrying an async bucket-index completion after ERR_BUSY_RESHARDING, while Quincy omits it; the target retry can therefore operate on a removed old shard instead of refusing to recreate it.",
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

for path, (finding, reason) in existing_additions.items():
    row = by_path[path]
    assert row["upgrade_impact"] == "affect", path
    findings = row["finding_id"].split(",") if row["finding_id"] else []
    if finding not in findings:
        row["finding_id"] = ",".join(findings + [finding])
        row["impact_reason"] = (row["impact_reason"] + " " + reason).strip()
    else:
        assert reason in row["impact_reason"], path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified reshard adjacency: 3 trivial; extended 1 existing affect row with RGW-043")
