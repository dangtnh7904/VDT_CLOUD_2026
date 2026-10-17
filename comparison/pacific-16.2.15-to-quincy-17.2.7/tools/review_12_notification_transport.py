"""Classify Kafka idle eviction and HTTP notification header contracts."""

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


base_kafka = show("v16.2.15", "src/rgw/rgw_kafka.cc")
target_kafka = show("v17.2.7", "src/rgw/rgw_kafka.cc")
assert "max_idle_time" not in base_kafka
assert "const size_t max_idle_time;" in target_kafka
assert "max_idle_time(30)" in target_kafka
assert "conn->timestamp = ceph_clock_now();" in target_kafka
assert "conn->timestamp.sec() + max_idle_time < ceph_clock_now()" in target_kafka
assert "IT=CONTAINER.erase(IT);" in target_kafka
assert "reply_count += rd_kafka_poll(conn->producer, read_timeout_ms);" in target_kafka
base_erase = base_kafka.split("if (conn->marked_for_deletion)", 1)[1].split(
    "if (!conn->is_ok())", 1
)[0]
target_erase = target_kafka.split("if(conn->timestamp.sec() + max_idle_time", 1)[1].split(
    "if (!conn->is_ok())", 1
)[0]
assert "std::lock_guard lock(connections_lock);" in base_erase
assert "std::lock_guard lock(connections_lock);" not in target_erase
target_connect = target_kafka.split("connection_ptr_t connect(", 1)[1].split(
    "// TODO publish with confirm", 1
)[0]
assert "std::lock_guard lock(connections_lock);" in target_connect
assert "connections.emplace(broker, conn)" in target_connect

# connect() returns the map entry, but notification endpoint objects retain an
# intrusive connection pointer. After idle erasure, that pointer can remain
# alive while the manager only polls producers still present in the map.
target_push = show("v17.2.7", "src/rgw/rgw_pubsub_push.cc")
target_sync = show("v17.2.7", "src/rgw/rgw_sync_module_pubsub.cc")
assert "kafka::connection_ptr_t conn;" in target_push
assert "conn(kafka::connect(" in target_push
assert "kafka::publish_with_confirm(conn," in target_push
assert "push_endpoint = RGWPubSubEndpoint::create" in target_sync
assert "sub_conf->push_endpoint->send_to_completion_async" in target_sync

# Both endpoints already send application/json on the active non-coroutine
# S3-notification path. Quincy additionally emits CloudEvents binary-mode ce-*
# headers when requested; Pacific accepts the stored endpoint args but ignores
# this new option.
base_push = show("v16.2.15", "src/rgw/rgw_pubsub_push.cc")
assert 'request.append_header("Content-Type", "application/json")' in base_push
assert 'request.append_header("Content-Type", "application/json")' in target_push
assert 'get_bool(args, "cloudevents", false)' not in base_push
assert 'get_bool(args, "cloudevents", false)' in target_push
for header in ("ce-specversion", "ce-type", "ce-time", "ce-id", "ce-source", "ce-subject"):
    assert f'request.append_header("{header}"' in target_push

target_notify = show("v17.2.7", "src/rgw/rgw_notify.cc")
assert "push_endpoint->send_to_completion_async(cct, event_entry.event" in target_notify
assert "push_endpoint->send_to_completion_async(\n\t  dpp->get_cct(), event_entry.event" in target_notify

base_doc = show("v16.2.15", "doc/radosgw/notifications.rst")
target_doc = show("v17.2.7", "doc/radosgw/notifications.rst")
assert "Attributes.entry.10.key=cloudevents" not in base_doc
assert "Attributes.entry.10.key=cloudevents" in target_doc


updates = {
    "src/rgw/rgw_kafka.cc": (
        "affect",
        "RGW-032",
        "RGW-032: Quincy expires Kafka connections after more than 30 seconds without a publish, erases the unordered-map entry outside connections_lock while connect() can insert, and can leave a long-lived endpoint holding an intrusive pointer to a producer no longer in the manager poll loop; post-idle concurrency and ACK callbacks require runtime validation.",
    ),
    "src/rgw/rgw_pubsub_push.cc": (
        "affect",
        "RGW-033",
        "RGW-033: When endpoint args set cloudevents=true, Quincy's active S3 HTTP-notification path adds CloudEvents binary-mode ce-* headers that Pacific ignores; mixed-version delivery can therefore present different webhook contracts while retaining the same JSON body/content type.",
    ),
    "doc/radosgw/notifications.rst": (
        "trivial",
        "",
        "RGW-033-DOC: Documents the new optional cloudevents endpoint argument and corrects response-example spelling; executable header behavior is owned by RGW-033 in rgw_pubsub_push.cc.",
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
for path, (impact, finding, reason) in updates.items():
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

print("Classified Kafka and HTTP notification runtime rows affect; notification docs trivial")
