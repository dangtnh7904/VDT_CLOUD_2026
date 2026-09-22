import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..db import connection, json_ready
from ..services.capacity_guard import snapshot_response


router = APIRouter(prefix="/api/capacity", tags=["capacity"])


@router.get("")
def capacity_snapshot(
    scope_type: str | None = Query(default=None, pattern="^pool$"),
    scope: str | None = None,
):
    if bool(scope_type) != bool(scope):
        raise HTTPException(422, "scope_type and scope must be provided together")
    if scope:
        settings = get_settings()
        allowed = settings.rgw_affected_pool_set | settings.rbd_allowed_pool_set
        if scope not in allowed:
            raise HTTPException(422, "Capacity pool scope is outside the configured allowlists")
    return snapshot_response(scope_type=scope_type, scope=scope)


@router.get("/decisions/{decision_id}")
def capacity_decision(decision_id: UUID, request: Request):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM capacity_decisions WHERE id=%s",
            (str(decision_id),),
        ).fetchone()
    if not row:
        raise HTTPException(
            404,
            {
                "request_id": request.state.request_id,
                "code": "CAPACITY_DECISION_NOT_FOUND",
                "message": "Capacity decision was not found",
                "retryable": False,
                "observed_state": None,
            },
        )
    return json_ready(row)


@router.get("/stream")
async def capacity_stream():
    async def events():
        while True:
            try:
                snapshot = await asyncio.to_thread(snapshot_response)
                yield f"data: {json.dumps(snapshot, default=str)}\n\n"
            except asyncio.CancelledError:
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
