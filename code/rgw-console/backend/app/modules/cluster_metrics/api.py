from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...config import get_settings
from .normalization import metric_catalog, samples
from .service import ClusterMetricsService, CollectionError


router = APIRouter(prefix="/api/v1/cluster", tags=["cluster-metrics-v1"])


class CollectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scopes: list[Literal["cluster", "mon", "mgr", "osd", "host", "pool"]] = Field(min_length=1, max_length=6)
    resource_ids: list[Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")]] = Field(default_factory=list, max_length=128)


def _service():
    return ClusterMetricsService(get_settings())


def _call(operation):
    try:
        return operation()
    except CollectionError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


@router.get("/resources")
def get_resources():
    return _call(lambda: _service().resources())


@router.get("/metric-catalog")
def get_metric_catalog():
    return metric_catalog()


@router.get("/collections")
def list_collections(limit: int = Query(default=50, ge=1, le=200)):
    return _call(lambda: _service().list(limit))


@router.get("/collections/{collection_id}")
def get_collection(collection_id: UUID):
    return _call(lambda: _service().get(collection_id))


@router.post("/collections", status_code=201)
def create_collection(payload: CollectRequest, request: Request,
                      idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]):
    return _call(lambda: _service().create(scopes=payload.scopes, resource_ids=payload.resource_ids,
                 idempotency_key=idempotency_key, actor=getattr(request.state, "console_actor", None) or "local-operator"))


@router.get("/metrics")
def get_metrics(collection_id: UUID, metric_id: str | None = Query(default=None, max_length=100)):
    if metric_id is not None and metric_id not in {item["id"] for item in metric_catalog()["items"]}:
        raise HTTPException(422, {"code": "UNKNOWN_METRIC", "message": "Choose a metric from the catalog."})
    collection = _call(lambda: _service().get(collection_id))
    return {"items": samples(collection, [metric_id] if metric_id else None), "collection_id": str(collection_id),
            "freshness": collection["freshness"], "source": "ceph_cli_snapshot"}
