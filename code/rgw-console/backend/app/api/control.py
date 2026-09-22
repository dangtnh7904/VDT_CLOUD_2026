import uuid
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import connection
from ..services.capacity_guard import snapshot_response


router = APIRouter(prefix="/api/control", tags=["control"])


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


@router.post("/emergency-stop")
def emergency_stop(
    request: ControlRequest,
    actor: str = Header(default="console", alias="X-Actor"),
):
    return _set_state("READ_CLEANUP_ONLY", request.reason, actor[:100])


@router.post("/resume")
def resume_control(
    request: ControlRequest,
    actor: str = Header(default="console", alias="X-Actor"),
):
    capacity = snapshot_response()
    if not capacity.get("fresh"):
        raise HTTPException(
            503,
            {
                "code": "TELEMETRY_STALE",
                "message": "Cannot resume without fresh capacity telemetry",
                "retryable": True,
                "request_id": str(uuid.uuid4()),
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
                "request_id": str(uuid.uuid4()),
            },
        )
    required = int(get_settings().capacity_resume_consecutive_samples)
    with connection() as conn:
        samples = conn.execute(
            """
            SELECT snapshot.id,snapshot.osdmap_epoch,snapshot.captured_at,snapshot.fresh,
                   max(osd.used_ratio) AS most_full_ratio
              FROM capacity_snapshots snapshot
              LEFT JOIN capacity_osds osd ON osd.snapshot_id=snapshot.id
             GROUP BY snapshot.id
             ORDER BY snapshot.captured_at DESC,snapshot.id DESC
             LIMIT %s
            """,
            (required,),
        ).fetchall()
    epochs = {row["osdmap_epoch"] for row in samples}
    if (
        len(samples) < required
        or len(epochs) != 1
        or any(not row["fresh"] or row["most_full_ratio"] is None or float(row["most_full_ratio"]) >= resume_ratio for row in samples)
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
    return _set_state("NORMAL", request.reason, actor[:100])
