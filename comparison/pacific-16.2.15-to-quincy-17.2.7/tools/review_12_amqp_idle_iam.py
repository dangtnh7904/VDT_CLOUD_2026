"""Classify the Quincy AMQP idle path and bucket-encryption IAM action mapping."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag, path):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True, encoding="utf-8")


amqp_path = "src/rgw/rgw_amqp.cc"
old_amqp = show("v16.2.15", amqp_path)
new_amqp = show("v17.2.7", amqp_path)
assert "max_idle_time" not in old_amqp
for snippet in (
    "utime_t timestamp = ceph_clock_now();",
    "const size_t max_idle_time;",
    "conn->timestamp = ceph_clock_now();",
    "if(conn->timestamp.sec() + max_idle_time < ceph_clock_now())",
    "ERASE_AND_CONTINUE(conn_it, connections);",
    "max_idle_time(30),",
    "const auto count = messages.consume_all(std::bind(&Manager::publish_internal",
    "const auto rc = amqp_simple_wait_frame_noblock(conn->state, &frame, &read_timeout);",
    "return connections.emplace(id, conn).first->second;",
    "if (!conn || !conn->is_ok())",
):
    assert snippet in new_amqp, snippet
assert "IT=CONTAINER.erase(IT);" in new_amqp
assert "--connection_count;" in new_amqp

endpoint = show("v17.2.7", "src/rgw/rgw_pubsub_push.cc")
for snippet in (
    "amqp::connection_ptr_t conn;",
    "conn(amqp::connect(endpoint, exchange,",
    "return ack_level_t::Broker;",
    "amqp::publish_with_confirm(conn,",
    "return w->wait(y);",
):
    assert snippet in endpoint, snippet
sync_module = show("v17.2.7", "src/rgw/rgw_sync_module_pubsub.cc")
assert "RGWPubSubEndpoint::Ptr push_endpoint;" in sync_module
assert "sub_conf->push_endpoint->send_to_completion_async(*event.get(), sync_env)" in sync_module

old_iam_cc = show("v16.2.15", "src/rgw/rgw_iam_policy.cc")
new_iam_cc = show("v17.2.7", "src/rgw/rgw_iam_policy.cc")
old_iam_h = show("v16.2.15", "src/rgw/rgw_iam_policy.h")
new_iam_h = show("v17.2.7", "src/rgw/rgw_iam_policy.h")
assert "s3GetBucketEncryption" not in old_iam_cc + old_iam_h
assert "s3PutBucketEncryption" not in old_iam_cc + old_iam_h
for action in ("s3GetBucketEncryption", "s3PutBucketEncryption"):
    assert new_iam_cc.count(action) >= 2, action
    assert new_iam_h.count(action) >= 2, action
    assert '"' + action.replace("s3", "s3:", 1) + '"' in new_iam_cc, action
assert "static constexpr std::uint64_t s3All = 68;" in old_iam_h
assert "static constexpr std::uint64_t s3All = 70;" in new_iam_h
assert "s3GetBucketEncryption" in show("v17.2.7", "src/rgw/rgw_op.cc")
assert "s3PutBucketEncryption" in show("v17.2.7", "src/rgw/rgw_op.cc")

changes = {
    amqp_path: ("RGW-021", "RGW-021: Quincy adds a hardcoded 30-second AMQP idle eviction from the manager map; a retained connection handle can outlive that map entry, changing retry and broker-ACK callback behavior on later publishes."),
    "src/rgw/rgw_iam_policy.cc": ("RGW-002", "RGW-002: Adds GetBucketEncryption/PutBucketEncryption action-name parsing and formatting used by the new RGW bucket-encryption operations."),
    "src/rgw/rgw_iam_policy.h": ("RGW-002", "RGW-002: Adds bucket-encryption action constants and maps them to read/write permissions; shifts the s3All sentinel for the new IAM actions."),
}
path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source, (finding, reason) in changes.items():
    row = by_path[source]
    assert row["status"] == "M" and not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row.update(upgrade_impact="affect", finding_id=finding, impact_reason=reason)
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
print("Classified AMQP idle eviction and two bucket-encryption IAM mapping rows affect")
