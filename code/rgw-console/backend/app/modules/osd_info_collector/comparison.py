from __future__ import annotations

from typing import Any


COMPARISON_FIELDS = (
    "osd_fsid",
    "hostname",
    "crush_location",
    "device_class",
    "public_ip",
    "public_ips",
    "cluster_ip",
    "cluster_ips",
    "data_device_path",
    "data_device_size_bytes",
    "physical_devices",
    "db_device_path",
    "db_device_size_bytes",
    "db_physical_devices",
    "wal_device_path",
    "wal_device_size_bytes",
    "wal_physical_devices",
    "device_ids",
    "total_bytes",
    "used_bytes",
    "available_bytes",
    "used_percent",
    "pg_count",
    "primary_count",
    "up",
    "in",
    "daemon_status",
    "crush_weight",
    "reweight",
    "primary_affinity",
    "ceph_version",
    "ceph_version_short",
    "container_image",
    "container_image_id",
)

ORDER_INSENSITIVE_LIST_FIELDS = {
    "public_ips",
    "cluster_ips",
    "physical_devices",
    "db_physical_devices",
    "wal_physical_devices",
    "device_ids",
}


def _records(collection: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for record in collection.get("osds") or []:
        if not isinstance(record, dict):
            continue
        osd_id = record.get("osd_id")
        if isinstance(osd_id, bool) or not isinstance(osd_id, int):
            continue
        result[osd_id] = record
    return result


def _normalized(field: str, value: Any) -> Any:
    if field in ORDER_INSENSITIVE_LIST_FIELDS and isinstance(value, list):
        return sorted(value)
    return value


def compare_collections(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare immutable OSD snapshots without turning changes into a PASS/FAIL verdict."""

    not_comparable: list[str] = []
    inconclusive: list[str] = []
    for field, reason in (
        ("cluster_id", "CLUSTER_ID_MISMATCH"),
        ("fsid", "FSID_MISMATCH"),
        ("session_id", "SESSION_MISMATCH"),
        ("config_snapshot_id", "CONFIG_SNAPSHOT_MISMATCH"),
    ):
        if str(before.get(field) or "") != str(after.get(field) or ""):
            not_comparable.append(reason)
    if before.get("phase") != "BEFORE":
        not_comparable.append("LEFT_PHASE_MUST_BE_BEFORE")
    if after.get("phase") not in {"AFTER_START", "AFTER_STABLE"}:
        not_comparable.append("RIGHT_PHASE_MUST_BE_AFTER")
    if before.get("state") != "COMPLETE" or after.get("state") != "COMPLETE":
        inconclusive.append("COLLECTION_NOT_COMPLETE")
    if before.get("quality") != "VALID" or after.get("quality") != "VALID":
        inconclusive.append("COLLECTION_QUALITY_NOT_VALID")

    before_records = _records(before)
    after_records = _records(after)
    before_ids = set(before_records)
    after_ids = set(after_records)
    added_ids = sorted(after_ids - before_ids)
    removed_ids = sorted(before_ids - after_ids)
    if added_ids or removed_ids:
        not_comparable.append("OSD_SCOPE_MISMATCH")

    changes: list[dict[str, Any]] = []
    unchanged_ids: list[int] = []
    for osd_id in sorted(before_ids & after_ids):
        fields = []
        for field in COMPARISON_FIELDS:
            left = _normalized(field, before_records[osd_id].get(field))
            right = _normalized(field, after_records[osd_id].get(field))
            if left != right:
                fields.append({"field": field, "before": left, "after": right})
        before_quality = before_records[osd_id].get("quality")
        after_quality = after_records[osd_id].get("quality")
        if before_quality != "VALID" or after_quality != "VALID":
            inconclusive.append(f"OSD_QUALITY_NOT_VALID:{osd_id}")
        if fields:
            changes.append({
                "osd_id": osd_id,
                "before_quality": before_quality,
                "after_quality": after_quality,
                "fields": fields,
            })
        else:
            unchanged_ids.append(osd_id)

    if not_comparable:
        status = "NOT_COMPARABLE"
    elif inconclusive:
        status = "INCONCLUSIVE"
    else:
        status = "COMPARABLE"
    return {
        "schema_version": 1,
        "comparison_status": status,
        "reasons": sorted(set(not_comparable + inconclusive)),
        "before": {
            "collection_id": str(before.get("id") or ""),
            "phase": before.get("phase"),
            "collected_at": before.get("collected_at"),
            "artifact_sha256": before.get("artifact_sha256"),
            "quality": before.get("quality"),
        },
        "after": {
            "collection_id": str(after.get("id") or ""),
            "phase": after.get("phase"),
            "collected_at": after.get("collected_at"),
            "artifact_sha256": after.get("artifact_sha256"),
            "quality": after.get("quality"),
        },
        "scope": {
            "before_osd_ids": sorted(before_ids),
            "after_osd_ids": sorted(after_ids),
            "added_osd_ids": added_ids,
            "removed_osd_ids": removed_ids,
        },
        "changed_osd_count": len(changes),
        "unchanged_osd_ids": unchanged_ids,
        "changes": changes,
    }
