from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..services.performance import history_samples, latest_sample, scope_supported


router = APIRouter(prefix="/api/performance", tags=["performance"])
PerformanceSource = Literal["application", "ceph", "device"]
ScopeType = Literal["cluster", "osd", "pool", "image", "job", "operation"]


def _default_scope(source: str, scope_type: str, scope: str | None) -> str:
    if scope:
        return scope
    if source == "application" and scope_type == "cluster":
        return "console"
    if source == "ceph" and scope_type == "cluster":
        return get_settings().ceph_expected_fsid or "unconfigured"
    return "all"


@router.get("/current")
def current_performance(
    source: PerformanceSource = "application",
    scope_type: ScopeType = "cluster",
    scope: str | None = Query(default=None, min_length=1, max_length=255),
):
    resolved_scope = _default_scope(source, scope_type, scope)
    return latest_sample(source, scope_type, resolved_scope)


@router.get("/history")
def performance_history(
    source: PerformanceSource = "application",
    scope_type: ScopeType = "cluster",
    scope: str | None = Query(default=None, min_length=1, max_length=255),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    step_seconds: int = Query(default=15, alias="step", ge=10, le=3600),
):
    ended_at = to_time or datetime.now(timezone.utc)
    started_at = from_time or ended_at - timedelta(minutes=5)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)
    if started_at >= ended_at:
        return {
            "state": "INVALID_RANGE",
            "items": [],
            "reasons": ["from must be earlier than to"],
        }
    if ended_at - started_at > timedelta(days=get_settings().performance_rollup_retention_days):
        started_at = ended_at - timedelta(days=get_settings().performance_rollup_retention_days)
    resolved_scope = _default_scope(source, scope_type, scope)
    if not scope_supported(source, scope_type):
        return {
            "state": "UNAVAILABLE",
            "source": source,
            "scope_type": scope_type,
            "scope": resolved_scope,
            "items": [],
            "reasons": ["UNSUPPORTED_SCOPE"],
        }
    if scope_type == "osd" and not resolved_scope.isdigit():
        return {
            "state": "UNAVAILABLE",
            "source": source,
            "scope_type": scope_type,
            "scope": resolved_scope,
            "items": [],
            "reasons": ["INVALID_SCOPE"],
        }
    sample_kind, items = history_samples(
        source,
        scope_type,
        resolved_scope,
        started_at=started_at,
        ended_at=ended_at,
        step_seconds=step_seconds,
    )
    return {
        "state": "OK",
        "source": source,
        "scope_type": scope_type,
        "scope": resolved_scope,
        "sample_kind": sample_kind,
        "from": started_at.isoformat(),
        "to": ended_at.isoformat(),
        "step_seconds": step_seconds,
        "items": items,
    }


@router.get("/stream")
async def performance_stream(
    source: PerformanceSource = "application",
    scope_type: ScopeType = "cluster",
    scope: str | None = Query(default=None, min_length=1, max_length=255),
):
    resolved_scope = _default_scope(source, scope_type, scope)

    async def events():
        last_id = ""
        while True:
            try:
                payload = await asyncio.to_thread(
                    latest_sample, source, scope_type, resolved_scope
                )
                event_id = str(payload.get("captured_at") or payload.get("state"))
                if event_id != last_id:
                    yield f"id: {event_id}\ndata: {json.dumps(payload, default=str)}\n\n"
                    last_id = event_id
            except asyncio.CancelledError:
                break
            except Exception:
                payload = {"state": "UNAVAILABLE", "reasons": ["PERFORMANCE_QUERY_FAILED"]}
                yield f"event: error\ndata: {json.dumps(payload)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
