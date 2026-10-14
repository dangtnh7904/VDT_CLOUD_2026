from __future__ import annotations

import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...config import get_settings
from .service import PreviewError, PreviewService

router = APIRouter(prefix="/api/v1/osdmap-previews", tags=["osdmap-preview"])


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    osd_id: Annotated[int, Field(strict=True, ge=0)]
    crush_weight: Annotated[float, Field(strict=True, ge=0, le=32767)]


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: list[Change] = Field(min_length=1, max_length=128)
    pool_id: Annotated[int, Field(strict=True, ge=0)] | None = None

    @model_validator(mode="after")
    def distinct(self):
        if len({x.osd_id for x in self.changes}) != len(self.changes):
            raise ValueError("Mỗi OSD chỉ có một giá trị CRUSH weight.")
        return self


def call(operation):
    try:
        return operation()
    except PreviewError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from None
    except (ValueError, OSError, KeyError):
        raise HTTPException(503, {"code": "OSDMAP_UNAVAILABLE", "message": "Kịch bản không đọc được hoặc không vượt qua kiểm tra dữ liệu."}) from None


@router.get("/capabilities")
def capabilities():
    return call(lambda: PreviewService(get_settings()).capabilities())


@router.post("", status_code=201)
def create(payload: PreviewRequest, request: Request):
    return call(lambda: PreviewService(get_settings()).create([x.model_dump() for x in payload.changes], payload.pool_id,
                       getattr(request.state, "console_actor", None) or "local-operator"))


@router.get("/{preview_id}")
def get(preview_id: UUID):
    return call(lambda: PreviewService(get_settings()).get(preview_id))


@router.post("/{preview_id}/export")
def export(preview_id: UUID):
    # Historical export never re-collects/recomputes. Epoch status is from creation time.
    result = call(lambda: PreviewService(get_settings()).get(preview_id, refresh=False))
    result["export_note"] = "Dự đoán đã lưu; trạng thái epoch là tại lúc tính. Không phải collection As-is."
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > 16 * 1024 * 1024:
        raise HTTPException(413, {"code": "EXPORT_LIMIT", "message": "Kết quả quá lớn; tính lại với phạm vi một pool."})
    return Response(encoded, media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="du-doan-osdmap-{preview_id}.json"',
        "X-Export-Sha256": hashlib.sha256(encoded).hexdigest(), "Cache-Control": "no-store"})
