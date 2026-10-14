from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ...config import get_settings
from .domain import ClusterReadError
from .executor_adapter import ExecutorClusterObservationAdapter
from .service import ClusterProfileService


router = APIRouter(prefix="/api/v1/cluster", tags=["cluster-v1"])


def _service() -> ClusterProfileService:
    return ClusterProfileService(get_settings(), ExecutorClusterObservationAdapter())


def _error(request: Request, exc: ClusterReadError) -> HTTPException:
    return HTTPException(
        status_code=503 if exc.retryable else 409,
        detail={
            "request_id": request.state.request_id,
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "observed_state": exc.observed_state,
            "evidence_refs": [],
        },
    )


@router.get("/profile")
def get_profile(request: Request):
    # This endpoint is deliberately offline-safe and never probes the cluster.
    try:
        return ClusterProfileService(get_settings()).profile()
    except ValueError as exc:
        translated = ClusterReadError("CLUSTER_PROFILE_MISMATCH", str(exc))
        raise _error(request, translated) from exc


@router.get("/capabilities")
def get_capabilities(request: Request):
    try:
        return _service().capabilities()
    except (ClusterReadError, ValueError) as exc:
        if isinstance(exc, ValueError):
            exc = ClusterReadError("CLUSTER_PROFILE_MISMATCH", str(exc))
        raise _error(request, exc) from exc


@router.get("/inventory")
def get_inventory(request: Request):
    try:
        return _service().inventory()
    except (ClusterReadError, ValueError) as exc:
        if isinstance(exc, ValueError):
            exc = ClusterReadError("CLUSTER_PROFILE_MISMATCH", str(exc))
        raise _error(request, exc) from exc
