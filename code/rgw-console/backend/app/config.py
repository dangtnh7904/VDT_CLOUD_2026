import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .platform.security.passwords import validate_password_hash


def _csv_set(value: str) -> frozenset[str]:
    """Parse a comma-separated allowlist without accepting empty entries."""

    return frozenset(item.strip() for item in value.split(",") if item.strip())


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _normalize_http_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be HTTP(S) and include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain credentials")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("URL must not include a path, query, or fragment")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    # The upgrade controller and the legacy tools are independently switchable.
    # Legacy credentials are optional at model construction time so an
    # upgrade-only deployment can start without S3 credentials. The explicit
    # feature readiness check below is run during application startup.
    app_env: Literal["lab", "development", "test", "production"] = "lab"
    app_instance_id: str = "storage-lab-console"
    lab_profile: str = ""
    cluster_config_path: Path | None = None
    log_level: str = "INFO"
    # Production serves read-only inventory behind authenticated
    # HTTPS ingress. Password material is read from a mounted hash file only.
    console_read_only: bool = False
    console_auth_username: str = ""
    console_auth_password_hash_file: Path | None = None
    console_auth_password_hash: SecretStr | None = Field(default=None, exclude=True)

    feature_upgrade: bool = False
    feature_lab: bool = False
    feature_legacy_rgw: bool = True
    feature_legacy_rbd: bool = True
    upgrade_mutations_enabled: bool = False

    cluster_id: str = ""
    cluster_profile_revision: str = "unversioned"
    policy_revision: str = "default-v1"
    execution_environment: Literal["lab", "staging", "production"] = "lab"

    rgw_endpoint_url: str | None = None
    rgw_access_key: str | None = None
    rgw_secret_key: str | None = None
    rgw_default_bucket: str = "test-data"
    # An empty allowlist is deliberately fail-closed. Operators must explicitly
    # name every lab bucket the console is allowed to read or mutate.
    rgw_allowed_buckets: str = ""
    # Empty means that streaming mutation is disabled until a root is chosen.
    rgw_stream_prefix_root: str = ""
    rgw_affected_pools: str = ""
    rgw_admin_mode: Literal["current_s3_identity", "admin_ops"] = "current_s3_identity"

    database_url: str = "postgresql://rgw:rgw@localhost:5432/rgw_console"
    database_url_file: Path | None = None
    # Set only for the unified API image. Development can leave this unset and
    # continue serving Vite separately.
    frontend_dist_path: Path | None = None
    corpus_mixed_root: Path = Path("/data/mix-file-corpus")
    corpus_size_root: Path = Path("/data/size-file-corpus")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    ceph_expected_fsid: str | None = None
    ceph_cluster_name: str = "ceph"
    ceph_transport: Literal["executor", "ssh"] = "executor"
    ceph_executor_url: str | None = None
    ceph_executor_token: SecretStr | None = None
    ceph_executor_token_file: Path | None = None
    rbd_executor_url: str = "http://rbd-console:3001"
    rbd_executor_token: SecretStr | None = None
    rbd_executor_timeout_seconds: float = Field(default=35, gt=0, le=300)
    rbd_validation_timeout_seconds: float = Field(default=300, gt=0, le=3600)
    osd_info_collector_timeout_seconds: float = Field(default=330, gt=0, le=3600)
    osd_info_collector_max_output_bytes: int = Field(
        default=64 * 1024 * 1024, ge=1024, le=256 * 1024 * 1024
    )
    osdmap_preview_spool: Path | None = None
    osdmap_preview_timeout_seconds: int = Field(default=90, ge=10, le=300)
    osdmap_preview_max_map_bytes: int = Field(default=16 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)

    # Privileged RBD actions remain disabled while either allowlist is empty.
    rbd_allowed_pools: str = ""
    rbd_allowed_namespaces: str = ""
    rbd_image_prefix: str = "rgw-console-"
    rbd_mount_root: Path = Path("/srv/ceph-lab/rbd")
    rbd_default_capacity_mode: Literal["reserved-logical"] = "reserved-logical"
    rbd_action_lease_seconds: int = Field(default=120, ge=10)
    rbd_action_poll_seconds: float = Field(default=1.0, gt=0, le=60)
    rbd_file_preview_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    rbd_file_upload_max_bytes: int = Field(default=16 * 1024 * 1024 * 1024, ge=1024)
    rbd_allowed_preview_mime: str = (
        "text/plain,text/markdown,text/yaml,text/csv,application/json,application/pdf,"
        "image/jpeg,image/png,image/gif,image/webp,image/svg+xml"
    )

    # Maximum deployment scope for production upgrade workflows. Empty means
    # no production resource is authorized.
    upgrade_allowed_osds: str = ""
    upgrade_allowed_hosts: str = ""
    upgrade_allowed_pools: str = ""
    upgrade_allowed_device_classes: str = ""
    upgrade_inventory_max_age_seconds: float = Field(default=45, gt=0, le=86400)

    telemetry_provider: Literal["prometheus", "disabled"] = "disabled"
    telemetry_prometheus_url: str | None = None
    telemetry_prometheus_bearer_token_file: Path | None = None
    telemetry_max_age_seconds: float = Field(default=45, gt=0, le=3600)
    telemetry_clock_skew_max_seconds: float = Field(default=5, ge=0, le=300)

    lab_validation_enabled: bool = False
    lab_allowed_pools: str = ""
    lab_allowed_pg_prefixes: str = ""
    lab_allowed_object_prefixes: str = ""
    lab_allow_write: bool = False

    evidence_store: Literal["filesystem"] = "filesystem"
    evidence_root: Path = Path("./runtime/evidence")
    evidence_retention_days: int = Field(default=30, ge=1, le=3650)
    evidence_max_artifact_bytes: int = Field(
        default=64 * 1024 * 1024, ge=1024, le=16 * 1024 * 1024 * 1024
    )

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

    # Performance telemetry always includes console-observed application I/O.
    # Cluster-wide Ceph counters are opt-in because their identity and metric
    # surface must be verified against the target Pacific cluster first.
    performance_enabled: bool = True
    performance_source: Literal["application_only", "prometheus"] = "application_only"
    performance_prometheus_url: str | None = None
    performance_prometheus_bearer_token: SecretStr | None = None
    performance_collector_interval_seconds: float = Field(default=15.0, ge=10, le=300)
    performance_current_window_seconds: int = Field(default=15, ge=10, le=3600)
    performance_stale_after_seconds: float = Field(default=45.0, ge=10, le=3600)
    performance_raw_retention_hours: int = Field(default=24, ge=1, le=24 * 31)
    performance_rollup_retention_days: int = Field(default=30, ge=1, le=366)

    @field_validator(
        "rgw_allowed_buckets",
        "rgw_affected_pools",
        "rbd_allowed_pools",
        "rbd_allowed_namespaces",
        "upgrade_allowed_osds",
        "upgrade_allowed_hosts",
        "upgrade_allowed_pools",
        "upgrade_allowed_device_classes",
        "lab_allowed_pools",
        "lab_allowed_pg_prefixes",
        "lab_allowed_object_prefixes",
    )
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

    @field_validator("app_instance_id")
    @classmethod
    def validate_app_instance_id(cls, value: str) -> str:
        value = value.strip()
        if not SAFE_ID_RE.fullmatch(value):
            raise ValueError("APP_INSTANCE_ID contains unsupported characters")
        return value

    @field_validator("cluster_id")
    @classmethod
    def validate_cluster_id(cls, value: str) -> str:
        value = value.strip()
        if value and not SAFE_ID_RE.fullmatch(value):
            raise ValueError("CLUSTER_ID contains unsupported characters")
        return value

    @field_validator("cluster_profile_revision", "policy_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        value = value.strip()
        if not SAFE_ID_RE.fullmatch(value):
            raise ValueError("revision contains unsupported characters")
        return value

    @field_validator("rbd_executor_url")
    @classmethod
    def validate_required_executor_url(cls, value: str) -> str:
        normalized = _normalize_http_url(value)
        if normalized is None:
            raise ValueError("RBD_EXECUTOR_URL must not be empty")
        return normalized

    @field_validator(
        "ceph_executor_url",
        "telemetry_prometheus_url",
    )
    @classmethod
    def validate_http_url(cls, value: str | None) -> str | None:
        return _normalize_http_url(value)

    @field_validator("rbd_image_prefix")
    @classmethod
    def validate_image_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("RBD_IMAGE_PREFIX must be a non-empty image-name prefix")
        return value

    @model_validator(mode="after")
    def validate_capacity_policy(self):
        if self.console_auth_password_hash_file is not None:
            try:
                encoded_hash = self.console_auth_password_hash_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ValueError("CONSOLE_AUTH_PASSWORD_HASH_FILE could not be read") from exc
            validate_password_hash(encoded_hash)
            self.console_auth_password_hash = SecretStr(encoded_hash)
        elif self.console_auth_password_hash is not None:
            raise ValueError("console authentication hash must use CONSOLE_AUTH_PASSWORD_HASH_FILE")
        if bool(self.console_auth_username) != bool(self.console_auth_password_hash):
            raise ValueError("console authentication requires both username and password hash file")
        if self.console_auth_username and (
            ":" in self.console_auth_username
            or len(self.console_auth_username) > 128
            or any(ord(char) < 33 for char in self.console_auth_username)
        ):
            raise ValueError("CONSOLE_AUTH_USERNAME contains unsupported characters")
        if self.app_env == "production":
            if not self.console_read_only:
                raise ValueError("APP_ENV=production requires CONSOLE_READ_ONLY=true")
            if not self.console_auth_username or not self.console_auth_password_hash_file:
                raise ValueError("production requires console authentication username and password hash file")
            if not self.origins:
                raise ValueError("production requires explicit HTTPS CORS_ORIGINS")
            for origin in self.origins:
                parsed_origin = urlsplit(origin)
                if (
                    parsed_origin.scheme != "https"
                    or not parsed_origin.hostname
                    or parsed_origin.username
                    or parsed_origin.password
                    or parsed_origin.path
                    or parsed_origin.query
                    or parsed_origin.fragment
                ):
                    raise ValueError("production CORS_ORIGINS must contain HTTPS origins without paths or wildcards")
        if self.console_read_only:
            unsafe = [
                name.upper()
                for name in (
                    "feature_legacy_rgw", "feature_legacy_rbd", "feature_lab",
                    "upgrade_mutations_enabled",
                    "lab_validation_enabled", "lab_allow_write",
                )
                if getattr(self, name)
            ]
            if unsafe or not self.capacity_observe_only:
                if not self.capacity_observe_only:
                    unsafe.append("CAPACITY_OBSERVE_ONLY=false")
                raise ValueError("CONSOLE_READ_ONLY requires disabled mutation features: " + ", ".join(unsafe))
        if self.database_url_file is not None:
            try:
                database_url = self.database_url_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ValueError("DATABASE_URL_FILE could not be read") from exc
            if not database_url:
                raise ValueError("DATABASE_URL_FILE must not be empty")
            self.database_url = database_url
        if self.ceph_executor_token_file is not None:
            try:
                executor_token = self.ceph_executor_token_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ValueError("CEPH_EXECUTOR_TOKEN_FILE could not be read") from exc
            if not executor_token:
                raise ValueError("CEPH_EXECUTOR_TOKEN_FILE must not be empty")
            self.ceph_executor_token = SecretStr(executor_token)
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
        if self.performance_stale_after_seconds < self.performance_collector_interval_seconds:
            raise ValueError(
                "PERFORMANCE_STALE_AFTER_SECONDS must be at least the collector interval"
            )
        if self.performance_current_window_seconds < self.performance_collector_interval_seconds:
            raise ValueError(
                "PERFORMANCE_CURRENT_WINDOW_SECONDS must be at least the collector interval"
            )
        if self.performance_source == "prometheus":
            if not self.performance_prometheus_url:
                raise ValueError(
                    "PERFORMANCE_PROMETHEUS_URL is required when PERFORMANCE_SOURCE=prometheus"
                )
            if not self.ceph_expected_fsid:
                raise ValueError(
                    "CEPH_EXPECTED_FSID is required when PERFORMANCE_SOURCE=prometheus"
                )
        if self.telemetry_provider == "prometheus" and not self.telemetry_prometheus_url:
            raise ValueError(
                "TELEMETRY_PROMETHEUS_URL is required when TELEMETRY_PROVIDER=prometheus"
            )
        if self.upgrade_mutations_enabled and not self.feature_upgrade:
            raise ValueError(
                "UPGRADE_MUTATIONS_ENABLED requires FEATURE_UPGRADE=true"
            )
        if self.lab_allow_write and not (self.feature_lab and self.lab_validation_enabled):
            raise ValueError(
                "LAB_ALLOW_WRITE requires FEATURE_LAB and LAB_VALIDATION_ENABLED"
            )
        return self

    @field_validator("performance_prometheus_url")
    @classmethod
    def validate_prometheus_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("PERFORMANCE_PROMETHEUS_URL must use http or https")
        parsed = urlsplit(value)
        if not parsed.hostname:
            raise ValueError("PERFORMANCE_PROMETHEUS_URL must include a hostname")
        if parsed.username or parsed.password:
            raise ValueError(
                "Prometheus credentials must not be embedded in PERFORMANCE_PROMETHEUS_URL"
            )
        return value

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
    def rbd_allowed_preview_mime_set(self) -> frozenset[str]:
        return _csv_set(self.rbd_allowed_preview_mime)

    @property
    def upgrade_allowed_osd_set(self) -> frozenset[str]:
        return _csv_set(self.upgrade_allowed_osds)

    @property
    def upgrade_allowed_host_set(self) -> frozenset[str]:
        return _csv_set(self.upgrade_allowed_hosts)

    @property
    def upgrade_allowed_pool_set(self) -> frozenset[str]:
        return _csv_set(self.upgrade_allowed_pools)

    @property
    def upgrade_allowed_device_class_set(self) -> frozenset[str]:
        return _csv_set(self.upgrade_allowed_device_classes)

    @property
    def effective_executor_url(self) -> str:
        return self.ceph_executor_url or self.rbd_executor_url

    @property
    def effective_executor_token(self) -> SecretStr | None:
        return self.ceph_executor_token or self.rbd_executor_token

    def validate_feature_dependencies(self) -> None:
        """Validate only dependencies for features enabled by this deployment.

        Keeping this separate from model construction lets tests and offline
        tooling inspect partial configuration while service startup remains
        fail-closed.
        """

        missing: list[str] = []
        if self.feature_legacy_rgw:
            for field_name in ("rgw_endpoint_url", "rgw_access_key", "rgw_secret_key"):
                if not getattr(self, field_name):
                    missing.append(field_name.upper())
        executor_required = (
            self.feature_upgrade
            or self.feature_legacy_rbd
            or (self.feature_lab and self.lab_validation_enabled)
        )
        if self.feature_upgrade:
            if not self.cluster_id.strip():
                missing.append("CLUSTER_ID")
        if executor_required:
            if not self.ceph_expected_fsid:
                missing.append("CEPH_EXPECTED_FSID")
            if not self.effective_executor_token:
                missing.append("CEPH_EXECUTOR_TOKEN or RBD_EXECUTOR_TOKEN")
        if self.upgrade_mutations_enabled:
            if not self.upgrade_allowed_osd_set:
                missing.append("UPGRADE_ALLOWED_OSDS")
            if not self.upgrade_allowed_host_set:
                missing.append("UPGRADE_ALLOWED_HOSTS")
            if not self.upgrade_allowed_pool_set:
                missing.append("UPGRADE_ALLOWED_POOLS")
        if self.feature_lab and self.lab_validation_enabled and not self.lab_allowed_pool_set:
            missing.append("LAB_ALLOWED_POOLS")
        if missing:
            raise ValueError(
                "enabled feature configuration is incomplete: " + ", ".join(sorted(set(missing)))
            )

    @property
    def lab_allowed_pool_set(self) -> frozenset[str]:
        return _csv_set(self.lab_allowed_pools)

    @property
    def corpus_roots(self) -> dict[str, Path]:
        return {
            "mixed": self.corpus_mixed_root.resolve(),
            "size": self.corpus_size_root.resolve(),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
