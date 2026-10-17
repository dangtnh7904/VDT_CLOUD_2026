"""Verify RGW ops-log handling for operations without a bucket."""

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


runtime_commit = "3863eb89512f1698b8e56f1f1ffc78a6ca8d5826"
qa_commit = "788da98cdedf9caaa7ce09b5792351473ce034c2"
for commit in (runtime_commit, qa_commit):
    assert not is_ancestor(commit, "v16.2.15")
    assert is_ancestor(commit, "v17.2.7")

runtime_message = subprocess.check_output(
    ["git", "-C", str(repo), "show", "-s", "--format=%B", runtime_commit],
    text=True,
    encoding="utf-8",
)
assert "permit logging of list-bucket (and any other no-bucket op)" in runtime_message

base_log = show("v16.2.15", "src/rgw/rgw_log.cc")
target_log = show("v17.2.7", "src/rgw/rgw_log.cc")
base_start = base_log.index("int rgw_log_op(")
target_start = target_log.index("int rgw_log_op(")
base_end = len(base_log)
target_end = target_log.index("void rgw_log_entry::generate_test_instances", target_start)
base_op = base_log[base_start:base_end]
target_op = target_log[target_start:target_end]

# Pacific exits before building or emitting an ops-log record when there is no
# bucket. Quincy skips only bucket/object fields and continues with request,
# identity, response and sink emission.
base_empty_start = base_op.index("if (s->bucket_name.empty())")
base_empty_end = base_op.index("if (s->err.ret == -ERR_NO_SUCH_BUCKET", base_empty_start)
base_empty = base_op[base_empty_start:base_empty_end]
assert "nothing to log for operation" in base_empty
assert "return -EINVAL;" in base_empty

target_empty_start = target_op.index("if (s->bucket_name.empty())")
target_empty_end = target_op.index("if (s->cct->_conf->rgw_remote_addr_param", target_empty_start)
target_empty = target_op[target_empty_start:target_empty_end]
assert "this case is needed for, e.g., list_buckets" in target_empty
assert "return -EINVAL;" not in target_empty
for token in (
    "entry.uri = std::move(uri);",
    "entry.op = op_name;",
    "entry.user = s->user->get_id().to_str();",
    "entry.http_status",
    "return olog->log(s, entry);",
):
    assert token in target_op

# The feature remains opt-in at both endpoints. RADOS remains the default sink,
# and the default object-name format substitutes empty bucket id/name fields.
base_options = show("v16.2.15", "src/common/options.cc")
target_options = show("v17.2.7", "src/common/options/rgw.yaml.in")
base_enable = base_options.index('Option("rgw_enable_ops_log"')
base_rados = base_options.index('Option("rgw_ops_log_rados"')
base_name = base_options.index('Option("rgw_log_object_name"')
target_enable = target_options.index("- name: rgw_enable_ops_log")
target_rados = target_options.index("- name: rgw_ops_log_rados")
target_name = target_options.index("- name: rgw_log_object_name")
assert ".set_default(false)" in base_options[base_enable:base_enable + 250]
assert "default: false" in target_options[target_enable:target_enable + 300]
assert ".set_default(true)" in base_options[base_rados:base_rados + 250]
assert "default: true" in target_options[target_rados:target_rados + 300]
assert '%Y-%m-%d-%H-%i-%n' in base_options[base_name:base_name + 250]
assert "%Y-%m-%d-%H-%i-%n" in target_options[target_name:target_name + 350]

# The ops-log payload schema, file sink, SIGHUP reopen and store-pointer
# reference fix are endpoint parity, so their header churn is not a new target
# behavior. Only SAL names and out-of-line dump/test helpers differ there.
base_header = show("v16.2.15", "src/rgw/rgw_log.h")
target_header = show("v17.2.7", "src/rgw/rgw_log.h")
for source in (base_header, target_header):
    for token in (
        "ENCODE_START(14, 5, bl)",
        "std::string access_key_id;",
        "delete_multi_obj_op_meta delete_multi_obj_meta;",
        "class OpsLogFile",
        "void reopen();",
        "const& store;",
    ):
        assert token in source

base_main = show("v16.2.15", "src/rgw/rgw_main.cc")
target_main = show("v17.2.7", "src/rgw/rgw_main.cc")
for source in (base_main, target_main):
    assert "static void rgw_sighup_handler" in source
    assert "ops_log_file->reopen();" in source
    assert "register_async_signal_handler(SIGHUP, rgw_sighup_handler);" in source

# Quincy QA acknowledges empty-bucket log objects but does not assert that a
# bucketless operation is actually present. Other net hunks add standalone
# runner support and relax GC timing; no in-tree upgrade recipe is introduced.
base_qa = show("v16.2.15", "qa/tasks/radosgw_admin.py")
target_qa = show("v17.2.7", "qa/tasks/radosgw_admin.py")
assert "skip any entry for which there is no bucket name" not in base_qa
assert "skip any entry for which there is no bucket name" in target_qa
assert 'if entry_bucket_name.strip() != "":' in target_qa
assert "assert entry_bucket_name.strip() == \"\"" not in target_qa

base_util = show("v16.2.15", "qa/tasks/util/rgw.py")
target_util = show("v17.2.7", "qa/tasks/util/rgw.py")
assert "omit_sudo=False, omit_tdir=False" not in base_util
assert "omit_sudo=False, omit_tdir=False" in target_util
assert "omit_sudo=omit_sudo" in target_util


new_rows = {
    "src/rgw/rgw_log.cc": (
        "affect",
        "RGW-046",
        "RGW-046: With ops logging enabled, Pacific returns EINVAL before emitting any record for an operation with an empty bucket name; Quincy continues and writes the request/identity/status record with empty bucket fields, including list-buckets operations.",
    ),
    "src/rgw/rgw_log.h": (
        "trivial",
        "",
        "RGW-OPSLOG-SUPPORT-01: Both endpoints retain ops-log encoding v14, auth/multi-delete fields, file sink, SIGHUP reopen and a reference to the reloadable store pointer; net header hunks are SAL type renames, STL qualification and moving dump/test helpers out of line.",
    ),
    "qa/tasks/radosgw_admin.py": (
        "trivial",
        "",
        "RGW-OPSLOG-QA-01: The QA task tolerates empty-bucket log objects from RGW-046 and adds standalone-runner/GC-environment handling, but it does not require a bucketless record or define an in-tree upgrade acceptance recipe.",
    ),
    "qa/tasks/util/rgw.py": (
        "trivial",
        "",
        "RGW-OPSLOG-QA-01: Adds optional omit_sudo/omit_tdir switches, both default false, so the existing Teuthology rgwadmin path is unchanged; the switches only support the standalone radosgw_admin local runner.",
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

print("Classified bucketless ops log: 1 affect, 3 trivial")
