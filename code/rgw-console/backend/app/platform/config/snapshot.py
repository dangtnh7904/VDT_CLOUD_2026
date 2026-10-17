from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

import yaml

from ...config import Settings


SECRET_FIELD_FRAGMENTS = (
    "access_key",
    "secret",
    "password",
    "private_key",
    "bearer_token",
    "executor_token",
    "database_url",
)

PROFILE_FIELDS = frozenset(
    {
        "app_env",
        "lab_profile",
        "cluster_id",
        "cluster_profile_revision",
        "policy_revision",
        "execution_environment",
        "ceph_expected_fsid",
        "ceph_cluster_name",
        "ceph_transport",
        "ceph_executor_url",
        "upgrade_allowed_osds",
        "upgrade_allowed_hosts",
        "upgrade_allowed_pools",
        "upgrade_allowed_device_classes",
        "upgrade_inventory_max_age_seconds",
        "telemetry_provider",
        "telemetry_prometheus_url",
        "telemetry_max_age_seconds",
        "telemetry_clock_skew_max_seconds",
        "evidence_store",
        "evidence_root",
        "evidence_retention_days",
        "evidence_max_artifact_bytes",
        "osd_info_collector_timeout_seconds",
        "osd_info_collector_max_output_bytes",
    }
)


@dataclass(frozen=True)
class ConfigSnapshot:
    id: UUID
    cluster_id: str
    expected_fsid: str | None
    profile_revision: str
    policy_revision: str
    config_hash: str
    payload: dict[str, Any]
    created_at: datetime


def _is_secret_field(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SECRET_FIELD_FRAGMENTS)


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "get_secret_value"):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_secret_field(str(key)) else _json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return value


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"could not read CLUSTER_CONFIG_PATH: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError("CLUSTER_CONFIG_PATH is not valid YAML") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("cluster profile must be a YAML object")
    normalized = {str(key).strip().lower(): value for key, value in raw.items()}
    unknown = sorted(set(normalized) - PROFILE_FIELDS)
    if unknown:
        raise ValueError(f"cluster profile contains unsupported fields: {', '.join(unknown)}")
    secret_fields = sorted(key for key in normalized if _is_secret_field(key))
    if secret_fields:
        raise ValueError("cluster profile must not contain secrets")
    return normalized


def resolve_settings(settings: Settings) -> Settings:
    """Apply a non-secret profile below explicit environment/.env values."""

    if settings.cluster_config_path is None:
        return settings
    profile = _load_profile(settings.cluster_config_path.resolve())
    merged = settings.model_dump()
    explicitly_configured = set(settings.model_fields_set)
    for key, value in profile.items():
        if key not in explicitly_configured:
            merged[key] = value
    return Settings(_env_file=None, **merged)


def build_config_snapshot(settings: Settings, *, snapshot_id: UUID | None = None) -> ConfigSnapshot:
    resolved = resolve_settings(settings)
    public_payload = _json_value(resolved.model_dump())
    public_payload["feature_readiness"] = {
        "upgrade": resolved.feature_upgrade,
        "lab": resolved.feature_lab,
        "legacy_rgw": resolved.feature_legacy_rgw,
        "legacy_rbd": resolved.feature_legacy_rbd,
        "upgrade_mutations_enabled": resolved.upgrade_mutations_enabled,
    }
    canonical = json.dumps(
        public_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return ConfigSnapshot(
        id=snapshot_id or uuid4(),
        cluster_id=resolved.cluster_id,
        expected_fsid=resolved.ceph_expected_fsid,
        profile_revision=resolved.cluster_profile_revision,
        policy_revision=resolved.policy_revision,
        config_hash=hashlib.sha256(canonical).hexdigest(),
        payload=public_payload,
        created_at=datetime.now(timezone.utc),
    )
