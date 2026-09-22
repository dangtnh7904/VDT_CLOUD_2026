from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv_set(value: str) -> frozenset[str]:
    """Parse a comma-separated allowlist without accepting empty entries."""

    return frozenset(item.strip() for item in value.split(",") if item.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    rgw_endpoint_url: str
    rgw_access_key: str
    rgw_secret_key: str
    rgw_default_bucket: str = "test-data"
    # An empty allowlist is deliberately fail-closed. Operators must explicitly
    # name every lab bucket the console is allowed to read or mutate.
    rgw_allowed_buckets: str = ""
    # Empty means that streaming mutation is disabled until a root is chosen.
    rgw_stream_prefix_root: str = ""
    rgw_affected_pools: str = ""
    rgw_admin_mode: Literal["current_s3_identity", "admin_ops"] = "current_s3_identity"

    database_url: str = "postgresql://rgw:rgw@localhost:5432/rgw_console"
    corpus_mixed_root: Path = Path("/data/mix-file-corpus")
    corpus_size_root: Path = Path("/data/size-file-corpus")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    ceph_expected_fsid: str | None = None
    ceph_cluster_name: str = "ceph"
    ceph_agent_socket: Path = Path("/run/rgw-console/ceph-agent.sock")

    # Privileged RBD actions remain disabled while either allowlist is empty.
    rbd_allowed_pools: str = ""
    rbd_allowed_namespaces: str = ""
    rbd_image_prefix: str = "rgw-console-"
    rbd_mount_root: Path = Path("/srv/ceph-lab/rbd")
    rbd_default_capacity_mode: Literal["reserved-logical"] = "reserved-logical"

    # Capacity policy defaults mirror the plan. Unknown byte budgets stay None;
    # future admission code must block instead of silently treating them as zero.
    capacity_observe_only: bool = True
    capacity_hard_ceiling_ratio: float = Field(default=0.70, gt=0, le=1)
    capacity_admission_stop_ratio: float = Field(default=0.68, gt=0, lt=1)
    capacity_throttle_start_ratio: float = Field(default=0.67, ge=0, lt=1)
    capacity_resume_ratio: float = Field(default=0.67, ge=0, lt=1)
    capacity_collector_interval_seconds: float = Field(default=2.0, gt=0)
    capacity_metrics_max_age_seconds: float = Field(default=5.0, gt=0)
    capacity_resume_consecutive_samples: int = Field(default=3, ge=1)
    capacity_operation_lease_seconds: int = Field(default=30, ge=1)
    capacity_settlement_consecutive_samples: int = Field(default=3, ge=1)
    capacity_settlement_min_seconds: float = Field(default=10.0, ge=0)
    capacity_raw_overhead_factor: float = Field(default=1.10, ge=1)
    capacity_fixed_metadata_bytes_per_object: int | None = Field(default=None, ge=0)
    capacity_safety_margin_ratio_per_osd: float = Field(default=0.01, ge=0, lt=1)
    capacity_safety_margin_min_bytes_per_osd: int | None = Field(default=None, ge=0)
    capacity_emergency_maintenance_bytes: int | None = Field(default=None, ge=0)
    capacity_fail_closed_on_osdmap_change: bool = True
    capacity_pause_on_degraded_or_remapped: bool = True
    capacity_require_clean_for_rbd_format: bool = True
    capacity_failure_reserve_mode: Literal["none", "one_osd", "one_host"] = "none"

    @field_validator("rgw_allowed_buckets", "rgw_affected_pools", "rbd_allowed_pools", "rbd_allowed_namespaces")
    @classmethod
    def validate_csv_allowlist(cls, value: str) -> str:
        entries = _csv_set(value)
        if "*" in entries:
            raise ValueError("wildcards are not allowed in resource allowlists")
        if any(any(ord(char) < 32 for char in entry) for entry in entries):
            raise ValueError("control characters are not allowed in resource allowlists")
        return ",".join(sorted(entries))

    @field_validator("rgw_stream_prefix_root")
    @classmethod
    def validate_stream_prefix_root(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if value.startswith("/") or "\\" in value or any(ord(char) < 32 for char in value):
            raise ValueError("RGW stream prefix root must be a relative S3 prefix")
        parts = value.rstrip("/").split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("RGW stream prefix root contains an unsafe path segment")
        if len(value.encode("utf-8")) > 1023:
            raise ValueError("RGW stream prefix root is too long")
        return value.rstrip("/") + "/"

    @field_validator("ceph_expected_fsid")
    @classmethod
    def validate_expected_fsid(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return str(UUID(value.strip()))
        except ValueError as exc:
            raise ValueError("CEPH_EXPECTED_FSID must be a UUID") from exc

    @field_validator("ceph_cluster_name")
    @classmethod
    def validate_cluster_name(cls, value: str) -> str:
        value = value.strip()
        if not value or not all(char.isalnum() or char in "_-" for char in value):
            raise ValueError("CEPH_CLUSTER_NAME contains unsupported characters")
        return value

    @field_validator("rbd_image_prefix")
    @classmethod
    def validate_image_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("RBD_IMAGE_PREFIX must be a non-empty image-name prefix")
        return value

    @model_validator(mode="after")
    def validate_capacity_policy(self):
        if not (
            self.capacity_resume_ratio
            <= self.capacity_throttle_start_ratio
            <= self.capacity_admission_stop_ratio
            < self.capacity_hard_ceiling_ratio
        ):
            raise ValueError(
                "capacity ratios must satisfy resume <= throttle <= admission < hard ceiling"
            )
        if self.capacity_metrics_max_age_seconds < self.capacity_collector_interval_seconds:
            raise ValueError(
                "CAPACITY_METRICS_MAX_AGE_SECONDS must be at least the collector interval"
            )
        return self

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def rgw_allowed_bucket_set(self) -> frozenset[str]:
        return _csv_set(self.rgw_allowed_buckets)

    @property
    def rbd_allowed_pool_set(self) -> frozenset[str]:
        return _csv_set(self.rbd_allowed_pools)

    @property
    def rgw_affected_pool_set(self) -> frozenset[str]:
        return _csv_set(self.rgw_affected_pools)

    @property
    def rbd_allowed_namespace_set(self) -> frozenset[str]:
        return _csv_set(self.rbd_allowed_namespaces)

    @property
    def corpus_roots(self) -> dict[str, Path]:
        return {
            "mixed": self.corpus_mixed_root.resolve(),
            "size": self.corpus_size_root.resolve(),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
