"""Classify S3 empty NotificationConfiguration semantics and its direct QA case."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag, source):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{source}"],
        text=True, encoding="utf-8")


pubsub_path = "src/rgw/rgw_pubsub.cc"
rest_path = "src/rgw/rgw_rest_pubsub.cc"
test_path = "src/test/rgw/bucket_notification/test_bn.py"
old_pubsub = show("v16.2.15", pubsub_path)
new_pubsub = show("v17.2.7", pubsub_path)
old_rest = show("v16.2.15", rest_path)
new_rest = show("v17.2.7", rest_path)
assert 'throw RGWXMLDecoder::err("at least one \'TopicConfiguration\' must exist");' in old_pubsub
assert 'throw RGWXMLDecoder::err("at least one \'TopicConfiguration\' must exist");' not in new_pubsub
assert 'do_decode_xml_obj(list, "TopicConfiguration", obj);' in old_pubsub
assert 'do_decode_xml_obj(list, "TopicConfiguration", obj);' in new_pubsub
assert "if(configurations.list.empty())" not in old_rest
for snippet in (
    "if(configurations.list.empty())",
    "op_ret = b->get_topics(&bucket_topics);",
    "op_ret = delete_all_notifications(this, bucket_topics, b, y, *ps);",
    "op_ret = b->remove_notification(dpp, topic_name, y);",
    "op_ret = ps.remove_topic(dpp, topic_name, y);",
    'RGWXMLDecoder::decode_xml("NotificationConfiguration", configurations, &parser, true);',
):
    assert snippet in new_rest, snippet
assert 'return -ERR_MALFORMED_XML;' in old_rest
new_test = show("v17.2.7", test_path)
for snippet in (
    "def test_ps_s3_notification_on_master_empty_config():",
    "topic_conf_list = []",
    "assert_equal(status/100, 2)",
    "response, status = s3_notification_conf.get_config()",
):
    assert snippet in new_test, snippet
runner = show("v17.2.7", "qa/tasks/notification_tests.py")
assert "src/test/rgw/bucket_notification/test_bn.py" in runner

changes = {
    pubsub_path: "RGW-022: Pacific rejects empty TopicConfiguration list during XML decode; Quincy accepts it for the PUT bucket notification clear-all operation.",
    rest_path: "RGW-022: Quincy PUT bucket notification now dispatches an empty configuration to delete_all_notifications, removing bucket notification entries and generated subscriptions/topics.",
    test_path: "RGW-022: New bucket notification test covers PUT of empty configuration, checks 2xx, and then checks the notification is absent when notification_tests runs this module.",
}
csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source, reason in changes.items():
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    assert row["status"] == ("A" if source == test_path else "M"), source
    row.update(upgrade_impact="affect", finding_id="RGW-022", impact_reason=reason)
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
print("Classified empty S3 notification runtime and direct QA rows affect")
