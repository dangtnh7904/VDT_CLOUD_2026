from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class CollectionPhase(str, Enum):
    MANUAL = "MANUAL"
    BEFORE = "BEFORE"
    DURING = "DURING"
    AFTER_START = "AFTER_START"
    AFTER_STABLE = "AFTER_STABLE"


class Quality(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    INCONCLUSIVE = "INCONCLUSIVE"


QUALITY_RANK = {
    Quality.VALID: 0,
    Quality.PARTIAL: 1,
    Quality.INCONCLUSIVE: 2,
}


class OsdInfoError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        observed_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.observed_state = observed_state or {}


@dataclass(frozen=True)
class ValidatedCollection:
    raw: dict[str, Any]
    cluster_fsid: str
    collected_at: datetime
    collector_version: str
    quality: Quality
    cluster_summary: dict[str, Any]
    records: tuple[dict[str, Any], ...]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _first_known(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _quality(value: Any, *, field: str) -> Quality:
    try:
        return Quality(value)
    except (TypeError, ValueError) as exc:
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", f"{field} has an invalid quality") from exc


def _timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector timestamp must include a timezone")
    return parsed


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item})


def _evidence_data(cluster_evidence: dict[str, Any], key: str) -> Any:
    envelope = _mapping(cluster_evidence.get(key))
    return envelope.get("data") if envelope.get("exit_code") == 0 else None


def _pool_summaries(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else _mapping(value).get("pools")
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pool_type = _optional_text(row.get("type_name"))
        if pool_type is None and isinstance(row.get("type"), (str, int)):
            pool_type = row.get("type")
        crush_rule = _optional_text(row.get("crush_rule_name"))
        if crush_rule is None and isinstance(row.get("crush_rule"), (str, int)):
            crush_rule = row.get("crush_rule")
        result.append({
            "pool_id": _optional_int(row.get("pool", row.get("pool_id"))),
            "pool_name": _optional_text(row.get("pool_name")),
            "type": pool_type,
            "size": _optional_int(row.get("size")),
            "min_size": _optional_int(row.get("min_size")),
            "pg_num": _optional_int(row.get("pg_num")),
            "pgp_num": _optional_int(row.get("pgp_num", row.get("pg_placement_num"))),
            "crush_rule": crush_rule,
            "erasure_code_profile": _optional_text(row.get("erasure_code_profile")),
        })
    return sorted(result, key=lambda row: (row["pool_id"] is None, row["pool_id"], row["pool_name"] or ""))


def _cluster_summary(raw: dict[str, Any]) -> dict[str, Any]:
    evidence = _mapping(raw.get("cluster_evidence"))
    status = _mapping(_evidence_data(evidence, "status"))
    health_detail = _mapping(_evidence_data(evidence, "health_detail"))
    pg_stat = _mapping(_evidence_data(evidence, "pg_stat"))
    osd_dump = _mapping(_evidence_data(evidence, "osd_dump"))
    osdmap = _mapping(status.get("osdmap"))
    pgmap = _mapping(status.get("pgmap"))
    health = _mapping(status.get("health"))
    checks = health_detail.get("checks", health.get("checks"))
    flags_value = osd_dump.get("flags_set", osd_dump.get("flags"))
    if isinstance(flags_value, str):
        flags = sorted({item.strip() for item in flags_value.split(",") if item.strip()})
    else:
        flags = _strings(flags_value)
    versions = _evidence_data(evidence, "versions")
    return {
        "health_status": _optional_text(health_detail.get("status")) or _optional_text(health.get("status")),
        "health_checks": checks if isinstance(checks, dict) else {},
        "osdmap_epoch": _first_known(
            _optional_int(osdmap.get("epoch")), _optional_int(osd_dump.get("epoch"))
        ),
        "cluster_flags": flags,
        "pool_summaries": _pool_summaries(_evidence_data(evidence, "pool_ls_detail")),
        "version_summary": versions if isinstance(versions, dict) else {},
        "cluster_pg_count": _first_known(
            _optional_int(pg_stat.get("num_pgs")), _optional_int(pgmap.get("num_pgs"))
        ),
        "cluster_osd_count": _optional_int(osdmap.get("num_osds")),
        "cluster_up_osd_count": _optional_int(osdmap.get("num_up_osds")),
        "cluster_in_osd_count": _optional_int(osdmap.get("num_in_osds")),
    }


def validate_collection(
    raw: dict[str, Any],
    *,
    expected_fsid: str,
    requested_osd_ids: tuple[int, ...],
) -> ValidatedCollection:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector payload has an unsupported schema")
    if raw.get("kind") != "CEPH_OSD_BASELINE":
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector payload kind is invalid")
    try:
        cluster_fsid = str(UUID(str(raw.get("cluster_fsid"))))
    except (TypeError, ValueError, AttributeError) as exc:
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector payload is missing a valid FSID") from exc
    if cluster_fsid != expected_fsid:
        raise OsdInfoError(
            "FSID_MISMATCH",
            "OSD inventory came from a different Ceph cluster",
            observed_state={"expected_fsid": expected_fsid, "observed_fsid": cluster_fsid},
        )
    collector_version = _optional_text(raw.get("collector_version"))
    if collector_version is None:
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector version is missing")
    osds = raw.get("osds")
    if not isinstance(osds, list):
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector OSD list is invalid")

    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    collection_quality = _quality(raw.get("quality"), field="collection")
    for item in osds:
        if not isinstance(item, dict):
            raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector returned a non-object OSD record")
        identity = _mapping(item.get("identity"))
        osd_id = _optional_int(identity.get("osd_id"))
        if osd_id is None or osd_id < 0 or osd_id in seen:
            raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector returned an invalid or duplicate OSD ID")
        seen.add(osd_id)
        version = _mapping(item.get("version"))
        network = _mapping(item.get("network"))
        devices = _mapping(item.get("devices"))
        data_device = _mapping(devices.get("data"))
        db_device = _mapping(devices.get("db"))
        wal_device = _mapping(devices.get("wal"))
        capacity = _mapping(item.get("capacity"))
        state = _mapping(item.get("state"))
        pgs = _mapping(item.get("placement_groups"))
        warnings = _strings(item.get("warnings"))
        row_quality = _quality(item.get("quality"), field=f"osd.{osd_id}")
        crush_location = _mapping(identity.get("crush_location"))
        device_class = _optional_text(identity.get("device_class"))

        core_values = (
            _optional_text(identity.get("osd_fsid")),
            _optional_int(capacity.get("total_bytes")),
            _optional_int(capacity.get("used_bytes")),
            _optional_int(capacity.get("available_bytes")),
            _optional_number(capacity.get("used_percent")),
            _optional_int(pgs.get("count")),
            _optional_int(pgs.get("primary_count")),
            _optional_bool(state.get("up")),
            _optional_bool(state.get("in")),
        )
        if any(value is None for value in core_values):
            row_quality = Quality.INCONCLUSIVE
            warnings = sorted(set(warnings) | {"CORE_PLANNING_FIELD_MISSING"})
        if not crush_location:
            warnings = sorted(set(warnings) | {"CRUSH_LOCATION_NOT_REPORTED"})
        if device_class is None:
            warnings = sorted(set(warnings) | {"DEVICE_CLASS_NOT_REPORTED"})
        if (
            _optional_text(identity.get("hostname")) is None
            or not crush_location
            or device_class is None
            or _optional_text(version.get("ceph_version")) is None
            or _optional_text(network.get("public_ip")) is None
            or _optional_text(data_device.get("path")) is None
            or not _strings(data_device.get("physical_devices"))
        ) and QUALITY_RANK[row_quality] < QUALITY_RANK[Quality.PARTIAL]:
            row_quality = Quality.PARTIAL
            warnings = sorted(set(warnings) | {"OPTIONAL_INVENTORY_FIELD_MISSING"})

        collection_quality = max(
            (collection_quality, row_quality),
            key=lambda value: QUALITY_RANK[value],
        )
        records.append(
            {
                "osd_id": osd_id,
                "quality": row_quality.value,
                "warnings": warnings,
                "errors": item.get("errors") if isinstance(item.get("errors"), list) else [],
                "osd_fsid": _optional_text(identity.get("osd_fsid")),
                "hostname": _optional_text(identity.get("hostname")),
                "crush_location": crush_location,
                "device_class": device_class,
                "public_ip": _optional_text(network.get("public_ip")),
                "public_ips": _strings(network.get("public_ips")),
                "cluster_ip": _optional_text(network.get("cluster_ip")),
                "cluster_ips": _strings(network.get("cluster_ips")),
                "data_device_path": _optional_text(data_device.get("path")),
                "data_device_size_bytes": _optional_int(data_device.get("size_bytes")),
                "physical_devices": _strings(data_device.get("physical_devices")),
                "db_device_path": _optional_text(db_device.get("path")),
                "db_device_size_bytes": _optional_int(db_device.get("size_bytes")),
                "db_physical_devices": _strings(db_device.get("physical_devices")),
                "wal_device_path": _optional_text(wal_device.get("path")),
                "wal_device_size_bytes": _optional_int(wal_device.get("size_bytes")),
                "wal_physical_devices": _strings(wal_device.get("physical_devices")),
                "device_ids": _strings(devices.get("device_ids")),
                "total_bytes": _optional_int(capacity.get("total_bytes")),
                "used_bytes": _optional_int(capacity.get("used_bytes")),
                "available_bytes": _optional_int(capacity.get("available_bytes")),
                "used_percent": _optional_number(capacity.get("used_percent")),
                "pg_count": _optional_int(pgs.get("count")),
                "primary_count": _optional_int(pgs.get("primary_count")),
                "up": _optional_bool(state.get("up")),
                "in": _optional_bool(state.get("in")),
                "daemon_status": _optional_text(state.get("status")),
                "crush_weight": _optional_number(state.get("crush_weight")),
                "reweight": _optional_number(state.get("reweight")),
                "primary_affinity": _optional_number(state.get("primary_affinity")),
                "ceph_version": _optional_text(version.get("ceph_version")),
                "ceph_version_short": _optional_text(version.get("ceph_version_short")),
                "container_image": _optional_text(version.get("container_image")),
                "container_image_id": _optional_text(version.get("container_image_id")),
                "payload": item,
            }
        )

    requested = set(requested_osd_ids)
    if seen != requested:
        raise OsdInfoError(
            "COLLECTOR_PROTOCOL_ERROR",
            "collector result does not match the requested OSD set",
            observed_state={"requested_osd_ids": sorted(requested), "returned_osd_ids": sorted(seen)},
        )
    if raw.get("osd_count") != len(records):
        raise OsdInfoError("COLLECTOR_PROTOCOL_ERROR", "collector OSD count does not match its payload")
    return ValidatedCollection(
        raw=raw,
        cluster_fsid=cluster_fsid,
        collected_at=_timestamp(raw.get("collected_at")),
        collector_version=collector_version,
        quality=collection_quality,
        cluster_summary=_cluster_summary(raw),
        records=tuple(sorted(records, key=lambda row: row["osd_id"])),
    )
