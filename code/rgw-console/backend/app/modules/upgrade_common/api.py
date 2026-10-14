from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ...adapters.osd_inventory_query import PostgresOsdInventoryQueryAdapter
from ...config import get_settings
from ..cluster_profiles.executor_adapter import ExecutorClusterObservationAdapter
from .domain import (
    BatchParameters,
    Pa2EndState,
    Strategy,
    UpgradeBatchSpec,
    UpgradeDomainError,
    UpgradeRunSpec,
)
from .repository import PostgresUpgradeRepository, UpgradeRepositoryError
from .service import (
    DownSetInventoryEnvelope,
    InventoryBindingEnvelope,
    PreflightEnvelope,
    UpgradeApplicationError,
    UpgradeApplicationService,
)


router = APIRouter(prefix="/api/v1", tags=["upgrade-dry-run-v1"])
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


class BatchParametersRequest(BaseModel):
    batch_size: int = Field(ge=1, le=128)
    drain_parallelism: int = Field(ge=1, le=128)
    max_simultaneous_down: int = Field(ge=1, le=128)
    return_parallelism: int = Field(ge=1, le=128)
    scrub_concurrency: int = Field(ge=1, le=128)
    promotion_parallelism: int = Field(ge=1, le=128)
    chain_parallelism: int = Field(ge=1, le=128)
    handoff_parallelism: int = Field(ge=1, le=128)
    max_pg_per_handoff_group: int = Field(ge=1, le=1_000_000)
    max_bytes_per_handoff_group: int = Field(ge=1)


class CreateBatchRequest(BaseModel):
    session_id: UUID
    name: str = Field(min_length=1, max_length=255)
    source_osds: list[int] = Field(min_length=1, max_length=128)
    destination_osds: list[int] = Field(min_length=1, max_length=128)
    parameters: BatchParametersRequest


class CreateRunRequest(BaseModel):
    batch_id: UUID
    strategy: Literal["PA1_PRODUCTION", "PA2_ROTATING_SPARE"]
    target_version: str = Field(min_length=1, max_length=128)
    target_image_digest: str = Field(min_length=71, max_length=71)
    pa2_end_state: Literal["KEEP_ROTATED_PLACEMENT", "RECONCILE_TO_POLICY"] | None = None
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"


class PreflightRequest(BaseModel):
    expected_state: Literal["CREATED"]
    plan_revision: int = Field(ge=1)
    config_snapshot_id: UUID
    resource_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class BindInventoryRequest(BaseModel):
    collection_id: UUID
    expected_state: Literal["CREATED"]
    plan_revision: int = Field(ge=1)
    config_snapshot_id: UUID
    resource_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class DownSetInventoryRequest(BaseModel):
    collection_id: UUID
    target_osd_ids: list[int] = Field(min_length=1, max_length=128)
    expected_state: str = Field(min_length=1, max_length=64)
    plan_revision: int = Field(ge=1)
    config_snapshot_id: UUID
    resource_version: int = Field(ge=1)


def _service(
    *,
    observations: bool = False,
    inventory: bool = False,
) -> UpgradeApplicationService:
    return UpgradeApplicationService(
        get_settings(),
        PostgresUpgradeRepository(),
        ExecutorClusterObservationAdapter() if observations else None,
        PostgresOsdInventoryQueryAdapter() if inventory else None,
    )


def _http_error(request: Request, exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "UPGRADE_ERROR")
    retryable = bool(getattr(exc, "retryable", False))
    if code in {"SESSION_NOT_FOUND", "BATCH_NOT_FOUND", "RUN_NOT_FOUND", "OSD_INVENTORY_NOT_FOUND"}:
        status = 404
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


@router.post("/upgrade-batches", status_code=201)
def create_batch(payload: CreateBatchRequest, request: Request, idempotency_key: IdempotencyHeader):
    try:
        parameters = BatchParameters(**payload.parameters.model_dump())
        spec = UpgradeBatchSpec(
            name=payload.name,
            source_osds=tuple(payload.source_osds),
            destination_osds=tuple(payload.destination_osds),
            parameters=parameters,
        )
        return _service().create_batch(
            session_id=payload.session_id,
            spec=spec,
            idempotency_key=idempotency_key,
        )
    except (UpgradeDomainError, UpgradeApplicationError, UpgradeRepositoryError, ValueError) as exc:
        raise _http_error(request, exc) from exc


@router.get("/upgrade-batches/{batch_id}")
def get_batch(batch_id: UUID, request: Request):
    try:
        return _service().get_batch(batch_id)
    except (UpgradeApplicationError, UpgradeRepositoryError, ValueError) as exc:
        raise _http_error(request, exc) from exc


@router.post("/upgrade-runs", status_code=201)
def create_run(payload: CreateRunRequest, request: Request, idempotency_key: IdempotencyHeader):
    if get_settings().console_read_only and (
        payload.strategy != Strategy.PA2.value
        or payload.pa2_end_state != Pa2EndState.KEEP_ROTATED.value
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "request_id": request.state.request_id,
                "code": "CONSOLE_DRY_RUN_SCOPE_REJECTED",
                "message": "New read-only plans require PA2_ROTATING_SPARE and KEEP_ROTATED_PLACEMENT",
                "retryable": False,
                "observed_state": {},
                "evidence_refs": [],
            },
        )
    try:
        strategy = Strategy(payload.strategy)
        end_state = Pa2EndState(payload.pa2_end_state) if payload.pa2_end_state else None
        spec = UpgradeRunSpec(
            strategy=strategy,
            target_version=payload.target_version.strip(),
            target_image_digest=payload.target_image_digest,
            pa2_end_state=end_state,
        )
        return _service().create_run(
            batch_id=payload.batch_id,
            spec=spec,
            idempotency_key=idempotency_key,
        )
    except (UpgradeDomainError, UpgradeApplicationError, UpgradeRepositoryError, ValueError) as exc:
        raise _http_error(request, exc) from exc


@router.get("/upgrade-runs/{run_id}")
def get_run(run_id: UUID, request: Request):
    try:
        return _service().get_run(run_id)
    except (UpgradeApplicationError, UpgradeRepositoryError, ValueError) as exc:
        raise _http_error(request, exc) from exc


@router.post("/upgrade-runs/{run_id}/inventory-bindings", status_code=201)
def bind_inventory(
    run_id: UUID,
    payload: BindInventoryRequest,
    request: Request,
    idempotency_key: IdempotencyHeader,
):
    try:
        return _service(inventory=True).bind_inventory(
            run_id=run_id,
            envelope=InventoryBindingEnvelope(**payload.model_dump()),
            idempotency_key=idempotency_key,
        )
    except (UpgradeDomainError, UpgradeApplicationError, UpgradeRepositoryError, ValueError) as exc:
        raise _http_error(request, exc) from exc


@router.get("/upgrade-runs/{run_id}/inventory-readiness")
def inventory_readiness(run_id: UUID, request: Request):
    try:
        return _service(inventory=True).inventory_readiness(run_id)
    except (UpgradeDomainError, UpgradeApplicationError, UpgradeRepositoryError, ValueError) as exc:
        raise _http_error(request, exc) from exc


@router.post("/upgrade-runs/{run_id}/down-set-readiness")
def down_set_readiness(
    run_id: UUID,
    payload: DownSetInventoryRequest,
    request: Request,
):
    try:
        return _service(inventory=True).assess_down_set_inventory(
            run_id=run_id,
            envelope=DownSetInventoryEnvelope(
                collection_id=payload.collection_id,
                target_osd_ids=tuple(payload.target_osd_ids),
                expected_state=payload.expected_state,
                plan_revision=payload.plan_revision,
                config_snapshot_id=payload.config_snapshot_id,
                resource_version=payload.resource_version,
            ),
        )
    except (UpgradeDomainError, UpgradeApplicationError, UpgradeRepositoryError, ValueError) as exc:
        raise _http_error(request, exc) from exc


@router.post("/upgrade-runs/{run_id}/preflight")
def preflight(
    run_id: UUID,
    payload: PreflightRequest,
    request: Request,
    idempotency_key: IdempotencyHeader,
):
    try:
        envelope = PreflightEnvelope(
            expected_state=payload.expected_state,
            plan_revision=payload.plan_revision,
            config_snapshot_id=payload.config_snapshot_id,
            resource_version=payload.resource_version,
            reason=payload.reason,
        )
        return _service(observations=True, inventory=True).preflight(
            run_id=run_id,
            envelope=envelope,
            idempotency_key=idempotency_key,
        )
    except (UpgradeDomainError, UpgradeApplicationError, UpgradeRepositoryError, ValueError) as exc:
        raise _http_error(request, exc) from exc
