from __future__ import annotations

from typing import Any

from .comparison import compare_collections
from .redaction import redact_collector_evidence


_IDENTITY_FIELDS = {"name", "who", "mask"}


def _config_maps(envelope: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if not isinstance(envelope, dict) or envelope.get("exit_code") != 0:
        return None
    data = envelope.get("data")
    redacted = redact_collector_evidence(data)
    if isinstance(data, dict) and isinstance(redacted, dict):
        if not all(isinstance(key, str) for key in data):
            return None
        return dict(data), dict(redacted)
    if not isinstance(data, list) or not isinstance(redacted, list) or len(data) != len(redacted):
        return None

    raw_map: dict[str, Any] = {}
    display_map: dict[str, Any] = {}
    for raw_row, display_row in zip(data, redacted):
        if not isinstance(raw_row, dict) or not isinstance(display_row, dict):
            return None
        name = raw_row.get("name")
        if not isinstance(name, str) or not name:
            return None
        who = raw_row.get("who") if isinstance(raw_row.get("who"), str) else "*"
        mask = raw_row.get("mask") if isinstance(raw_row.get("mask"), str) else "*"
        option = f"{who} | {mask} | {name}"
        if option in raw_map:
            return None
        raw_map[option] = {key: value for key, value in raw_row.items() if key not in _IDENTITY_FIELDS}
        display_map[option] = {
            key: value for key, value in display_row.items() if key not in _IDENTITY_FIELDS
        }
    return raw_map, display_map


def _diff(before_envelope: Any, after_envelope: Any) -> dict[str, Any]:
    before_maps = _config_maps(before_envelope)
    after_maps = _config_maps(after_envelope)
    if before_maps is None or after_maps is None:
        return {
            "before_available": before_maps is not None,
            "after_available": after_maps is not None,
            "changed_count": 0,
            "added": [],
            "removed": [],
            "changed": [],
        }
    before_raw, before_display = before_maps
    after_raw, after_display = after_maps
    before_keys = set(before_raw)
    after_keys = set(after_raw)
    added = [
        {"option": option, "after": after_display[option]}
        for option in sorted(after_keys - before_keys)
    ]
    removed = [
        {"option": option, "before": before_display[option]}
        for option in sorted(before_keys - after_keys)
    ]
    changed = [
        {
            "option": option,
            "before": before_display[option],
            "after": after_display[option],
        }
        for option in sorted(before_keys & after_keys)
        if before_raw[option] != after_raw[option]
    ]
    return {
        "before_available": True,
        "after_available": True,
        "changed_count": len(added) + len(removed) + len(changed),
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def _osd_payloads(raw: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in raw.get("osds") or []:
        if not isinstance(item, dict):
            continue
        identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
        osd_id = identity.get("osd_id")
        if isinstance(osd_id, int) and not isinstance(osd_id, bool):
            result[osd_id] = item
    return result


def _cluster_config(raw: dict[str, Any]) -> Any:
    cluster = raw.get("cluster_evidence")
    return cluster.get("config_dump") if isinstance(cluster, dict) else None


def _effective_config(item: dict[str, Any] | None) -> Any:
    evidence = item.get("evidence") if isinstance(item, dict) else None
    return evidence.get("config_effective") if isinstance(evidence, dict) else None


def compare_config_evidence(
    before_collection: dict[str, Any],
    after_collection: dict[str, Any],
    before_raw: dict[str, Any],
    after_raw: dict[str, Any],
) -> dict[str, Any]:
    """Compare config values from two verified collector artifacts."""

    indexed = compare_collections(before_collection, after_collection)
    reasons = list(indexed["reasons"])
    cluster_config = _diff(_cluster_config(before_raw), _cluster_config(after_raw))
    if not cluster_config["before_available"]:
        reasons.append("CLUSTER_CONFIG_UNAVAILABLE:BEFORE")
    if not cluster_config["after_available"]:
        reasons.append("CLUSTER_CONFIG_UNAVAILABLE:AFTER")

    before_osds = _osd_payloads(before_raw)
    after_osds = _osd_payloads(after_raw)
    osd_results: list[dict[str, Any]] = []
    for osd_id in sorted(set(before_osds) & set(after_osds)):
        result = _diff(
            _effective_config(before_osds.get(osd_id)),
            _effective_config(after_osds.get(osd_id)),
        )
        result["osd_id"] = osd_id
        osd_results.append(result)
        if not result["before_available"]:
            reasons.append(f"OSD_EFFECTIVE_CONFIG_UNAVAILABLE:{osd_id}:BEFORE")
        if not result["after_available"]:
            reasons.append(f"OSD_EFFECTIVE_CONFIG_UNAVAILABLE:{osd_id}:AFTER")

    if indexed["comparison_status"] == "NOT_COMPARABLE":
        status = "NOT_COMPARABLE"
    elif indexed["comparison_status"] == "INCONCLUSIVE" or reasons:
        status = "INCONCLUSIVE"
    else:
        status = "COMPARABLE"
    return {
        "schema_version": 1,
        "comparison_status": status,
        "reasons": sorted(set(reasons)),
        "sensitive_values_redacted": True,
        "before": indexed["before"],
        "after": indexed["after"],
        "cluster_config": cluster_config,
        "osds": osd_results,
        "summary": {
            "cluster_changed_option_count": cluster_config["changed_count"],
            "osd_changed_option_count": sum(item["changed_count"] for item in osd_results),
            "osd_compared_count": len(osd_results),
        },
    }
