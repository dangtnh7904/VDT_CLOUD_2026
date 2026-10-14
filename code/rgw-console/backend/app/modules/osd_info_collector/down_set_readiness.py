"""Read-only OSD inventory checks performed immediately before a down-set.

This module deliberately does not claim that an OSD mutation is safe.  The
collector does not own PG up/acting checks, the maintenance lease, fencing, or
the live cluster-health gate.  Its only job is to decide whether a fresh,
cluster-wide inventory is internally good enough to feed those later gates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


MUTATION_LIMITATIONS = (
    "PG_UP_ACTING_RECHECK_REQUIRED",
    "CLUSTER_HEALTH_RECHECK_REQUIRED",
    "LEASE_AND_FENCE_REQUIRED",
    "LIVE_MUTATION_DISABLED",
)


def _ids(values: Iterable[Any]) -> list[int]:
    return sorted({int(value) for value in values})


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value)


def _result(
    inventory_result: str,
    reasons: list[str],
    *,
    target_osd_ids: list[int],
    observed: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "inventory_result": inventory_result,
        # An inventory-only decision must never be interpreted as permission
        # to execute a Ceph mutation.
        "mutation_readiness": "BLOCKED",
        "reasons": reasons,
        "limitations": list(MUTATION_LIMITATIONS),
        "target_osd_ids": target_osd_ids,
        "observed": dict(observed),
    }


def evaluate_down_set_inventory(
    *,
    run: Mapping[str, Any],
    collection: Mapping[str, Any],
    target_osd_ids: Iterable[Any],
    allowed_osd_ids: Iterable[Any],
    now: datetime,
    max_age_seconds: int,
    clock_skew_seconds: int,
) -> dict[str, Any]:
    """Evaluate the inventory portion of a pre-down-set safety gate.

    ``READY`` here means only that the inventory input is fresh, complete and
    within the configured simultaneous-down budget.  ``mutation_readiness`` is
    intentionally always ``BLOCKED`` until the independent PG, health, lease
    and fencing gates exist and pass.
    """

    targets = _ids(target_osd_ids)
    allowed = _ids(allowed_osd_ids)
    source_osds = _ids(run.get("source_osds") or [])
    requested = _ids(collection.get("requested_osd_ids") or [])
    collection_state = collection.get("state", collection.get("collection_state"))
    collection_quality = collection.get("quality", collection.get("quality_status"))
    artifact_sha256 = collection.get("artifact_sha256", collection.get("payload_sha256"))
    observed: dict[str, Any] = {
        "phase": collection.get("phase"),
        "collection_state": collection_state,
        "quality_status": collection_quality,
        "requested_osd_ids": requested,
        "allowed_osd_ids": allowed,
        "source_osd_ids": source_osds,
    }

    structural_reasons: list[str] = []
    if not targets:
        structural_reasons.append("TARGET_OSD_IDS_REQUIRED")
    if not allowed:
        structural_reasons.append("OSD_ALLOWLIST_EMPTY")
    if set(targets) - set(source_osds):
        structural_reasons.append("TARGET_OUTSIDE_UPGRADE_SOURCE_SET")
    if set(source_osds) - set(allowed):
        structural_reasons.append("RUN_SOURCE_OUTSIDE_ALLOWLIST")
    if set(targets) - set(allowed):
        structural_reasons.append("TARGET_OUTSIDE_ALLOWLIST")
    identity_fields = (
        ("cluster_id", run.get("cluster_id"), collection.get("cluster_id")),
        ("fsid", run.get("fsid", run.get("cluster_fsid")), collection.get("fsid", collection.get("cluster_fsid"))),
        ("session_id", run.get("session_id"), collection.get("session_id")),
        ("config_snapshot_id", run.get("config_snapshot_id"), collection.get("config_snapshot_id")),
    )
    for field, run_value, collection_value in identity_fields:
        if not run_value or not collection_value:
            structural_reasons.append(f"{field.upper()}_MISSING")
        elif str(run_value) != str(collection_value):
            structural_reasons.append(f"{field.upper()}_MISMATCH")
    if collection.get("phase") not in {"BEFORE", "DURING"}:
        structural_reasons.append("PHASE_NOT_PRE_DOWN_SET")
    if requested != allowed:
        structural_reasons.append("COLLECTION_NOT_CLUSTER_WIDE")
    if not _valid_sha256(artifact_sha256):
        structural_reasons.append("ARTIFACT_SHA256_INVALID")
    if structural_reasons:
        return _result(
            "BLOCKED",
            structural_reasons,
            target_osd_ids=targets,
            observed=observed,
        )

    if collection_state != "COMPLETE":
        return _result(
            "HOLD",
            ["COLLECTION_NOT_COMPLETE"],
            target_osd_ids=targets,
            observed=observed,
        )
    if collection_quality != "VALID":
        return _result(
            "INCONCLUSIVE",
            ["COLLECTION_NOT_VALID"],
            target_osd_ids=targets,
            observed=observed,
        )

    collected_at = _timestamp(
        collection.get("collected_at")
        or collection.get("finished_at")
        or collection.get("created_at")
    )
    if collected_at is None:
        return _result(
            "INCONCLUSIVE",
            ["COLLECTION_TIMESTAMP_MISSING_OR_INVALID"],
            target_osd_ids=targets,
            observed=observed,
        )
    now_utc = _timestamp(now)
    if now_utc is None:
        raise ValueError("now must be a datetime")
    age_seconds = (now_utc - collected_at).total_seconds()
    observed["age_seconds"] = age_seconds
    observed["max_age_seconds"] = max_age_seconds
    if age_seconds < -clock_skew_seconds:
        return _result(
            "INCONCLUSIVE",
            ["COLLECTION_TIMESTAMP_IN_FUTURE"],
            target_osd_ids=targets,
            observed=observed,
        )
    if age_seconds > max_age_seconds:
        return _result(
            "HOLD",
            ["COLLECTION_STALE"],
            target_osd_ids=targets,
            observed=observed,
        )

    records = collection.get("osds")
    if not isinstance(records, list):
        return _result(
            "INCONCLUSIVE",
            ["OSD_RECORDS_MISSING"],
            target_osd_ids=targets,
            observed=observed,
        )

    by_id: dict[int, Mapping[str, Any]] = {}
    duplicates: list[int] = []
    invalid_record_ids = False
    for record in records:
        if not isinstance(record, Mapping) or "osd_id" not in record:
            continue
        try:
            osd_id = int(record["osd_id"])
        except (TypeError, ValueError):
            invalid_record_ids = True
            continue
        if osd_id in by_id:
            duplicates.append(osd_id)
        by_id[osd_id] = record
    if invalid_record_ids:
        return _result(
            "INCONCLUSIVE",
            ["OSD_RECORD_ID_INVALID"],
            target_osd_ids=targets,
            observed=observed,
        )
    if duplicates:
        observed["duplicate_osd_ids"] = sorted(set(duplicates))
        return _result(
            "BLOCKED",
            ["DUPLICATE_OSD_RECORDS"],
            target_osd_ids=targets,
            observed=observed,
        )

    missing = sorted(set(allowed) - set(by_id))
    unexpected = sorted(set(by_id) - set(allowed))
    if missing or unexpected:
        observed["missing_osd_ids"] = missing
        observed["unexpected_osd_ids"] = unexpected
        return _result(
            "INCONCLUSIVE",
            ["OSD_RECORD_SCOPE_MISMATCH"],
            target_osd_ids=targets,
            observed=observed,
        )

    invalid_quality = sorted(
        osd_id
        for osd_id in allowed
        if by_id[osd_id].get("quality", by_id[osd_id].get("quality_status")) != "VALID"
    )
    if invalid_quality:
        observed["invalid_quality_osd_ids"] = invalid_quality
        return _result(
            "INCONCLUSIVE",
            ["OSD_RECORD_QUALITY_NOT_VALID"],
            target_osd_ids=targets,
            observed=observed,
        )

    unknown_state = sorted(
        osd_id
        for osd_id in allowed
        if not isinstance(by_id[osd_id].get("up"), bool)
        or not isinstance(by_id[osd_id].get("in"), bool)
    )
    if unknown_state:
        observed["unknown_state_osd_ids"] = unknown_state
        return _result(
            "INCONCLUSIVE",
            ["OSD_UP_IN_STATE_UNKNOWN"],
            target_osd_ids=targets,
            observed=observed,
        )

    already_unavailable = sorted(
        osd_id
        for osd_id in allowed
        if by_id[osd_id]["up"] is not True or by_id[osd_id]["in"] is not True
    )
    observed["already_unavailable_osd_ids"] = already_unavailable
    target_already_unavailable = sorted(set(targets) & set(already_unavailable))
    if target_already_unavailable:
        observed["target_already_unavailable_osd_ids"] = target_already_unavailable
        return _result(
            "HOLD",
            ["TARGET_ALREADY_NOT_UP_IN"],
            target_osd_ids=targets,
            observed=observed,
        )

    parameters = run.get("parameters") or {}
    try:
        max_simultaneous_down = int(parameters["max_simultaneous_down"])
    except (KeyError, TypeError, ValueError):
        return _result(
            "BLOCKED",
            ["MAX_SIMULTANEOUS_DOWN_MISSING_OR_INVALID"],
            target_osd_ids=targets,
            observed=observed,
        )
    if max_simultaneous_down <= 0:
        return _result(
            "BLOCKED",
            ["MAX_SIMULTANEOUS_DOWN_MISSING_OR_INVALID"],
            target_osd_ids=targets,
            observed=observed,
        )

    projected_unavailable = sorted(set(already_unavailable) | set(targets))
    observed["max_simultaneous_down"] = max_simultaneous_down
    observed["projected_unavailable_osd_ids"] = projected_unavailable
    if len(projected_unavailable) > max_simultaneous_down:
        return _result(
            "HOLD",
            ["MAX_SIMULTANEOUS_DOWN_EXCEEDED"],
            target_osd_ids=targets,
            observed=observed,
        )

    return _result(
        "READY",
        [],
        target_osd_ids=targets,
        observed=observed,
    )
