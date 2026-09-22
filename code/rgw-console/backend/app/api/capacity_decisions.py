from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter

from .rbd import RbdControlError
from ..db import connection


router = APIRouter(prefix="/api/capacity", tags=["capacity"])


def _json_value(value: Any) -> Any:
    if isinstance(value, (UUID, datetime)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


@router.get("/decisions/{decision_id}")
def capacity_decision(decision_id: UUID):
    with connection() as conn:
        row = conn.execute(
            """
            SELECT decision.*,
                   reservation.id AS reservation_id,
                   reservation.state AS reservation_state,
                   reservation.reservation_class,
                   reservation.remaining_commitment_bytes
              FROM capacity_decisions decision
              LEFT JOIN capacity_reservations reservation
                ON reservation.decision_id=decision.id
             WHERE decision.id=%s
            """,
            (decision_id,),
        ).fetchone()
    if row is None:
        raise RbdControlError(
            404,
            "CAPACITY_DECISION_NOT_FOUND",
            "Capacity decision was not found",
        )
    return _json_value(dict(row))

