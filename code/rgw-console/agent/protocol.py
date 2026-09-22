from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

from .errors import AgentError


PROTOCOL_VERSION = 1
REQUEST_FIELDS = frozenset({"version", "request_id", "action", "params"})


@dataclass(frozen=True)
class AgentRequest:
    request_id: str
    action: str
    params: dict[str, Any]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AgentError("INVALID_JSON", f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise AgentError("INVALID_JSON", f"Unsupported JSON constant: {value}")


def decode_request(raw: bytes, allowed_actions: Iterable[str]) -> AgentRequest:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentError("INVALID_ENCODING", "Requests must be UTF-8") from exc

    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except AgentError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AgentError("INVALID_JSON", "Request is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise AgentError("INVALID_REQUEST", "Request must be a JSON object")

    unknown_fields = sorted(set(payload) - REQUEST_FIELDS)
    if unknown_fields:
        raise AgentError(
            "INVALID_REQUEST",
            "Request contains unsupported fields",
            details={"fields": unknown_fields},
        )

    if payload.get("version") != PROTOCOL_VERSION:
        raise AgentError(
            "UNSUPPORTED_PROTOCOL",
            f"Protocol version must be {PROTOCOL_VERSION}",
        )

    request_id = payload.get("request_id")
    try:
        normalized_request_id = str(UUID(request_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AgentError("INVALID_REQUEST_ID", "request_id must be a UUID") from exc
    if request_id != normalized_request_id:
        raise AgentError("INVALID_REQUEST_ID", "request_id must be a canonical UUID")

    action = payload.get("action")
    allowed = frozenset(allowed_actions)
    if not isinstance(action, str) or action not in allowed:
        raise AgentError("ACTION_NOT_ALLOWED", "The requested action is not allowed")

    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise AgentError("INVALID_PARAMS", "params must be a JSON object")
    if params:
        raise AgentError(
            "INVALID_PARAMS",
            "Read-only inventory actions do not accept parameters",
        )

    return AgentRequest(
        request_id=normalized_request_id,
        action=action,
        params=params,
    )


def encode_success(request_id: str, result: dict[str, Any]) -> bytes:
    return _encode(
        {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    )


def encode_error(request_id: str | None, error: AgentError) -> bytes:
    return _encode(
        {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": False,
            "error": error.as_payload(),
        }
    )


def _encode(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
