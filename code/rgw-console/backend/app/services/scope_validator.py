from collections.abc import Iterable
from typing import Any
from uuid import UUID

from ..config import Settings, get_settings
from ..models.api import ApiErrorDetail
from ..models.domain import RgwScopeTarget


class InvalidScopeError(ValueError):
    code = "INVALID_SCOPE"
    status_code = 422
    retryable = False

    def __init__(self, message: str, *, observed_state: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.observed_state = observed_state

    def as_error_detail(self, request_id: UUID) -> ApiErrorDetail:
        return ApiErrorDetail(
            request_id=request_id,
            code=self.code,
            message=self.message,
            retryable=self.retryable,
            observed_state=self.observed_state,
        )


class ScopeValidator:
    """Fail-closed validation for every RGW read and mutation target.

    The bucket allowlist applies to all operations. ``streaming=True`` adds the
    stricter configured stream-prefix boundary so workers cannot expand their
    ownership scope. S3 keys are not filesystem paths, but path-like ambiguous
    segments are rejected because these keys are later used as ownership scope.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        allowed_buckets: Iterable[str] | None = None,
        stream_prefix_root: str | None = None,
    ):
        if settings is not None and (allowed_buckets is not None or stream_prefix_root is not None):
            raise ValueError("pass Settings or explicit scope values, not both")
        if settings is None and allowed_buckets is None and stream_prefix_root is None:
            settings = get_settings()

        if settings is not None:
            self._allowed_buckets = settings.rgw_allowed_bucket_set
            self._stream_prefix_root = settings.rgw_stream_prefix_root
        else:
            self._allowed_buckets = frozenset(item for item in (allowed_buckets or ()) if item)
            if "*" in self._allowed_buckets:
                raise ValueError("wildcards are not allowed in RGW bucket allowlists")
            self._stream_prefix_root = self._normalize_configured_root(stream_prefix_root or "")

    @property
    def allowed_buckets(self) -> frozenset[str]:
        return self._allowed_buckets

    @property
    def stream_prefix_root(self) -> str:
        return self._stream_prefix_root

    @staticmethod
    def _normalize_configured_root(value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        ScopeValidator._validate_s3_path(value, kind="stream prefix root", allow_empty=False)
        if len(value.rstrip("/").encode("utf-8")) > 1023:
            raise InvalidScopeError("stream prefix root is too long")
        return value.rstrip("/") + "/"

    @staticmethod
    def _validate_s3_path(value: str, *, kind: str, allow_empty: bool) -> str:
        if not isinstance(value, str):
            raise InvalidScopeError(f"{kind} must be a string")
        if not value:
            if allow_empty:
                return value
            raise InvalidScopeError(f"{kind} must not be empty")
        if value != value.strip():
            raise InvalidScopeError(f"{kind} must not have leading or trailing whitespace")
        if value.startswith("/") or "\\" in value:
            raise InvalidScopeError(f"{kind} must be a relative S3 path")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise InvalidScopeError(f"{kind} contains a control character")
        if len(value.encode("utf-8")) > 1024:
            raise InvalidScopeError(f"{kind} exceeds the S3 key length limit")

        without_trailing_slash = value[:-1] if value.endswith("/") else value
        parts = without_trailing_slash.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise InvalidScopeError(f"{kind} contains an unsafe path segment")
        return value

    def require_bucket(self, bucket: str) -> str:
        if not isinstance(bucket, str) or not bucket or bucket != bucket.strip():
            raise InvalidScopeError("bucket must be a non-empty exact name")
        if "/" in bucket or "\\" in bucket or any(
            ord(char) < 32 or ord(char) == 127 for char in bucket
        ):
            raise InvalidScopeError("bucket contains unsupported characters")
        if len(bucket.encode("utf-8")) > 255:
            raise InvalidScopeError("bucket name is too long")
        if bucket not in self._allowed_buckets:
            reason = "RGW bucket allowlist is not configured" if not self._allowed_buckets else "bucket is outside the RGW allowlist"
            raise InvalidScopeError(
                reason,
                observed_state={"bucket": bucket, "scope": "RGW_BUCKET"},
            )
        return bucket

    def require_prefix(self, bucket: str, prefix: str, *, streaming: bool = False) -> str:
        self.require_bucket(bucket)
        prefix = self._validate_s3_path(prefix, kind="prefix", allow_empty=not streaming)
        if streaming:
            self._require_stream_boundary(prefix, kind="prefix")
        return prefix

    def require_key(self, bucket: str, key: str, *, streaming: bool = False) -> str:
        self.require_bucket(bucket)
        key = self._validate_s3_path(key, kind="object key", allow_empty=False)
        if streaming:
            self._require_stream_boundary(key, kind="object key")
        return key

    def _require_stream_boundary(self, value: str, *, kind: str) -> None:
        if not self._stream_prefix_root:
            raise InvalidScopeError(
                "RGW stream prefix root is not configured",
                observed_state={"scope": "RGW_STREAM_PREFIX", "configured": False},
            )
        if not value.startswith(self._stream_prefix_root):
            raise InvalidScopeError(
                f"{kind} is outside the RGW stream prefix root",
                observed_state={"scope": "RGW_STREAM_PREFIX"},
            )

    def build_stream_prefix(self, relative_prefix: str = "") -> str:
        if not self._stream_prefix_root:
            raise InvalidScopeError(
                "RGW stream prefix root is not configured",
                observed_state={"scope": "RGW_STREAM_PREFIX", "configured": False},
            )
        if not relative_prefix:
            return self._stream_prefix_root
        relative_prefix = self._validate_s3_path(
            relative_prefix,
            kind="relative stream prefix",
            allow_empty=False,
        )
        return f"{self._stream_prefix_root}{relative_prefix.rstrip('/')}/"

    def validate_rgw_target(self, target: RgwScopeTarget) -> RgwScopeTarget:
        self.require_bucket(target.bucket)
        if target.key is not None and target.prefix is not None:
            raise InvalidScopeError("an RGW target cannot contain both key and prefix")
        if target.key is not None:
            self.require_key(target.bucket, target.key, streaming=target.streaming)
        elif target.prefix is not None:
            self.require_prefix(target.bucket, target.prefix, streaming=target.streaming)
        elif target.streaming:
            raise InvalidScopeError("a streaming RGW target requires a key or prefix")
        return target
