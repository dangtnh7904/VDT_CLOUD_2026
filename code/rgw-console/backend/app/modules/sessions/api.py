from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...config import get_settings
from ..cluster_profiles.executor_adapter import ExecutorClusterObservationAdapter
from .domain import CreateSessionCommand, SessionError
from .repository import PostgresSessionRepository
from .service import SessionService


router = APIRouter(prefix="/api/v1/sessions", tags=["sessions-v1"])


class CreateSessionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    workflow_types: list[
        Literal["UPGRADE_PRODUCTION", "QOS_OBSERVER", "LAB_TEST", "ROLLBACK", "LEGACY"]
    ] = Field(min_length=1, max_length=5)


def _service() -> SessionService:
    return SessionService(
        get_settings(),
        ExecutorClusterObservationAdapter(),
        PostgresSessionRepository(),
    )


def _raise(request: Request, exc: SessionError) -> HTTPException:
    status = 404 if exc.code == "SESSION_NOT_FOUND" else 503 if exc.retryable else 409
    return HTTPException(
        status_code=status,
        detail={
            "request_id": request.state.request_id,
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "observed_state": exc.observed_state,
            "evidence_refs": [],
        },
    )


@router.post("", status_code=201)
def create_session(payload: CreateSessionRequest, request: Request):
    try:
        return _service().create(
            CreateSessionCommand(
                name=payload.name.strip(),
                workflow_types=tuple(payload.workflow_types),
            )
        )
    except (SessionError, ValueError) as exc:
        if isinstance(exc, ValueError):
            exc = SessionError("CLUSTER_PROFILE_MISMATCH", str(exc))
        raise _raise(request, exc) from exc


@router.get("")
def list_sessions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        settings = get_settings()
        if not settings.cluster_id:
            raise SessionError("CLUSTER_PROFILE_MISMATCH", "CLUSTER_ID is required")
        return {
            "schema_version": 1,
            "cluster_id": settings.cluster_id,
            "items": PostgresSessionRepository().list(
                cluster_id=settings.cluster_id,
                limit=limit,
            ),
        }
    except (SessionError, ValueError) as exc:
        if isinstance(exc, ValueError):
            exc = SessionError("CLUSTER_PROFILE_MISMATCH", str(exc))
        raise _raise(request, exc) from exc


@router.get("/{session_id}")
def get_session(session_id: UUID, request: Request):
    try:
        # Reading an existing session remains available after a profile switch;
        # only create/resume/mutation paths resolve and bind the current cluster.
        session = PostgresSessionRepository().get(session_id)
        if session is None:
            raise SessionError("SESSION_NOT_FOUND", "session does not exist")
        return session
    except (SessionError, ValueError) as exc:
        if isinstance(exc, ValueError):
            exc = SessionError("CLUSTER_PROFILE_MISMATCH", str(exc))
        raise _raise(request, exc) from exc


@router.get("/{session_id}/timeline")
def get_session_timeline(session_id: UUID, request: Request):
    try:
        return {
            "schema_version": 1,
            "session_id": str(session_id),
            "events": PostgresSessionRepository().timeline(session_id),
        }
    except SessionError as exc:
        raise _raise(request, exc) from exc


@router.get("/{session_id}/report")
def get_session_report(session_id: UUID, request: Request):
    try:
        return PostgresSessionRepository().report(session_id)
    except SessionError as exc:
        raise _raise(request, exc) from exc
