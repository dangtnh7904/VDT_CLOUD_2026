import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel

from ..models.api import ApiErrorDetail
from ..models.domain import (
    IdempotencyClaimRequest,
    IdempotencyClaimResult,
    IdempotencyDisposition,
    IdempotencyRecord,
    IdempotencyState,
)


class DatabaseConnection(Protocol):
    def execute(self, query: str, params: tuple[Any, ...] = ()): ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


ConnectionFactory = Callable[[], AbstractContextManager[DatabaseConnection]]


class IdempotencyError(RuntimeError):
    status_code = 409
    code = "IDEMPOTENCY_ERROR"
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


class IdempotencyConflictError(IdempotencyError):
    code = "IDEMPOTENCY_CONFLICT"


class IdempotencyFenceLostError(IdempotencyError):
    code = "IDEMPOTENCY_FENCE_LOST"


class IdempotencyNotFoundError(IdempotencyError):
    status_code = 404
    code = "IDEMPOTENCY_NOT_FOUND"


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
            return value.isoformat().replace("+00:00", "Z")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            result[key] = _canonical_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset, bytes, bytearray, memoryview)):
        raise TypeError(f"{type(value).__name__} is not valid canonical request JSON")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not valid canonical request JSON")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported canonical request value: {type(value).__name__}")


def canonical_request_fingerprint(
    http_method: str,
    resource: str,
    payload: Any = None,
    *,
    headers: Mapping[str, Any] | None = None,
    content_sha256: str | None = None,
) -> str:
    """Return a deterministic fingerprint for mutation semantics.

    ``resource`` should be a stable logical resource identifier, not a URL with
    unordered query parameters. Callers should pass only semantic headers (for
    example Content-Type or If-Match), never Authorization credentials.
    """

    method = http_method.strip().upper()
    logical_resource = resource.strip()
    if not method or not logical_resource:
        raise ValueError("HTTP method and logical resource are required")
    if content_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", content_sha256):
        raise ValueError("content_sha256 must contain exactly 64 hexadecimal characters")

    normalized_headers: dict[str, Any] = {}
    for key, value in (headers or {}).items():
        normalized_key = key.strip().lower()
        if not normalized_key:
            raise ValueError("canonical header name must not be empty")
        normalized_headers[normalized_key] = _canonical_value(value)

    envelope = {
        "content_sha256": content_sha256.lower() if content_sha256 else None,
        "headers": normalized_headers,
        "method": method,
        "payload": _canonical_value(payload),
        "resource": logical_resource,
    }
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


_SENSITIVE_KEY = re.compile(
    r"(^|[_-])(authorization|password|passwd|secret|secret_key|access_key|credential|keyring)([_-]|$)",
    re.IGNORECASE,
)


def redact_sensitive_data(value: Any) -> Any:
    """Return JSON-compatible data with credential-shaped fields redacted."""

    canonical = _canonical_value(value)
    if isinstance(canonical, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE_KEY.search(key) else redact_sensitive_data(item)
            for key, item in canonical.items()
        }
    if isinstance(canonical, list):
        return [redact_sensitive_data(item) for item in canonical]
    return canonical


_ROW_COLUMNS = """
id, scope, idempotency_key, http_method, resource, request_fingerprint,
state, owner_id, fencing_generation, request_id, action_id, response_status,
response_body, error_code, created_at, updated_at, completed_at
""".strip()


class IdempotencyService:
    """Transactional claim/replay service; migrations own all schema creation."""

    def __init__(self, connection_factory: ConnectionFactory | None = None):
        if connection_factory is None:
            # Lazy import keeps pure fingerprint/model tests independent from
            # application settings and avoids any runtime schema bootstrap.
            from ..db import connection

            connection_factory = connection
        self._connection_factory = connection_factory

    @staticmethod
    def _record(row: Mapping[str, Any]) -> IdempotencyRecord:
        return IdempotencyRecord.model_validate(dict(row))

    @staticmethod
    def _same_request(record: IdempotencyRecord, request: IdempotencyClaimRequest) -> bool:
        return (
            record.request_fingerprint == request.request_fingerprint
            and record.http_method == request.http_method.strip().upper()
            and record.resource == request.resource.strip()
        )

    def claim(self, request: IdempotencyClaimRequest) -> IdempotencyClaimResult:
        method = request.http_method.strip().upper()
        resource = request.resource.strip()
        with self._connection_factory() as conn:
            try:
                inserted = conn.execute(
                    f"""
                    INSERT INTO idempotency_requests (
                      scope, idempotency_key, http_method, resource,
                      request_fingerprint, state, owner_id, fencing_generation,
                      request_id, action_id
                    ) VALUES (%s,%s,%s,%s,%s,'CLAIMED',%s,1,%s,%s)
                    ON CONFLICT (scope, idempotency_key) DO NOTHING
                    RETURNING {_ROW_COLUMNS}
                    """,
                    (
                        request.scope,
                        request.idempotency_key,
                        method,
                        resource,
                        request.request_fingerprint,
                        request.owner_id,
                        request.request_id,
                        request.action_id,
                    ),
                ).fetchone()
                if inserted is not None:
                    conn.commit()
                    return IdempotencyClaimResult(
                        disposition=IdempotencyDisposition.CLAIMED,
                        record=self._record(inserted),
                    )

                existing_row = conn.execute(
                    f"""
                    SELECT {_ROW_COLUMNS}
                    FROM idempotency_requests
                    WHERE scope=%s AND idempotency_key=%s
                    FOR UPDATE
                    """,
                    (request.scope, request.idempotency_key),
                ).fetchone()
                if existing_row is None:
                    raise IdempotencyNotFoundError(
                        "idempotency record disappeared during claim",
                    )
                existing = self._record(existing_row)
                if not self._same_request(existing, request):
                    raise IdempotencyConflictError(
                        "the idempotency key was already used for a different request",
                        observed_state={
                            "state": existing.state.value,
                            "request_id": str(existing.request_id),
                        },
                    )

                if existing.state in {IdempotencyState.FAILED_RETRYABLE, IdempotencyState.CLAIMED}:
                    reclaimed = conn.execute(
                        f"""
                        UPDATE idempotency_requests
                        SET state='CLAIMED', owner_id=%s,
                            fencing_generation=fencing_generation+1,
                            action_id=coalesce(action_id,%s), response_status=NULL,
                            response_body=NULL, error_code=NULL, completed_at=NULL,
                            updated_at=now()
                        WHERE id=%s
                          AND (
                            state='FAILED_RETRYABLE'
                            OR (state='CLAIMED' AND updated_at < now() - interval '60 seconds')
                          )
                        RETURNING {_ROW_COLUMNS}
                        """,
                        (request.owner_id, request.action_id, existing.id),
                    ).fetchone()
                    if reclaimed is None and existing.state is IdempotencyState.FAILED_RETRYABLE:
                        raise IdempotencyFenceLostError(
                            "retryable idempotency claim changed concurrently",
                            observed_state={"request_id": str(existing.request_id)},
                        )
                    if reclaimed is not None:
                        conn.commit()
                        return IdempotencyClaimResult(
                            disposition=IdempotencyDisposition.RETRY_CLAIMED,
                            record=self._record(reclaimed),
                        )

                conn.commit()
                disposition = (
                    IdempotencyDisposition.REPLAY
                    if existing.state in {IdempotencyState.SUCCEEDED, IdempotencyState.FAILED_FINAL}
                    else IdempotencyDisposition.IN_PROGRESS
                )
                return IdempotencyClaimResult(disposition=disposition, record=existing)
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

    def mark_in_progress(
        self,
        scope: str,
        idempotency_key: str,
        *,
        owner_id: str,
        fencing_generation: int,
    ) -> IdempotencyRecord:
        with self._connection_factory() as conn:
            row = conn.execute(
                f"""
                UPDATE idempotency_requests
                SET state='IN_PROGRESS', updated_at=now()
                WHERE scope=%s AND idempotency_key=%s AND owner_id=%s
                  AND fencing_generation=%s AND state='CLAIMED'
                RETURNING {_ROW_COLUMNS}
                """,
                (scope, idempotency_key, owner_id, fencing_generation),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise IdempotencyFenceLostError(
                    "idempotency claim is no longer owned by this generation",
                    observed_state={"scope": scope, "fencing_generation": fencing_generation},
                )
            conn.commit()
            return self._record(row)

    def finish(
        self,
        scope: str,
        idempotency_key: str,
        *,
        owner_id: str,
        fencing_generation: int,
        state: IdempotencyState,
        response_status: int,
        response_body: Any = None,
        error_code: str | None = None,
    ) -> IdempotencyRecord:
        if state not in {
            IdempotencyState.SUCCEEDED,
            IdempotencyState.FAILED_RETRYABLE,
            IdempotencyState.FAILED_FINAL,
        }:
            raise ValueError("finish state must be terminal or retryable failure")
        if not 100 <= response_status <= 599:
            raise ValueError("response_status must be a valid HTTP status")
        if state is not IdempotencyState.SUCCEEDED and not error_code:
            raise ValueError("failed idempotency results require an error_code")

        stored_body = None
        if response_body is not None:
            stored_body = json.dumps(
                redact_sensitive_data(response_body),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        with self._connection_factory() as conn:
            row = conn.execute(
                f"""
                UPDATE idempotency_requests
                SET state=%s, response_status=%s, response_body=%s::jsonb,
                    error_code=%s, completed_at=now(), updated_at=now()
                WHERE scope=%s AND idempotency_key=%s AND owner_id=%s
                  AND fencing_generation=%s AND state IN ('CLAIMED','IN_PROGRESS')
                RETURNING {_ROW_COLUMNS}
                """,
                (
                    state.value,
                    response_status,
                    stored_body,
                    error_code,
                    scope,
                    idempotency_key,
                    owner_id,
                    fencing_generation,
                ),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise IdempotencyFenceLostError(
                    "idempotency result was rejected by the fencing generation",
                    observed_state={"scope": scope, "fencing_generation": fencing_generation},
                )
            conn.commit()
            return self._record(row)

    def get(self, scope: str, idempotency_key: str) -> IdempotencyRecord:
        with self._connection_factory() as conn:
            row = conn.execute(
                f"""
                SELECT {_ROW_COLUMNS}
                FROM idempotency_requests
                WHERE scope=%s AND idempotency_key=%s
                """,
                (scope, idempotency_key),
            ).fetchone()
        if row is None:
            raise IdempotencyNotFoundError("idempotency request was not found")
        return self._record(row)
