import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..services.capacity_guard import snapshot_response


router = APIRouter(prefix="/api/capacity", tags=["capacity"])


@router.get("")
def capacity_snapshot():
    return snapshot_response()


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
