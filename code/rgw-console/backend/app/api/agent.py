from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .rbd import RbdControlError
from ..services.rbd_agent_client import RbdAgentClient, RbdAgentClientError


router = APIRouter(prefix="/api/agent", tags=["agent"])


def _public_health(result: dict[str, Any]) -> dict[str, Any]:
    """Return only identity/capability fields; never proxy arbitrary agent data."""

    allowed = {
        "status",
        "fsid",
        "agent_version",
        "version",
        "protocol_version",
        "collected_at",
        "capabilities",
        "actions",
        "rbd_scope",
        "read_only",
    }
    return {key: value for key, value in result.items() if key in allowed}


@router.get("/health")
def agent_health():
    try:
        client = RbdAgentClient.from_settings()
        health = client.health()
        capabilities = client.capabilities()
    except ValueError as exc:
        raise RbdControlError(
            503,
            "AGENT_NOT_CONFIGURED",
            str(exc),
            retryable=False,
        ) from exc
    except RbdAgentClientError as exc:
        raise RbdControlError(
            503,
            exc.code,
            exc.message,
            retryable=exc.retryable,
            observed_state=exc.details or None,
        ) from exc
    response = _public_health(health)
    response["capabilities"] = _public_health(capabilities)
    return response
