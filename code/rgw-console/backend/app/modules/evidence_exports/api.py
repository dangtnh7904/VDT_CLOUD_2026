from __future__ import annotations

import base64
import logging
import re
from threading import BoundedSemaphore
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from starlette.background import BackgroundTask
from starlette.responses import Response

from ...config import get_settings
from .models import ExportRequest
from .rendering import ExportError
from .service import EvidenceExportService


router = APIRouter(prefix="/api/v1/exports", tags=["evidence-exports-v1"])
_EXPORT_GATE = BoundedSemaphore(2)
logger = logging.getLogger(__name__)


def _service() -> EvidenceExportService:
    return EvidenceExportService(get_settings())


@router.post("")
def create_export(payload: ExportRequest, request: Request):
    """Return small downloads directly; oversized queries never silently truncate."""
    if not _EXPORT_GATE.acquire(blocking=False):
        raise HTTPException(429, detail={"code": "EXPORT_BUSY", "message": "Two exports are already in progress; retry shortly", "retryable": True}, headers={"Retry-After": "5"})
    try:
        download = _service().create(payload, actor=getattr(request.state, "console_actor", None))
        digest = base64.b64encode(bytes.fromhex(download.sha256)).decode("ascii")
        return Response(
            content=download.content, media_type=download.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{download.filename}"; filename*=UTF-8\'\'{quote(download.filename)}',
                "Content-Length": str(len(download.content)), "X-Export-Id": download.export_id,
                "X-Export-Sha256": download.sha256, "Content-Digest": f"sha-256=:{digest}:",
                "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            },
            # Keep the quota slot until the response has been sent, including a
            # slow client, rather than releasing it immediately after rendering.
            background=BackgroundTask(_EXPORT_GATE.release),
        )
    except Exception as exc:
        _EXPORT_GATE.release()
        if isinstance(exc, HTTPException):
            raise
        if isinstance(exc, ExportError):
            status, code, message = exc.status_code, exc.code, exc.message
        else:
            source_code = str(getattr(exc, "code", "EXPORT_SOURCE_UNAVAILABLE"))
            code = re.sub(r"[^A-Z0-9_]", "", source_code)[:80] or "EXPORT_SOURCE_UNAVAILABLE"
            status = 404 if code.endswith("NOT_FOUND") else 409 if "INVALID" in code or "NOT_READY" in code or "MISMATCH" in code else 503
            message = "Export source is unavailable or failed verification; no download was created"
        raise HTTPException(status, detail={
            "request_id": str(getattr(request.state, "request_id", "")),
            "code": code, "message": message, "retryable": status in {429, 503},
        }) from exc
