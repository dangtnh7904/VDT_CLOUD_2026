from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...config import get_settings
from .domain import CollectionPhase, OsdInfoError
from .executor_adapter import ExecutorOsdInfoAdapter
from .repository import PostgresOsdInfoRepository
from .service import OsdInfoService


router = APIRouter(prefix="/api/v1/osd-inventory/collections", tags=["osd-inventory-v1"])
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


class CreateCollectionRequest(BaseModel):
    session_id: UUID
    phase: Literal["MANUAL", "BEFORE", "DURING", "AFTER_START", "AFTER_STABLE"] = "MANUAL"
    osd_ids: list[int] | None = Field(default=None, min_length=1, max_length=128)


def _service(*, with_collector: bool = False) -> OsdInfoService:
    return OsdInfoService(
        get_settings(),
        PostgresOsdInfoRepository(),
        ExecutorOsdInfoAdapter() if with_collector else None,
    )


def _http_error(request: Request, exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "OSD_INFO_COLLECTION_FAILED")
    retryable = bool(getattr(exc, "retryable", False))
    if code in {"SESSION_NOT_FOUND", "OSD_INVENTORY_NOT_FOUND"}:
        status = 404
    elif code in {"INVALID_REQUEST"}:
        status = 422
    elif retryable:
        status = 503
    else:
        status = 409
    return HTTPException(
        status_code=status,
        detail={
            "request_id": request.state.request_id,
            "code": code,
            "message": getattr(exc, "message", str(exc)),
            "retryable": retryable,
            "observed_state": getattr(exc, "observed_state", {}),
            "evidence_refs": [],
        },
    )


@router.post("", status_code=201)
def create_collection(
    payload: CreateCollectionRequest,
    request: Request,
    idempotency_key: IdempotencyHeader,
):
    try:
        osd_ids = tuple(payload.osd_ids) if payload.osd_ids is not None else None
        return _service(with_collector=True).create(
            session_id=payload.session_id,
            phase=CollectionPhase(payload.phase),
            requested_osd_ids=osd_ids,
            idempotency_key=idempotency_key,
        )
    except (OsdInfoError, ValueError) as exc:
        raise _http_error(request, exc) from exc


@router.get("")
def list_collections(
    session_id: UUID,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return _service().list(session_id=session_id, limit=limit)
    except OsdInfoError as exc:
        raise _http_error(request, exc) from exc


@router.get("/compare")
def compare_collections(
    before_id: UUID,
    after_id: UUID,
    request: Request,
):
    try:
        return _service().compare(before_id=before_id, after_id=after_id)
    except OsdInfoError as exc:
        raise _http_error(request, exc) from exc


@router.get("/compare-config")
def compare_collection_config(
    before_id: UUID,
    after_id: UUID,
    request: Request,
):
    try:
        return _service().compare_evidence(before_id=before_id, after_id=after_id)
    except OsdInfoError as exc:
        raise _http_error(request, exc) from exc


@router.get("/{collection_id}")
def get_collection(collection_id: UUID, request: Request):
    try:
        return _service().get(collection_id)
    except OsdInfoError as exc:
        raise _http_error(request, exc) from exc


@router.get("/{collection_id}/evidence")
def get_collection_evidence(collection_id: UUID, request: Request):
    try:
        return _service().get_evidence(collection_id)
    except OsdInfoError as exc:
        raise _http_error(request, exc) from exc


@router.get("/{collection_id}/osds/{osd_id}")
def get_collection_osd(collection_id: UUID, osd_id: int, request: Request):
    try:
        if osd_id < 0:
            raise OsdInfoError("INVALID_REQUEST", "OSD ID must be non-negative")
        return _service().get_osd(collection_id, osd_id)
    except OsdInfoError as exc:
        raise _http_error(request, exc) from exc
