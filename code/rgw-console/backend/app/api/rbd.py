from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid5

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..db import connection
from ..models.domain import (
    IdempotencyClaimRequest,
    IdempotencyDisposition,
    IdempotencyState,
)
from ..services.capacity_guard import CapacityRejected, finish_reservation, require_admission
from ..services.idempotency import IdempotencyService, canonical_request_fingerprint
from ..services.rbd_agent_client import RbdAgentClient, RbdAgentClientError


router = APIRouter(prefix="/api/rbd", tags=["rbd"])
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
    logical_size_bytes: int = Field(gt=0, le=1 << 50)
    capacity_mode: Literal["reserved-logical"] = "reserved-logical"
    filesystem: Literal["ext4"] = "ext4"
    auto_mount: bool
    display_name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("pool", "namespace", "display_name")
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


def _agent_namespace(namespace: str | None) -> str:
    return namespace or ""


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


def _volume_result(row: dict[str, Any]) -> dict[str, Any]:
    result = _json_value(dict(row))
    result["namespace"] = result.get("namespace") or ""
    result["status_url"] = f"/api/rbd/volumes/{result['id']}"
    return result


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
        result = RbdAgentClient.from_settings().rbd_pool_list()
    except (RbdAgentClientError, ValueError) as exc:
        code = exc.code if isinstance(exc, RbdAgentClientError) else "AGENT_NOT_CONFIGURED"
        raise RbdControlError(
            503,
            code,
            str(exc),
            retryable=isinstance(exc, RbdAgentClientError) and exc.retryable,
        ) from exc
    candidates = result.get("pools", result.get("items", []))
    pools: list[dict[str, Any]] = []
    for item in candidates if isinstance(candidates, list) else []:
        name = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
        if name in configured:
            pools.append({"name": name} if isinstance(item, str) else _json_value(item))
    return {"enabled": True, "pools": pools, "fsid": result.get("fsid")}


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
    items = [dict(row) for row in rows[:limit]]
    return {
        "items": [_volume_result(row) for row in items],
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
    _assert_scope(payload.pool, payload.namespace)
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
    image_name = f"{get_settings().rbd_image_prefix}{volume_id.hex}"
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
    return _volume_result(_load_volume(volume_id))


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
    },
}
_INTENDED_STATE = {"MOUNT": "READY", "UNMOUNT": "UNMOUNTED", "DELETE": "DELETED"}


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
                if observed in {"RECONCILING", "UNKNOWN", "REQUESTED", "CAPACITY_RESERVED"}:
                    raise RbdControlError(
                        423,
                        "RECONCILING",
                        "The volume must be reconciled before this transition",
                        retryable=True,
                        observed_state={"observed_state": observed},
                    )
                if observed not in _ALLOWED_TRANSITIONS[action_type]:
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

