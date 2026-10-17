"""Verify and classify RGW lifecycle, payload, and cache-notify core changes."""

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


base_event = show("v16.2.15", "src/rgw/rgw_notify_event_type.cc")
target_event = show("v17.2.7", "src/rgw/rgw_notify_event_type.cc")
base_event_h = show("v16.2.15", "src/rgw/rgw_notify_event_type.h")
target_event_h = show("v17.2.7", "src/rgw/rgw_notify_event_type.h")
assert "ObjectLifecycle" not in base_event + base_event_h
for token in (
    "ObjectLifecycle",
    "ObjectExpirationCurrent",
    "ObjectExpirationNoncurrent",
    "ObjectExpirationDeleteMarker",
    "ObjectTransitionCurrent",
    "ObjectTransitionNoncurrent",
):
    assert token in target_event + target_event_h
assert 'return "s3:UnknownEvet";' in base_event
assert 'return "s3:ObjectLifecycle:Expiration:AbortMPU";' in target_event
assert 's == "s3:ObjectLifecycle:Expiration:AbortMultipartUpload"' in target_event

base_lc = show("v16.2.15", "src/rgw/rgw_lc.cc")
target_lc = show("v17.2.7", "src/rgw/rgw_lc.cc")
assert "rgw::notify::publish_reserve" not in base_lc
assert "rgw::notify::publish_reserve" in target_lc
for token in (
    "ObjectExpirationCurrent",
    "ObjectExpirationNoncurrent",
    "ObjectExpirationDeleteMarker",
):
    assert token in target_lc
assert "ObjectTransitionCurrent" not in target_lc
assert "ObjectTransitionNoncurrent" not in target_lc

base_sync = show("v16.2.15", "src/rgw/rgw_sync_module_pubsub_rest.cc")
target_sync = show("v17.2.7", "src/rgw/rgw_sync_module_pubsub_rest.cc")
assert '"OBJECT_CREATE,OBJECT_DELETE,DELETE_MARKER_CREATE"' in base_sync
assert '"OBJECT_CREATE,OBJECT_DELETE,DELETE_MARKER_CREATE,OBJECT_EXPIRATION"' in target_sync

# Bucket-topic encoding stays at v3 and stores event strings. A Pacific reader
# therefore decodes Quincy-only lifecycle strings as UnknownEvent. Both S3 PUT
# paths reject UnknownEvent, while remove_notification performs read/modify/write.
for tag in ("v16.2.15", "v17.2.7"):
    pubsub_h = show(tag, "src/rgw/rgw_pubsub.h")
    rest = show(tag, "src/rgw/rgw_rest_pubsub.cc")
    pubsub_cc = show(tag, "src/rgw/rgw_pubsub.cc")
    assert "ENCODE_START(3, 1, bl);" in pubsub_h
    assert "std::vector<std::string> tmp_events;" in pubsub_h
    assert "rgw::notify::from_string" in pubsub_h
    assert "rgw::notify::UnknownEvent" in rest
    assert "bucket_topics.topics.erase(topic_name);" in pubsub_cc
    assert "write_topics(dpp, bucket_topics" in pubsub_cc

base_notify = show("v16.2.15", "src/rgw/rgw_notify.cc")
target_notify = show("v17.2.7", "src/rgw/rgw_notify.cc")
base_notify_h = show("v16.2.15", "src/rgw/rgw_notify.h")
target_notify_h = show("v17.2.7", "src/rgw/rgw_notify.h")
assert "event.awsRegion =" not in base_notify
assert "event.awsRegion = res.store->get_zone()->get_zonegroup().api_name;" in target_notify
assert "event.object_versionId = obj->get_instance();" in base_notify
assert "event.object_versionId = version;" in target_notify
assert "metadata_fetched_from_attributes" not in base_notify + base_notify_h
assert "metadata_fetched_from_attributes" in target_notify + target_notify_h
assert "src_object" in target_notify_h
assert "ctor for non-request caller (e.g., lifecycle)" in target_notify_h

base_svc_notify = show("v16.2.15", "src/rgw/services/svc_notify.cc")
target_svc_notify = show("v17.2.7", "src/rgw/services/svc_notify.cc")
assert "bool unregister_done{false};" in base_svc_notify
assert base_svc_notify.count("svc->schedule_context(new C_ReinitWatch(this));") == 2
assert "bool unregister_done{false};" not in target_svc_notify
assert target_svc_notify.count("svc->schedule_context(new C_ReinitWatch(this));") == 1
# Both endpoints already guard partial startup registration during shutdown.
# The net difference is Pacific's later runtime reinit backport, which is not
# present in Quincy 17.2.7.
assert "if (watchers_set.find(i) != watchers_set.end())" in base_svc_notify
assert "if (watchers_set.find(i) != watchers_set.end())" in target_svc_notify

# REMOVE_OBJ -> INVALIDATE_OBJ is only a same-ordinal rename; the receiver still
# evicts the named cache entry, so these support files do not own RGW-038.
base_cache_h = show("v16.2.15", "src/rgw/rgw_cache.h")
target_cache_h = show("v17.2.7", "src/rgw/rgw_cache.h")
base_sys_cache = show("v16.2.15", "src/rgw/services/svc_sys_obj_cache.cc")
target_sys_cache = show("v17.2.7", "src/rgw/services/svc_sys_obj_cache.cc")
assert "UPDATE_OBJ,\n  REMOVE_OBJ," in base_cache_h
assert "UPDATE_OBJ,\n  INVALIDATE_OBJ," in target_cache_h
assert "case REMOVE_OBJ:" in base_sys_cache and "cache.remove(dpp, name);" in base_sys_cache
assert "case INVALIDATE_OBJ:" in target_sys_cache
assert "cache.invalidate_remove(dpp, name);" in target_sys_cache


updates = {
    "src/rgw/rgw_notify_event_type.cc": (
        "affect",
        "RGW-036",
        "RGW-036: Quincy parses and formats new lifecycle expiration/transition event families; Pacific maps those persisted strings to UnknownEvent.",
    ),
    "src/rgw/rgw_notify_event_type.h": (
        "affect",
        "RGW-036",
        "RGW-036: Adds lifecycle event bit ranges and moves UnknownEvent, enabling lifecycle filter matching only on Quincy.",
    ),
    "src/rgw/rgw_sync_module_pubsub_rest.cc": (
        "affect",
        "RGW-036",
        "RGW-036: Ceph-specific PubSub notification creation now includes OBJECT_EXPIRATION in the default event set.",
    ),
    "src/rgw/rgw_notify.cc": (
        "affect",
        "RGW-037",
        "RGW-037: Notification construction now emits zonegroup api_name as awsRegion, consumes explicit operation version IDs, and fetches COPY/CompleteMultipartUpload metadata through the explicit source object.",
    ),
    "src/rgw/rgw_notify.h": (
        "affect",
        "RGW-037",
        "RGW-037: Reservation state carries explicit source/bucket/request data and version input, supporting non-request lifecycle callers and revised event payload fields.",
    ),
    "src/rgw/services/svc_notify.cc": (
        "affect",
        "RGW-038",
        "RGW-038: Quincy lacks Pacific 16.2.15's later unregister_done and rescheduled re-register recovery after runtime watch errors, so its metadata cache can remain disabled until restart.",
    ),
    "src/rgw/rgw_pubsub.h": (
        "trivial",
        "",
        "RGW-PUBSUB-DECL-02: Keeps bucket-topic encoding v3 and string-based event serialization unchanged; remaining changes are SAL/std declaration cleanup, while lifecycle interpretation is owned by RGW-036.",
    ),
    "doc/radosgw/s3-notification-compatibility.rst": (
        "trivial",
        "",
        "RGW-NOTIFY-DOC-02: Documents lifecycle notification names and fixes prose typos; runtime and mixed-version behavior are tracked by RGW-036, including endpoint spelling mismatches.",
    ),
    "src/rgw/services/svc_sys_obj_cache.cc": (
        "trivial",
        "",
        "RGW-CACHE-NAME-02: Follows the same-ordinal REMOVE_OBJ to INVALIDATE_OBJ and remove to invalidate_remove renames; receiver behavior still evicts the named entry.",
    ),
    "src/rgw/services/svc_sys_obj_cache.h": (
        "trivial",
        "",
        "RGW-CACHE-NAME-02: Qualifies STL types and updates the admin-socket callback signature without changing cache lookup, encoding, or invalidation behavior.",
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

print("Classified notification core: 6 affect, 4 trivial")
