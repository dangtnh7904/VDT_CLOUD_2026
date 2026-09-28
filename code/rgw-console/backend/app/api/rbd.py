from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid5

import httpx
from fastapi import APIRouter, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed

from ..config import get_settings
from ..db import connection, record_operation
from ..models.domain import (
    IdempotencyClaimRequest,
    IdempotencyDisposition,
    IdempotencyState,
)
from ..services.capacity_guard import CapacityRejected, decide, finish_reservation, require_admission
from ..services.idempotency import IdempotencyService, canonical_request_fingerprint
from ..services.executor_client import ExecutorClient, ExecutorClientError


router = APIRouter(prefix="/api/rbd", tags=["rbd"])
terminal_router = APIRouter(tags=["rbd-terminal"])
idempotency_service = IdempotencyService()
MIB = 1024 * 1024
ACTION_NAMESPACE = UUID("816aa426-1a42-4a60-9d67-d5179c99cb94")


class RbdControlError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        observed_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.observed_state = observed_state


class VolumeCreateRequest(BaseModel):
    pool: str = Field(min_length=1, max_length=255)
    namespace: str | None = Field(default=None, max_length=255)
    logical_size_bytes: int = Field(ge=16 * MIB, le=1 << 40)
    capacity_mode: Literal["reserved-logical"] = "reserved-logical"
    filesystem: Literal["ext4"] = "ext4"
    auto_mount: bool
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    image_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )

    @field_validator("pool", "namespace", "display_name", "image_name")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("logical_size_bytes")
    @classmethod
    def require_mib_alignment(cls, value: int) -> int:
        if value % MIB:
            raise ValueError("logical_size_bytes must be aligned to 1 MiB")
        return value


class FilePathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class ValidationBaselineRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    baseline_label: str = Field(default="pre-upgrade", min_length=1, max_length=255)
    paths: list[str] = Field(min_length=1, max_length=100)

    @field_validator("name", "baseline_label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("paths")
    @classmethod
    def unique_paths(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("paths must not contain duplicates")
        if any(not path or len(path) > 4096 for path in value):
            raise ValueError("each validation path must contain 1 to 4096 characters")
        return value


def _json_value(value: Any) -> Any:
    if isinstance(value, (UUID, datetime)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _default_namespace_allowed(namespace: str | None) -> str:
    return namespace or "default"


def _assert_scope(
    pool: str,
    namespace: str | None,
    image_name: str | None = None,
) -> None:
    settings = get_settings()
    if not settings.rbd_allowed_pool_set or pool not in settings.rbd_allowed_pool_set:
        raise RbdControlError(
            422,
            "INVALID_SCOPE",
            "RBD pool is outside the configured allowlist",
            observed_state={"pool": pool},
        )
    namespace_name = _default_namespace_allowed(namespace)
    if (
        not settings.rbd_allowed_namespace_set
        or namespace_name not in settings.rbd_allowed_namespace_set
    ):
        raise RbdControlError(
            422,
            "INVALID_SCOPE",
            "RBD namespace is outside the configured allowlist",
            observed_state={"namespace": namespace_name},
        )
    if image_name is not None and not image_name.startswith(settings.rbd_image_prefix):
        raise RbdControlError(
            422,
            "INVALID_SCOPE",
            "RBD image name does not use the configured console prefix",
        )


def _step_action_id(action_id: UUID | str, step: str) -> UUID:
    return uuid5(UUID(str(action_id)), step)


def _volume_result(row: dict[str, Any], *, can_retry_busy_mount: bool = False) -> dict[str, Any]:
    result = _json_value(dict(row))
    result["namespace"] = result.get("namespace") or ""
    result["can_retry_busy_mount"] = can_retry_busy_mount
    result["status_url"] = f"/api/rbd/volumes/{result['id']}"
    return result


def _busy_mount_retryable(volume: dict[str, Any], latest_action: dict[str, Any] | None) -> bool:
    """Only retry a known map refusal, never an ambiguous mount or unmount."""
    return bool(
        volume.get("observed_state") == "BUSY"
        and volume.get("image_id")
        and volume.get("device") is None
        and volume.get("device_major") is None
        and volume.get("device_minor") is None
        and volume.get("mountpoint") is None
        and latest_action
        and latest_action.get("action_type") == "MOUNT"
        and latest_action.get("state") == "FAILED_FINAL"
        and latest_action.get("error_code") == "VOLUME_BUSY"
        and latest_action.get("current_step") == "rbd.image.map"
        and latest_action.get("volume_generation") == volume.get("transition_generation")
    )


def _latest_volume_action(conn, volume_id: UUID | str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT action_type,state,error_code,current_step,volume_generation
          FROM rbd_actions
         WHERE volume_id=%s
         ORDER BY created_at DESC,id DESC
         LIMIT 1
        """,
        (volume_id,),
    ).fetchone()
    return dict(row) if row else None


def _action_result(row: dict[str, Any]) -> dict[str, Any]:
    result = _json_value(dict(row))
    action_id = result.pop("id")
    result["action_id"] = action_id
    result["status_url"] = f"/api/rbd/actions/{action_id}"
    return result


def _load_action(action_id: UUID | str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT action.id, action.volume_id, action.action_type,
                   action.intended_state AS desired_state,
                   action.observed_state, action.state, action.current_step,
                   action.created_at, action.started_at, action.finished_at,
                   action.error_code, action.error, action.redacted_result,
                   action.capacity_decision_id, action.volume_generation,
                   action.attempt_count
              FROM rbd_actions action
             WHERE action.id=%s
            """,
            (action_id,),
        ).fetchone()
    return dict(row) if row else None


def _accepted(action_id: UUID | str) -> JSONResponse:
    row = _load_action(action_id)
    if row is None:
        raise RbdControlError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "The request is claimed but its action has not been durably queued yet",
            retryable=True,
        )
    return JSONResponse(status_code=202, content=_action_result(row))


def _claim_action(
    request: Request,
    *,
    idempotency_key: str,
    scope: str,
    method: str,
    resource: str,
    payload: Any,
    proposed_action_id: UUID,
):
    fingerprint = canonical_request_fingerprint(method, resource, payload)
    claim = idempotency_service.claim(
        IdempotencyClaimRequest(
            scope=scope,
            idempotency_key=idempotency_key,
            http_method=method,
            resource=resource,
            request_fingerprint=fingerprint,
            owner_id=request.state.request_id,
            request_id=UUID(request.state.request_id),
            action_id=proposed_action_id,
        )
    )
    if claim.disposition is IdempotencyDisposition.REPLAY:
        return claim, JSONResponse(
            status_code=claim.record.response_status or 202,
            content=claim.record.response_body or {},
            headers={"Idempotency-Replayed": "true"},
        )
    if claim.disposition is IdempotencyDisposition.IN_PROGRESS:
        if claim.record.action_id is not None and _load_action(claim.record.action_id):
            response = _accepted(claim.record.action_id)
            response.headers["Idempotency-Replayed"] = "true"
            return claim, response
        raise RbdControlError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "The same RBD mutation is already being queued",
            retryable=True,
            observed_state={
                "request_id": str(claim.record.request_id),
                "state": claim.record.state.value,
            },
        )
    claim.record = idempotency_service.mark_in_progress(
        scope,
        idempotency_key,
        owner_id=request.state.request_id,
        fencing_generation=claim.record.fencing_generation,
    )
    return claim, None


def _finish_claim(claim, body: dict[str, Any], status: int = 202) -> None:
    idempotency_service.finish(
        claim.record.scope,
        claim.record.idempotency_key,
        owner_id=claim.record.owner_id,
        fencing_generation=claim.record.fencing_generation,
        state=IdempotencyState.SUCCEEDED,
        response_status=status,
        response_body=body,
    )


def _fail_claim(
    claim,
    *,
    code: str,
    message: str,
    status: int,
    retryable: bool,
    observed_state: dict[str, Any] | None = None,
) -> None:
    idempotency_service.finish(
        claim.record.scope,
        claim.record.idempotency_key,
        owner_id=claim.record.owner_id,
        fencing_generation=claim.record.fencing_generation,
        state=(
            IdempotencyState.FAILED_RETRYABLE
            if retryable
            else IdempotencyState.FAILED_FINAL
        ),
        response_status=status,
        response_body={
            "detail": {
                "request_id": str(claim.record.request_id),
                "code": code,
                "message": message[:2000],
                "retryable": retryable,
                "observed_state": observed_state,
            }
        },
        error_code=code,
    )


def _parse_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return datetime.fromisoformat(payload["created_at"]), UUID(payload["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RbdControlError(422, "INVALID_CURSOR", "The volume cursor is invalid") from exc


def _cursor(row: dict[str, Any]) -> str:
    payload = json.dumps(
        {"created_at": row["created_at"].isoformat(), "id": str(row["id"])},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


@router.get("/pools")
def list_pools():
    configured = get_settings().rbd_allowed_pool_set
    if not configured:
        return {"enabled": False, "pools": [], "reason": "RBD_ALLOWED_POOLS is empty"}
    try:
        result = ExecutorClient.from_settings().rbd_pool_list()
    except (ExecutorClientError, ValueError) as exc:
        code = exc.code if isinstance(exc, ExecutorClientError) else "EXECUTOR_NOT_CONFIGURED"
        raise RbdControlError(
            503,
            code,
            str(exc),
            retryable=isinstance(exc, ExecutorClientError) and exc.retryable,
        ) from exc
    candidates = result.get("pools", result.get("items", []))
    pools: list[dict[str, Any]] = []
    for item in candidates if isinstance(candidates, list) else []:
        name = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
        if name in configured:
            pools.append({"name": name} if isinstance(item, str) else _json_value(item))
    return {"enabled": True, "pools": pools, "fsid": result.get("fsid")}


def _executor_status(call: str) -> dict[str, Any]:
    try:
        client = ExecutorClient.from_settings()
        result = getattr(client, call)()
    except (ExecutorClientError, ValueError) as exc:
        code = exc.code if isinstance(exc, ExecutorClientError) else "EXECUTOR_NOT_CONFIGURED"
        raise RbdControlError(
            503,
            code,
            str(exc),
            retryable=isinstance(exc, ExecutorClientError) and exc.retryable,
        ) from exc
    nested_data = result.get("data")
    if isinstance(nested_data, dict):
        public_data = dict(nested_data)
    else:
        public_data = {
            key: value
            for key, value in result.items()
            if key not in {"fsid", "collected_at", "status"}
        }
    return {
        "status": result.get("status", "ok"),
        "executor": "node-ssh",
        "fsid": result.get("fsid"),
        "collected_at": result.get("collected_at"),
        "data": public_data,
    }


@router.get("/ssh/health")
def ssh_health():
    return _executor_status("health")


@router.get("/ssh/capabilities")
def ssh_capabilities():
    return _executor_status("capabilities")


@router.get("/volumes")
def list_volumes(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
):
    settings = get_settings()
    pools = sorted(settings.rbd_allowed_pool_set)
    namespaces = sorted(
        "" if item == "default" else item for item in settings.rbd_allowed_namespace_set
    )
    if not pools or not namespaces:
        return {"items": [], "next_cursor": None}
    marker = _parse_cursor(cursor)
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT *
              FROM rbd_volumes
             WHERE pool=ANY(%s)
               AND coalesce(namespace,'')=ANY(%s)
               AND image_name LIKE %s
               AND (%s::timestamptz IS NULL OR (created_at,id) < (%s,%s))
             ORDER BY created_at DESC,id DESC
             LIMIT %s
            """,
            (
                pools,
                namespaces,
                settings.rbd_image_prefix.replace("%", "\\%").replace("_", "\\_") + "%",
                marker[0] if marker else None,
                marker[0] if marker else None,
                marker[1] if marker else None,
                limit + 1,
            ),
        ).fetchall()
        busy_ids = [row["id"] for row in rows if row["observed_state"] == "BUSY"]
        latest_actions = {}
        if busy_ids:
            action_rows = conn.execute(
                """
                SELECT DISTINCT ON (volume_id)
                       volume_id,action_type,state,error_code,current_step,volume_generation
                  FROM rbd_actions
                 WHERE volume_id=ANY(%s)
                 ORDER BY volume_id,created_at DESC,id DESC
                """,
                (busy_ids,),
            ).fetchall()
            latest_actions = {row["volume_id"]: dict(row) for row in action_rows}
    items = [dict(row) for row in rows[:limit]]
    return {
        "items": [
            _volume_result(
                row,
                can_retry_busy_mount=_busy_mount_retryable(row, latest_actions.get(row["id"])),
            )
            for row in items
        ],
        "next_cursor": _cursor(items[-1]) if len(rows) > limit and items else None,
    }


@router.post("/volumes", status_code=202)
def create_volume(
    payload: VolumeCreateRequest,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=255)
    ],
):
    _assert_scope(payload.pool, payload.namespace, payload.image_name)
    proposed_action_id = uuid.uuid4()
    claim, replay = _claim_action(
        request,
        idempotency_key=idempotency_key,
        scope="rbd:volume-create",
        method="POST",
        resource="rbd:volumes",
        payload=payload,
        proposed_action_id=proposed_action_id,
    )
    if replay:
        return replay
    action_id = claim.record.action_id or proposed_action_id
    volume_id = uuid5(action_id, "volume")
    image_name = payload.image_name or f"{get_settings().rbd_image_prefix}{volume_id.hex}"
    decision = None
    try:
        decision = require_admission(
            "RBD_CREATE",
            payload.logical_size_bytes,
            request_id=request.state.request_id,
            affected_pools=[payload.pool],
        )
        observed = "CAPACITY_RESERVED" if decision.reservation_id else "REQUESTED"
        desired = "READY" if payload.auto_mount else "CREATED"
        request_payload = payload.model_dump(mode="json")
        request_payload["image_name"] = image_name
        with connection() as conn:
            with conn.transaction():
                reserved_raw = 0
                if decision.reservation_id:
                    reservation = conn.execute(
                        "SELECT estimated_raw_bytes FROM capacity_reservations WHERE id=%s FOR UPDATE",
                        (decision.reservation_id,),
                    ).fetchone()
                    if not reservation:
                        raise RuntimeError("capacity reservation disappeared before queueing")
                    reserved_raw = int(reservation["estimated_raw_bytes"])
                conn.execute(
                    """
                    INSERT INTO rbd_volumes (
                      id,pool,namespace,image_name,display_name,logical_size_bytes,
                      reserved_raw_bytes,capacity_mode,desired_state,observed_state,
                      capacity_reservation_id,transition_generation,
                      creation_action_id,filesystem,auto_mount
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s)
                    """,
                    (
                        volume_id,
                        payload.pool,
                        payload.namespace,
                        image_name,
                        payload.display_name,
                        payload.logical_size_bytes,
                        reserved_raw,
                        payload.capacity_mode,
                        desired,
                        observed,
                        decision.reservation_id,
                        _step_action_id(action_id, "rbd.image.create"),
                        payload.filesystem,
                        payload.auto_mount,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO rbd_actions (
                      id,idempotency_request_id,volume_id,action_type,intended_state,
                      observed_state,state,timeout_seconds,request_payload,current_step,
                      volume_generation,capacity_decision_id
                    ) VALUES (%s,%s,%s,'CREATE',%s,%s,'PENDING',900,%s::jsonb,NULL,1,%s)
                    """,
                    (
                        action_id,
                        claim.record.id,
                        volume_id,
                        desired,
                        observed,
                        json.dumps(request_payload),
                        decision.id,
                    ),
                )
                conn.execute(
                    "UPDATE capacity_decisions SET action_id=%s WHERE id=%s",
                    (action_id, decision.id),
                )
                if decision.reservation_id:
                    converted = conn.execute(
                        """
                        UPDATE capacity_reservations
                           SET owner_type='VOLUME',owner_id=%s,
                               reservation_class='PERSISTENT_VOLUME',
                               remaining_commitment_bytes=estimated_raw_bytes,
                               state='PERSISTENT_COMMITMENT',lease_owner=NULL,
                               heartbeat_at=NULL,lease_expires_at=NULL,updated_at=now()
                         WHERE id=%s AND lease_generation=%s AND state='PENDING'
                        RETURNING id
                        """,
                        (
                            str(volume_id),
                            decision.reservation_id,
                            int(decision.reservation_generation or 1),
                        ),
                    ).fetchone()
                    if not converted:
                        raise RuntimeError("capacity reservation fencing was lost while queueing")
    except CapacityRejected as exc:
        _fail_claim(
            claim,
            code=exc.code,
            message=str(exc),
            status=exc.status_code,
            retryable=exc.decision.retryable,
            observed_state=exc.decision.to_dict(),
        )
        raise
    except Exception as exc:
        if decision is not None and decision.reservation_id:
            try:
                finish_reservation(decision, "not_started")
            except Exception:
                pass
        _fail_claim(
            claim,
            code="RBD_QUEUE_FAILED",
            message=str(exc),
            status=503,
            retryable=True,
        )
        raise RbdControlError(
            503, "RBD_QUEUE_FAILED", "Could not durably queue the RBD create action", retryable=True
        ) from exc
    response = _accepted(action_id)
    try:
        _finish_claim(claim, json.loads(response.body))
    except Exception:
        # The durable action is authoritative. A same-key retry discovers it via action_id.
        pass
    return response


def _load_volume(volume_id: UUID | str, *, lock: bool = False, conn=None):
    manager = connection() if conn is None else None
    if manager is not None:
        with manager as owned:
            return _load_volume(volume_id, lock=lock, conn=owned)
    suffix = " FOR UPDATE" if lock else ""
    row = conn.execute(f"SELECT * FROM rbd_volumes WHERE id=%s{suffix}", (volume_id,)).fetchone()
    if row is None:
        raise RbdControlError(404, "VOLUME_NOT_FOUND", "RBD volume was not found")
    result = dict(row)
    _assert_scope(result["pool"], result.get("namespace"), result["image_name"])
    return result


@router.get("/volumes/{volume_id}")
def get_volume(volume_id: UUID):
    with connection() as conn:
        volume = _load_volume(volume_id, conn=conn)
        latest = _latest_volume_action(conn, volume_id) if volume["observed_state"] == "BUSY" else None
    return _volume_result(volume, can_retry_busy_mount=_busy_mount_retryable(volume, latest))


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "MOUNT": {"CREATED", "MAPPED", "FORMATTED", "UNMOUNTED", "UNMAPPED"},
    "UNMOUNT": {"READY", "MOUNTED"},
    "DELETE": {
        "CREATED",
        "MAPPED",
        "FORMATTED",
        "READY",
        "MOUNTED",
        "UNMOUNTED",
        "UNMAPPED",
        "MAP_FAILED",
        "FORMAT_FAILED",
        "MOUNT_FAILED",
        "BUSY",
        "DELETE_BLOCKED_DEPENDENCY",
        "REQUESTED",
        "CAPACITY_RESERVED",
    },
}
_INTENDED_STATE = {"MOUNT": "READY", "UNMOUNT": "UNMAPPED", "DELETE": "DELETED"}


def _enqueue_volume_action(
    volume_id: UUID,
    action_type: Literal["MOUNT", "UNMOUNT", "DELETE"],
    request: Request,
    idempotency_key: str,
):
    existing = _load_volume(volume_id)
    method = "DELETE" if action_type == "DELETE" else "POST"
    resource = f"rbd:volumes:{volume_id}:{action_type.lower()}"
    proposed_action_id = uuid.uuid4()
    claim, replay = _claim_action(
        request,
        idempotency_key=idempotency_key,
        scope=resource,
        method=method,
        resource=resource,
        payload={"volume_id": str(volume_id), "action_type": action_type},
        proposed_action_id=proposed_action_id,
    )
    if replay:
        return replay
    action_id = claim.record.action_id or proposed_action_id
    try:
        with connection() as conn:
            with conn.transaction():
                volume = _load_volume(volume_id, lock=True, conn=conn)
                active = conn.execute(
                    """
                    SELECT id,state FROM rbd_actions
                     WHERE volume_id=%s AND state IN ('PENDING','RUNNING','RECONCILING')
                     LIMIT 1
                    """,
                    (volume_id,),
                ).fetchone()
                if active:
                    raise RbdControlError(
                        423 if active["state"] == "RECONCILING" else 409,
                        "RECONCILING" if active["state"] == "RECONCILING" else "STATE_CONFLICT",
                        "The volume already has an active lifecycle action",
                        retryable=True,
                        observed_state={"action_id": str(active["id"]), "state": active["state"]},
                    )
                observed = volume["observed_state"]
                precreate_cleanup = (
                    action_type == "DELETE"
                    and observed in {"REQUESTED", "CAPACITY_RESERVED"}
                    and not volume.get("image_id")
                )
                if observed in {"RECONCILING", "UNKNOWN", "REQUESTED", "CAPACITY_RESERVED"} and not precreate_cleanup:
                    raise RbdControlError(
                        423,
                        "RECONCILING",
                        "The volume must be reconciled before this transition",
                        retryable=True,
                        observed_state={"observed_state": observed},
                    )
                retry_busy_mount = (
                    action_type == "MOUNT"
                    and observed == "BUSY"
                    and _busy_mount_retryable(volume, _latest_volume_action(conn, volume_id))
                )
                if observed not in _ALLOWED_TRANSITIONS[action_type] and not retry_busy_mount:
                    raise RbdControlError(
                        409,
                        "STATE_CONFLICT",
                        f"{action_type.lower()} is not valid while the volume is {observed}",
                        observed_state={"observed_state": observed},
                    )
                generation = int(volume["transition_generation"]) + 1
                intended = _INTENDED_STATE[action_type]
                conn.execute(
                    """
                    UPDATE rbd_volumes
                       SET desired_state=%s,transition_generation=%s,updated_at=now(),last_error=NULL
                     WHERE id=%s AND transition_generation=%s
                    """,
                    (intended, generation, volume_id, volume["transition_generation"]),
                )
                conn.execute(
                    """
                    INSERT INTO rbd_actions (
                      id,idempotency_request_id,volume_id,action_type,intended_state,
                      observed_state,state,timeout_seconds,request_payload,volume_generation
                    ) VALUES (%s,%s,%s,%s,%s,%s,'PENDING',900,%s::jsonb,%s)
                    """,
                    (
                        action_id,
                        claim.record.id,
                        volume_id,
                        action_type,
                        intended,
                        observed,
                        json.dumps({"volume_id": str(volume_id)}),
                        generation,
                    ),
                )
    except RbdControlError as exc:
        _fail_claim(
            claim,
            code=exc.code,
            message=exc.message,
            status=exc.status_code,
            retryable=exc.retryable,
            observed_state=exc.observed_state,
        )
        raise
    except Exception as exc:
        _fail_claim(
            claim,
            code="RBD_QUEUE_FAILED",
            message=str(exc),
            status=503,
            retryable=True,
        )
        raise RbdControlError(
            503, "RBD_QUEUE_FAILED", "Could not durably queue the RBD action", retryable=True
        ) from exc
    response = _accepted(action_id)
    try:
        _finish_claim(claim, json.loads(response.body))
    except Exception:
        pass
    return response


@router.post("/volumes/{volume_id}/mount", status_code=202)
def mount_volume(
    volume_id: UUID,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=255)
    ],
):
    return _enqueue_volume_action(volume_id, "MOUNT", request, idempotency_key)


@router.post("/volumes/{volume_id}/unmount", status_code=202)
def unmount_volume(
    volume_id: UUID,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=255)
    ],
):
    return _enqueue_volume_action(volume_id, "UNMOUNT", request, idempotency_key)


@router.delete("/volumes/{volume_id}", status_code=202)
def delete_volume(
    volume_id: UUID,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=255)
    ],
):
    return _enqueue_volume_action(volume_id, "DELETE", request, idempotency_key)


@router.get("/actions/{action_id}")
def get_action(action_id: UUID):
    row = _load_action(action_id)
    if row is None:
        raise RbdControlError(404, "ACTION_NOT_FOUND", "RBD lifecycle action was not found")
    volume = _load_volume(row["volume_id"])
    result = _action_result(row)
    result["volume"] = _volume_result(volume)
    return result


def _mounted_volume(volume_id: UUID | str) -> dict[str, Any]:
    volume = _load_volume(volume_id)
    if volume.get("observed_state") not in {"MOUNTED", "READY"}:
        raise RbdControlError(
            409,
            "VOLUME_NOT_MOUNTED",
            "The volume must be mounted before using files or terminal",
            observed_state={"observed_state": volume.get("observed_state")},
        )
    required = ("image_id", "device_major", "device_minor", "fs_uuid", "mountpoint")
    if any(volume.get(field) is None for field in required):
        raise RbdControlError(
            423,
            "RECONCILING",
            "Mounted volume identity is incomplete and must be reconciled",
            retryable=True,
        )
    if volume.get("capacity_mode") != "reserved-logical":
        raise RbdControlError(
            409,
            "CAPACITY_MODE_UNSUPPORTED",
            "File and terminal access requires reserved-logical capacity mode",
        )
    return volume


def _volume_executor_params(
    volume: dict[str, Any],
    *,
    path: str | None = None,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "volume_id": str(volume["id"]),
        "pool": volume["pool"],
        "namespace": volume.get("namespace") or "",
        "image_name": volume["image_name"],
        "image_id": volume["image_id"],
        "device_major": int(volume["device_major"]),
        "device_minor": int(volume["device_minor"]),
        "fs_uuid": str(volume["fs_uuid"]),
    }
    if path is not None:
        params["path"] = path
    if paths is not None:
        params["paths"] = paths
    return params


def _executor_error(exc: Exception) -> RbdControlError:
    if isinstance(exc, ExecutorClientError):
        status_by_code = {
            "FILE_NOT_FOUND": 404,
            "FILE_EXISTS": 409,
            "DIRECTORY_NOT_EMPTY": 409,
            "VOLUME_NOT_MOUNTED": 409,
            "VOLUME_BUSY": 409,
            "IS_A_DIRECTORY": 409,
            "NOT_A_DIRECTORY": 409,
            "NOT_A_FILE": 409,
            "INVALID_PATH": 422,
            "PATH_ESCAPE": 422,
            "SYMLINK_NOT_ALLOWED": 422,
            "SCOPE_NOT_ALLOWED": 422,
            "FILE_TOO_LARGE": 413,
            "INVALID_LENGTH": 400,
        }
        status = status_by_code.get(exc.code, 503 if exc.retryable else 502)
        return RbdControlError(
            status,
            exc.code,
            exc.message,
            retryable=exc.retryable,
            observed_state=exc.details,
        )
    return RbdControlError(503, "EXECUTOR_NOT_CONFIGURED", str(exc), retryable=True)


def _call_file_executor(
    action: str,
    volume: dict[str, Any],
    *,
    path: str | None = None,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    try:
        return ExecutorClient.from_settings().rbd_file_action(
            action,
            _volume_executor_params(volume, path=path, paths=paths),
            timeout_seconds=(
                get_settings().rbd_validation_timeout_seconds
                if action == "rbd.files.manifest"
                else None
            ),
        )
    except (ExecutorClientError, ValueError) as exc:
        raise _executor_error(exc) from exc


def _require_reserved_volume_gate(
    operation: Literal["RBD_FILE_WRITE", "RBD_DELETE_CLEANUP"],
    volume: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    decision = decide(
        operation,
        0,
        request_id=request_id,
        affected_pools=[volume["pool"]],
    )
    if decision.decision == "BLOCK":
        code = "TELEMETRY_STALE" if decision.state == "BLOCKED_TELEMETRY" else "CAPACITY_LIMIT"
        raise CapacityRejected(decision, code, 503 if code == "TELEMETRY_STALE" else 409)
    return decision.to_dict()


def _audit_file_operation(
    kind: Literal["RBD_FILE_READ", "RBD_FILE_WRITE", "RBD_FILE_DELETE"],
    volume: dict[str, Any],
    path: str,
    *,
    request_id: str,
    started: float,
    success: bool,
    bytes_count: int = 0,
    content_type: str | None = None,
    capacity_decision_id: str | None = None,
    osdmap_epoch: int | None = None,
    error: str | None = None,
    error_code: str | None = None,
) -> None:
    try:
        record_operation(
            kind=kind,
            success=success,
            bytes_count=max(0, int(bytes_count)),
            latency_ms=(time.monotonic() - started) * 1000,
            volume_id=volume["id"],
            request_id=request_id,
            target_type="RBD_FILE",
            target_id=f"rbd-file:{volume['id']}:{path}",
            source="web-rbd-files",
            content_type=content_type,
            capacity_decision_id=capacity_decision_id,
            osdmap_epoch=osdmap_epoch,
            error=error[:1000] if error else None,
            error_code=error_code,
        )
    except Exception:
        # The file result is authoritative; an audit sink failure must not invent
        # a second SFTP mutation or turn a completed stream into a retry.
        pass


def _file_context_header(params: dict[str, Any]) -> str:
    raw = json.dumps(params, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _executor_file_url() -> str:
    return f"{get_settings().rbd_executor_url.rstrip('/')}/internal/v1/files/content"


def _executor_auth_headers(params: dict[str, Any]) -> dict[str, str]:
    settings = get_settings()
    token = settings.rbd_executor_token.get_secret_value() if settings.rbd_executor_token else ""
    if len(token) < 32:
        raise RbdControlError(503, "EXECUTOR_NOT_CONFIGURED", "RBD executor token is not configured")
    return {
        "X-Executor-Token": token,
        "X-RBD-Context": _file_context_header(params),
    }


def _executor_http_error(response: httpx.Response) -> RbdControlError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    nested = body.get("error") if isinstance(body.get("error"), dict) else body
    code = nested.get("code", "EXECUTOR_PROTOCOL_ERROR") if isinstance(nested, dict) else "EXECUTOR_PROTOCOL_ERROR"
    message = (nested.get("message") or nested.get("error")) if isinstance(nested, dict) else None
    error = ExecutorClientError(
        str(code),
        str(message or "RBD executor rejected the file request"),
        retryable=response.status_code >= 500,
    )
    mapped = _executor_error(error)
    if response.status_code in {400, 401, 404, 409, 411, 413, 422, 423, 503}:
        mapped.status_code = response.status_code
    return mapped


@router.get("/volumes/{volume_id}/files")
def list_volume_files(volume_id: UUID, path: str = Query(default="/", min_length=1, max_length=4096)):
    volume = _mounted_volume(volume_id)
    result = _call_file_executor("rbd.files.list", volume, path=path)
    result["volume_id"] = str(volume_id)
    return result


@router.get("/volumes/{volume_id}/files/metadata")
def volume_file_metadata(
    volume_id: UUID,
    path: str = Query(min_length=1, max_length=4096),
):
    return _call_file_executor("rbd.files.stat", _mounted_volume(volume_id), path=path)


@router.post("/volumes/{volume_id}/directories", status_code=201)
def create_volume_directory(volume_id: UUID, payload: FilePathRequest, request: Request):
    started = time.monotonic()
    volume = _mounted_volume(volume_id)
    capacity = _require_reserved_volume_gate("RBD_FILE_WRITE", volume, request.state.request_id)
    try:
        result = _call_file_executor("rbd.files.mkdir", volume, path=payload.path)
        result["capacity_decision"] = capacity
        _audit_file_operation(
            "RBD_FILE_WRITE",
            volume,
            payload.path,
            request_id=request.state.request_id,
            started=started,
            success=True,
            capacity_decision_id=capacity.get("id"),
            osdmap_epoch=capacity.get("osdmap_epoch"),
        )
        return result
    except Exception as exc:
        _audit_file_operation(
            "RBD_FILE_WRITE",
            volume,
            payload.path,
            request_id=request.state.request_id,
            started=started,
            success=False,
            error=str(exc),
            error_code=getattr(exc, "code", "RBD_MKDIR_FAILED"),
            capacity_decision_id=capacity.get("id"),
            osdmap_epoch=capacity.get("osdmap_epoch"),
        )
        raise


@router.delete("/volumes/{volume_id}/files")
def delete_volume_file(
    volume_id: UUID,
    request: Request,
    path: str = Query(min_length=1, max_length=4096),
):
    started = time.monotonic()
    volume = _mounted_volume(volume_id)
    capacity = _require_reserved_volume_gate("RBD_DELETE_CLEANUP", volume, request.state.request_id)
    try:
        result = _call_file_executor("rbd.files.delete", volume, path=path)
        _audit_file_operation(
            "RBD_FILE_DELETE",
            volume,
            path,
            request_id=request.state.request_id,
            started=started,
            success=True,
            bytes_count=int(result.get("size") or 0),
            capacity_decision_id=capacity.get("id"),
            osdmap_epoch=capacity.get("osdmap_epoch"),
        )
        return result
    except Exception as exc:
        _audit_file_operation(
            "RBD_FILE_DELETE",
            volume,
            path,
            request_id=request.state.request_id,
            started=started,
            success=False,
            error=str(exc),
            error_code=getattr(exc, "code", "RBD_FILE_DELETE_FAILED"),
            capacity_decision_id=capacity.get("id"),
            osdmap_epoch=capacity.get("osdmap_epoch"),
        )
        raise


@router.put("/volumes/{volume_id}/files/content")
async def upload_volume_file(
    volume_id: UUID,
    request: Request,
    content_length: Annotated[int, Header(alias="Content-Length", ge=0)],
    path: str = Query(min_length=1, max_length=4096),
):
    started = time.monotonic()
    volume = await asyncio.to_thread(_mounted_volume, volume_id)
    settings = get_settings()
    if content_length > settings.rbd_file_upload_max_bytes or content_length > int(volume["logical_size_bytes"]):
        raise RbdControlError(413, "FILE_TOO_LARGE", "Upload exceeds the configured or logical volume limit")
    capacity = await asyncio.to_thread(
        _require_reserved_volume_gate,
        "RBD_FILE_WRITE",
        volume,
        request.state.request_id,
    )
    params = _volume_executor_params(volume, path=path)
    headers = _executor_auth_headers(params)
    headers["Content-Length"] = str(content_length)
    try:
        timeout = httpx.Timeout(get_settings().rbd_executor_timeout_seconds, read=None)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.put(
                _executor_file_url(),
                headers=headers,
                content=request.stream(),
            )
        if not response.is_success:
            raise _executor_http_error(response)
        body = response.json()
        if body.get("version") != 1 or body.get("ok") is not True or not isinstance(body.get("result"), dict):
            raise RbdControlError(502, "EXECUTOR_PROTOCOL_ERROR", "Executor upload response is invalid")
        result = body["result"]
        result["capacity_decision"] = capacity
        await asyncio.to_thread(
            _audit_file_operation,
            "RBD_FILE_WRITE",
            volume,
            path,
            request_id=request.state.request_id,
            started=started,
            success=True,
            bytes_count=content_length,
            content_type=result.get("mime_type"),
            capacity_decision_id=capacity.get("id"),
            osdmap_epoch=capacity.get("osdmap_epoch"),
        )
        return result
    except (httpx.TimeoutException, httpx.HTTPError) as exc:
        mapped = RbdControlError(503, "EXECUTOR_UNAVAILABLE", "Could not stream the upload to the SSH executor", retryable=True)
        await asyncio.to_thread(
            _audit_file_operation,
            "RBD_FILE_WRITE",
            volume,
            path,
            request_id=request.state.request_id,
            started=started,
            success=False,
            error=str(exc),
            error_code=mapped.code,
            capacity_decision_id=capacity.get("id"),
            osdmap_epoch=capacity.get("osdmap_epoch"),
        )
        raise mapped from exc
    except Exception as exc:
        await asyncio.to_thread(
            _audit_file_operation,
            "RBD_FILE_WRITE",
            volume,
            path,
            request_id=request.state.request_id,
            started=started,
            success=False,
            error=str(exc),
            error_code=getattr(exc, "code", "RBD_FILE_WRITE_FAILED"),
            capacity_decision_id=capacity.get("id"),
            osdmap_epoch=capacity.get("osdmap_epoch"),
        )
        raise


@router.get("/volumes/{volume_id}/files/content")
async def download_volume_file(
    volume_id: UUID,
    request: Request,
    path: str = Query(min_length=1, max_length=4096),
    preview: bool = False,
):
    started = time.monotonic()
    volume = await asyncio.to_thread(_mounted_volume, volume_id)
    metadata = await asyncio.to_thread(_call_file_executor, "rbd.files.stat", volume, path=path)
    settings = get_settings()
    mime_type = str(metadata.get("mime_type") or "application/octet-stream").split(";", 1)[0].lower()
    if preview:
        if int(metadata.get("size") or 0) > settings.rbd_file_preview_max_bytes:
            raise RbdControlError(413, "PREVIEW_TOO_LARGE", "File exceeds the configured preview limit")
        if mime_type not in settings.rbd_allowed_preview_mime_set:
            raise RbdControlError(415, "PREVIEW_UNSUPPORTED", "This file type is download-only")

    params = _volume_executor_params(volume, path=path)
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.rbd_executor_timeout_seconds, read=None),
        follow_redirects=False,
    )
    try:
        upstream = await client.send(
            client.build_request("GET", _executor_file_url(), headers=_executor_auth_headers(params)),
            stream=True,
        )
        if not upstream.is_success:
            await upstream.aread()
            error = _executor_http_error(upstream)
            await upstream.aclose()
            await client.aclose()
            raise error
    except Exception:
        await client.aclose()
        raise

    filename = str(metadata.get("name") or "download.bin").replace('"', "")
    disposition = "inline" if preview else "attachment"
    headers = {
        "Content-Length": str(int(metadata.get("size") or 0)),
        "Content-Disposition": f'{disposition}; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        "Cache-Control": "private, no-store",
    }

    async def body():
        sent = 0
        stream_error: Exception | None = None
        try:
            async for chunk in upstream.aiter_bytes():
                sent += len(chunk)
                yield chunk
        except Exception as exc:
            stream_error = exc
            raise
        finally:
            await upstream.aclose()
            await client.aclose()
            await asyncio.to_thread(
                _audit_file_operation,
                "RBD_FILE_READ",
                volume,
                path,
                request_id=request.state.request_id,
                started=started,
                success=stream_error is None and sent == int(metadata.get("size") or 0),
                bytes_count=sent,
                content_type=mime_type,
                error=str(stream_error) if stream_error else None,
                error_code="RBD_FILE_READ_FAILED" if stream_error else None,
            )

    return StreamingResponse(body(), media_type=mime_type, headers=headers)


@router.post("/volumes/{volume_id}/terminal-ticket")
def create_terminal_ticket(volume_id: UUID, request: Request):
    volume = _mounted_volume(volume_id)
    capacity = _require_reserved_volume_gate("RBD_FILE_WRITE", volume, request.state.request_id)
    try:
        result = ExecutorClient.from_settings().terminal_ticket(_volume_executor_params(volume))
    except (ExecutorClientError, ValueError) as exc:
        raise _executor_error(exc) from exc
    result["websocket_path"] = "/ws/terminal"
    result["capacity_decision"] = capacity
    result["lab_warning"] = "This is a real shell on the configured Linux Ceph client host. Closing it does not unmount the volume."
    return result


def _validation_result(row: dict[str, Any]) -> dict[str, Any]:
    return _json_value(dict(row))


@router.get("/volumes/{volume_id}/validation-runs")
def list_validation_runs(volume_id: UUID):
    _load_volume(volume_id)
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rbd_validation_runs WHERE volume_id=%s ORDER BY created_at DESC LIMIT 100",
            (volume_id,),
        ).fetchall()
    return {"items": [_validation_result(dict(row)) for row in rows]}


@router.post("/volumes/{volume_id}/validation-runs", status_code=201)
def create_validation_run(
    volume_id: UUID,
    payload: ValidationBaselineRequest,
    request: Request,
):
    started = time.monotonic()
    volume = _mounted_volume(volume_id)
    manifest = _call_file_executor("rbd.files.manifest", volume, paths=payload.paths)
    files = manifest.get("files")
    if (
        manifest.get("algorithm") != "sha256"
        or not isinstance(files, list)
        or len(files) != len(payload.paths)
        or len({item.get("path") for item in files if isinstance(item, dict)}) != len(files)
        or any(
            not isinstance(item, dict)
            or item.get("status") != "PRESENT"
            or not isinstance(item.get("sha256"), str)
            or len(item["sha256"]) != 64
            for item in files
        )
    ):
        raise RbdControlError(409, "BASELINE_FILE_MISSING", "Every baseline path must be a present regular file")
    with connection() as conn:
        snapshot = conn.execute(
            "SELECT fsid,osdmap_epoch FROM capacity_snapshots WHERE fresh=true ORDER BY captured_at DESC,id DESC LIMIT 1"
        ).fetchone()
        run_id = uuid.uuid4()
        row = conn.execute(
            """
            INSERT INTO rbd_validation_runs (
              id,volume_id,name,baseline_label,image_id,fs_uuid,
              baseline_fsid,baseline_osdmap_epoch,manifest
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            RETURNING *
            """,
            (
                run_id,
                volume_id,
                payload.name,
                payload.baseline_label,
                volume["image_id"],
                volume["fs_uuid"],
                snapshot["fsid"] if snapshot else None,
                snapshot["osdmap_epoch"] if snapshot else None,
                json.dumps(manifest),
            ),
        ).fetchone()
        conn.commit()
    for item in manifest.get("files", []):
        _audit_file_operation(
            "RBD_FILE_READ",
            volume,
            item["path"],
            request_id=request.state.request_id,
            started=started,
            success=True,
            bytes_count=int(item.get("size") or 0),
            content_type=item.get("mime_type"),
        )
    return _validation_result(dict(row))


@router.post("/volumes/{volume_id}/validation-runs/{run_id}/verify")
def verify_validation_run(volume_id: UUID, run_id: UUID, request: Request):
    started = time.monotonic()
    volume = _mounted_volume(volume_id)
    with connection() as conn:
        stored = conn.execute(
            "SELECT * FROM rbd_validation_runs WHERE id=%s AND volume_id=%s",
            (run_id, volume_id),
        ).fetchone()
    if stored is None:
        raise RbdControlError(404, "VALIDATION_RUN_NOT_FOUND", "RBD validation run was not found")
    stored = dict(stored)
    if stored["image_id"] != volume["image_id"] or str(stored["fs_uuid"]) != str(volume["fs_uuid"]):
        raise RbdControlError(409, "VOLUME_IDENTITY_MISMATCH", "The mounted image or filesystem no longer matches the baseline")
    expected = {item["path"]: item for item in stored["manifest"].get("files", [])}
    try:
        observed_manifest = _call_file_executor(
            "rbd.files.manifest",
            volume,
            paths=list(expected),
        )
        observed_files = observed_manifest.get("files")
        if observed_manifest.get("algorithm") != "sha256" or not isinstance(observed_files, list) or len(observed_files) != len(expected):
            raise RbdControlError(502, "EXECUTOR_PROTOCOL_ERROR", "Executor verification manifest is incomplete")
        observed = {item["path"]: item for item in observed_files}
        if len(observed) != len(observed_files):
            raise RbdControlError(502, "EXECUTOR_PROTOCOL_ERROR", "Executor verification manifest contains duplicate paths")
        comparisons = []
        for path, baseline in expected.items():
            current = observed.get(path)
            matches = bool(
                current
                and current.get("sha256") == baseline.get("sha256")
                and int(current.get("size") or 0) == int(baseline.get("size") or 0)
            )
            comparisons.append(
                {
                    "path": path,
                    "status": "MATCH" if matches else "CHANGED_OR_MISSING",
                    "expected_sha256": baseline.get("sha256"),
                    "observed_sha256": current.get("sha256") if current else None,
                    "expected_size": baseline.get("size"),
                    "observed_size": current.get("size") if current else None,
                }
            )
        passed = all(item["status"] == "MATCH" for item in comparisons)
        verification = {
            "algorithm": "sha256",
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "passed": passed,
            "files": comparisons,
        }
        status = "PASS" if passed else "FAIL"
    except Exception as exc:
        verification = {
            "algorithm": "sha256",
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "passed": False,
            "error_code": getattr(exc, "code", "VALIDATION_FAILED"),
            "error": str(exc)[:1000],
        }
        status = "ERROR"
        with connection() as conn:
            conn.execute(
                "UPDATE rbd_validation_runs SET status=%s,verification=%s::jsonb,verified_at=now(),updated_at=now() WHERE id=%s",
                (status, json.dumps(verification), run_id),
            )
            conn.commit()
        raise
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE rbd_validation_runs
               SET status=%s,verification=%s::jsonb,verified_at=now(),updated_at=now()
             WHERE id=%s
            RETURNING *
            """,
            (status, json.dumps(verification), run_id),
        ).fetchone()
        conn.commit()
    for item in observed.values():
        present = item.get("status") == "PRESENT"
        _audit_file_operation(
            "RBD_FILE_READ",
            volume,
            item["path"],
            request_id=request.state.request_id,
            started=started,
            success=present,
            bytes_count=int(item.get("size") or 0),
            content_type=item.get("mime_type"),
            error="Validation file is missing" if not present else None,
            error_code="FILE_NOT_FOUND" if not present else None,
        )
    return _validation_result(dict(row))


def _executor_terminal_ws_url(ticket: str) -> str:
    parsed = urlsplit(get_settings().rbd_executor_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, "/ws/terminal", urlencode({"ticket": ticket}), ""))


@terminal_router.websocket("/ws/terminal")
async def terminal_websocket(websocket: WebSocket, ticket: str = Query(min_length=32, max_length=128)):
    try:
        async with websocket_connect(
            _executor_terminal_ws_url(ticket),
            max_size=64 * 1024,
            open_timeout=get_settings().rbd_executor_timeout_seconds,
        ) as upstream:
            await websocket.accept()

            async def browser_to_executor():
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("bytes") is not None:
                        await upstream.send(message["bytes"])
                    elif message.get("text") is not None:
                        await upstream.send(message["text"])

            async def executor_to_browser():
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            tasks = {
                asyncio.create_task(browser_to_executor()),
                asyncio.create_task(executor_to_browser()),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except (WebSocketDisconnect, ConnectionClosed):
        return
    except Exception:
        try:
            await websocket.close(code=1011, reason="Terminal bridge unavailable")
        except Exception:
            pass
