from __future__ import annotations

import hashlib
import asyncio
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ...config import get_settings
from .service import AsIsService, AsIsError, CollectionControl, OBSERVATION_DEADLINE_SECONDS, encoded


router = APIRouter(prefix='/api/v1/as-is', tags=['as-is-v1'])
DaemonType = Literal['mon', 'mgr', 'osd', 'rgw', 'mds']
DaemonKey = Annotated[str, Field(pattern=r'^(mon|mgr|osd|rgw|mds)\.[A-Za-z0-9_.-]{1,128}$')]
Phase = Literal['BEFORE', 'DURING', 'AFTER']


class ObserveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    daemon_types: list[DaemonType] | None = Field(default=None, min_length=1, max_length=5)
    daemon_keys: list[DaemonKey] = Field(default_factory=list, max_length=128)
    deep: bool = False


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    daemon_keys: list[DaemonKey] = Field(min_length=1, max_length=128)
    phase: Phase
    note: str = Field(default='', max_length=2000)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    collection_a_id: UUID
    collection_b_id: UUID
    daemon_type: DaemonType
    daemon_keys: list[DaemonKey] = Field(default_factory=list, max_length=128)


def _service():
    return AsIsService(get_settings())


def _call(operation):
    try:
        return operation()
    except AsIsError as exc:
        raise HTTPException(exc.status, {'code': exc.code, 'message': exc.message}) from exc


def _actor(request):
    return getattr(request.state, 'console_actor', None) or 'local-operator'


async def _observe_call(request, operation, *, timeout_seconds=OBSERVATION_DEADLINE_SECONDS):
    # Cancelling fetch() previously left the sync endpoint doing every source
    # read. Watch the disconnect without blocking the ASGI event loop and signal
    # the source coordinator; its worker owns slot release after reads settle.
    control = CollectionControl(timeout_seconds)
    worker = asyncio.create_task(asyncio.to_thread(_call, lambda: operation(control)))

    async def disconnect():
        # FastAPI has already consumed the complete JSON body. Awaiting receive
        # (rather than nonblocking is_disconnected polling) also works through
        # BaseHTTPMiddleware's AnyIO receive channel, which checkpoints before
        # yielding a message and can hide disconnects from cancelled polls.
        try:
            while True:
                if (await request.receive())['type'] == 'http.disconnect':
                    control.cancel()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            control.cancel()

    monitor = asyncio.create_task(disconnect())
    try:
        return await asyncio.shield(worker)
    finally:
        monitor.cancel()
        try:
            await monitor
        except asyncio.CancelledError:
            pass
        if not worker.done():
            control.cancel()
            # ASGI shutdown/task cancellation must not cancel the thread's slot
            # lifetime or leave its eventual exception unobserved.
            worker.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)


def _export(payload, prefix):
    content = encoded(payload)
    checksum = hashlib.sha256(content).hexdigest()
    return Response(content, media_type='application/json', headers={
        'Content-Disposition': f'attachment; filename="{prefix}-{payload.get("id", "comparison")}.json"',
        'X-Export-Sha256': checksum, 'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff'})


@router.post('/observe')
async def observe(payload: ObserveRequest, request: Request):
    service = _service()
    budget = OBSERVATION_DEADLINE_SECONDS + (service.settings.osd_info_collector_timeout_seconds if payload.deep else 0)
    return await _observe_call(request, lambda control: service.observe(**payload.model_dump(), control=control),
        timeout_seconds=budget)


@router.post('/export')
async def export_fresh(payload: ObserveRequest, request: Request):
    service = _service()
    budget = OBSERVATION_DEADLINE_SECONDS + (service.settings.osd_info_collector_timeout_seconds if payload.deep else 0)
    observed = await _observe_call(request, lambda control: service.observe(**payload.model_dump(), control=control),
        timeout_seconds=budget)
    return _export(observed, 'hien-trang-moi')


@router.post('/collections', status_code=201)
def create(payload: CollectionRequest, request: Request,
           idempotency_key: Annotated[str | None, Header(alias='Idempotency-Key', min_length=8, max_length=128)] = None):
    return _call(lambda: _service().create(**payload.model_dump(), idempotency_key=idempotency_key, actor=_actor(request)))


@router.get('/collections')
def list_collections(daemon_type: DaemonType | None = None, from_date: str | None = None,
                     to_date: str | None = None, phase: Phase | None = None, include_deleted: bool = False,
                     limit: int = Query(default=10, ge=1, le=200),
                     cursor: str | None = Query(default=None, min_length=1, max_length=1024),
                     q: str | None = Query(default=None, max_length=200),
                     quality: Literal['VALID', 'PARTIAL'] | None = None,
                     daemon_key: DaemonKey | None = None):
    return _call(lambda: _service().list(daemon_type=daemon_type, from_date=from_date, to_date=to_date,
        phase=phase, include_deleted=include_deleted, limit=limit, cursor=cursor, query=q,
        quality=quality, daemon_key=daemon_key))


@router.get('/collections/{collection_id}')
def get_collection(collection_id: UUID, include_deleted: bool = False):
    return _call(lambda: _service().get(collection_id, include_deleted=include_deleted))


@router.get('/collections/{collection_id}/export')
def export_saved(collection_id: UUID, include_deleted: bool = False, daemon_type: DaemonType | None = None,
                 daemon_key: DaemonKey | None = None):
    return _export(_call(lambda: _service().export_view(collection_id, include_deleted=include_deleted,
        daemon_type=daemon_type, daemon_key=daemon_key)), 'collection-da-luu')


@router.delete('/collections/{collection_id}')
def delete(collection_id: UUID, request: Request):
    return _call(lambda: _service().set_deleted(collection_id, deleted=True, actor=_actor(request)))


@router.post('/collections/{collection_id}/restore')
def restore(collection_id: UUID, request: Request):
    return _call(lambda: _service().set_deleted(collection_id, deleted=False, actor=_actor(request)))


@router.post('/compare')
def compare(payload: CompareRequest):
    return _call(lambda: _service().compare(**payload.model_dump()))


@router.post('/compare/export')
def export_comparison(payload: CompareRequest):
    return _export(_call(lambda: _service().compare(**payload.model_dump())), 'so-sanh')
