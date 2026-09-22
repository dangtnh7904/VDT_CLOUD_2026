import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import connection
from ..models.domain import IdempotencyClaimRequest, IdempotencyDisposition, IdempotencyState
from ..services.capacity_guard import snapshot_response
from ..services.idempotency import IdempotencyService, canonical_request_fingerprint


router = APIRouter(prefix="/api/control", tags=["control"])
idempotency_service = IdempotencyService()


class ControlRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _state() -> dict:
    with connection() as conn:
        row = conn.execute(
            "SELECT desired_state, reason, action_id, updated_by, updated_at FROM control_state WHERE id=true"
        ).fetchone()
    result = dict(row)
    if result.get("updated_at"):
        result["updated_at"] = result["updated_at"].isoformat()
    if result.get("action_id"):
        result["action_id"] = str(result["action_id"])
    return result


@router.get("/state")
def control_state():
    return _state()


def _set_state(target: Literal["NORMAL", "READ_CLEANUP_ONLY"], reason: str, actor: str) -> dict:
    action_id = str(uuid.uuid4())
    with connection() as conn:
        conn.execute(
            """
            UPDATE control_state
               SET desired_state=%s, reason=%s, action_id=%s, updated_by=%s, updated_at=now()
             WHERE id=true
            """,
            (target, reason, action_id, actor),
        )
        if target == "READ_CLEANUP_ONLY":
            conn.execute(
                """
                UPDATE stream_jobs
                   SET state='paused', paused_reason=%s, updated_at=now()
                 WHERE state IN ('pending','running')
                """,
                (f"Emergency stop: {reason}",),
            )
        conn.commit()
    return _state()


def _begin(request: Request, key: str, action: str, body: ControlRequest, actor: str):
    scope = "control:global"
    resource = f"control:{action}"
    fingerprint = canonical_request_fingerprint(
        "POST",
        resource,
        {"reason": body.reason, "actor": actor},
    )
    claim = idempotency_service.claim(
        IdempotencyClaimRequest(
            scope=scope,
            idempotency_key=key,
            http_method="POST",
            resource=resource,
            request_fingerprint=fingerprint,
            owner_id=request.state.request_id,
            request_id=uuid.UUID(request.state.request_id),
        )
    )
    if claim.disposition is IdempotencyDisposition.REPLAY:
        return claim, JSONResponse(
            status_code=claim.record.response_status or 200,
            content=claim.record.response_body or {},
            headers={"Idempotency-Replayed": "true"},
        )
    if claim.disposition is IdempotencyDisposition.IN_PROGRESS:
        raise HTTPException(
            409,
            {
                "request_id": str(claim.record.request_id),
                "code": "IDEMPOTENCY_IN_PROGRESS",
                "message": "The same control action is already in progress",
                "retryable": True,
                "observed_state": {"state": claim.record.state.value},
            },
        )
    claim.record = idempotency_service.mark_in_progress(
        scope,
        key,
        owner_id=request.state.request_id,
        fencing_generation=claim.record.fencing_generation,
    )
    return claim, None


def _finish(claim, state: IdempotencyState, status: int, body: dict, code: str | None = None):
    idempotency_service.finish(
        claim.record.scope,
        claim.record.idempotency_key,
        owner_id=claim.record.owner_id,
        fencing_generation=claim.record.fencing_generation,
        state=state,
        response_status=status,
        response_body=body,
        error_code=code,
    )


def _error_body(request: Request, exc: HTTPException) -> dict:
    if isinstance(exc.detail, dict):
        detail = dict(exc.detail)
        detail.setdefault("request_id", request.state.request_id)
        detail.setdefault("observed_state", None)
        return {"detail": detail}
    return {
        "detail": {
            "request_id": request.state.request_id,
            "code": "CONTROL_ACTION_FAILED",
            "message": str(exc.detail),
            "retryable": exc.status_code >= 500,
            "observed_state": None,
        }
    }


@router.post("/emergency-stop")
def emergency_stop(
    body: ControlRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    actor: str = Header(default="console", alias="X-Actor"),
):
    actor = actor[:100]
    claim, replay = _begin(request, idempotency_key, "emergency-stop", body, actor)
    if replay:
        return replay
    try:
        result = _set_state("READ_CLEANUP_ONLY", body.reason, actor)
        result["request_id"] = request.state.request_id
        _finish(claim, IdempotencyState.SUCCEEDED, 200, result)
        return result
    except Exception as exc:
        error = {
            "detail": {
                "request_id": request.state.request_id,
                "code": "CONTROL_ACTION_FAILED",
                "message": str(exc)[:1000],
                "retryable": True,
                "observed_state": None,
            }
        }
        _finish(claim, IdempotencyState.FAILED_RETRYABLE, 503, error, "CONTROL_ACTION_FAILED")
        raise HTTPException(503, error["detail"]) from exc


@router.post("/resume")
def resume_control(
    body: ControlRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    actor: str = Header(default="console", alias="X-Actor"),
):
    actor = actor[:100]
    claim, replay = _begin(request, idempotency_key, "resume", body, actor)
    if replay:
        return replay
    try:
        capacity = snapshot_response()
        if not capacity.get("fresh"):
            raise HTTPException(
            503,
            {
                "code": "TELEMETRY_STALE",
                "message": "Cannot resume without fresh capacity telemetry",
                "retryable": True,
                    "request_id": request.state.request_id,
            },
            )
        ratio = capacity.get("most_full_ratio")
        resume_ratio = capacity["policy"]["resume_ratio"]
        if ratio is None or ratio >= resume_ratio:
            raise HTTPException(
            409,
            {
                "code": "CAPACITY_LIMIT",
                "message": f"Most-full OSD must be below resume ratio {resume_ratio:.4f}",
                "retryable": True,
                    "request_id": request.state.request_id,
            },
            )
        settings = get_settings()
        if not settings.ceph_expected_fsid or capacity.get("fsid") != settings.ceph_expected_fsid:
            raise HTTPException(
                409,
                {
                    "code": "RECONCILING",
                    "message": "Capacity telemetry cluster identity is not configured or does not match",
                    "retryable": True,
                    "request_id": request.state.request_id,
                },
            )
        required = int(settings.capacity_resume_consecutive_samples)
        affected_pools = sorted(settings.rgw_affected_pool_set | settings.rbd_allowed_pool_set)
        if not affected_pools:
            raise HTTPException(
                409,
                {
                    "code": "RECONCILING",
                    "message": "No affected Ceph pool scope is configured",
                    "retryable": True,
                    "request_id": request.state.request_id,
                },
            )
        with connection() as conn:
            samples = conn.execute(
            """
            SELECT snapshot.id,snapshot.osdmap_epoch,snapshot.captured_at,snapshot.fresh,
                   snapshot.cluster_health_summary,
                   max(osd.used_ratio) AS most_full_ratio,
                   bool_and(coalesce((osd.scope_metadata->>'capacity_scope_complete')::boolean,false)) AS scope_complete
              FROM capacity_snapshots snapshot
              JOIN capacity_osds osd ON osd.snapshot_id=snapshot.id
             WHERE snapshot.fsid=%s
               AND (osd.scope_metadata->'eligible_pools') ?| %s
             GROUP BY snapshot.id
             ORDER BY snapshot.captured_at DESC,snapshot.id DESC
             LIMIT %s
            """,
                (settings.ceph_expected_fsid, affected_pools, required),
            ).fetchall()
        epochs = {row["osdmap_epoch"] for row in samples}
        now = datetime.now(timezone.utc)
        captured = []
        for row in samples:
            timestamp = row["captured_at"]
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            captured.append(timestamp)
        timing_safe = bool(captured) and all(
            0 <= (now - timestamp).total_seconds() <= settings.capacity_metrics_max_age_seconds
            for timestamp in captured
        )
        timing_safe = timing_safe and all(
            0 <= (captured[index] - captured[index + 1]).total_seconds()
            <= settings.capacity_metrics_max_age_seconds
            for index in range(len(captured) - 1)
        )
        unsafe_health_fields = (
            "degraded", "remapped", "recovering", "backfilling", "full", "backfillfull"
        )
        if (
            len(samples) < required
            or len(epochs) != 1
            or not timing_safe
            or any(
                not row["fresh"]
                or not row["scope_complete"]
                or row["most_full_ratio"] is None
                or float(row["most_full_ratio"]) >= resume_ratio
                or any(bool((row["cluster_health_summary"] or {}).get(field)) for field in unsafe_health_fields)
                for row in samples
            )
        ):
            raise HTTPException(
            409,
            {
                "code": "RECONCILING",
                "message": f"Resume requires {required} consecutive fresh samples below {resume_ratio:.4f} at one OSDMap epoch",
                "retryable": True,
                "request_id": str(uuid.uuid4()),
            },
            )
        result = _set_state("NORMAL", body.reason, actor)
        result["request_id"] = request.state.request_id
        _finish(claim, IdempotencyState.SUCCEEDED, 200, result)
        return result
    except HTTPException as exc:
        error = _error_body(request, exc)
        _finish(
            claim,
            IdempotencyState.FAILED_RETRYABLE,
            exc.status_code,
            error,
            error["detail"]["code"],
        )
        raise
    except Exception as exc:
        error = {
            "detail": {
                "request_id": request.state.request_id,
                "code": "CONTROL_ACTION_FAILED",
                "message": str(exc)[:1000],
                "retryable": True,
                "observed_state": None,
            }
        }
        _finish(claim, IdempotencyState.FAILED_RETRYABLE, 503, error, "CONTROL_ACTION_FAILED")
        raise HTTPException(503, error["detail"]) from exc
