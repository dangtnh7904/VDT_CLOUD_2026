from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from uuid import UUID

from .errors import AgentError


PROTOCOL_VERSION = 1
REQUEST_FIELDS = frozenset({"version", "request_id", "action", "params"})
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_IMAGE_ID = re.compile(r"^[0-9a-f]{1,64}$")


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


def decode_request(
    raw: bytes,
    allowed_actions: Iterable[str],
    action_schemas: Mapping[str, Mapping[str, Mapping[str, str]]] | None = None,
) -> AgentRequest:
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
    if action_schemas is None and params:
        raise AgentError(
            "INVALID_PARAMS",
            "Read-only inventory actions do not accept parameters",
        )
    if action_schemas is not None:
        validate_action_params(action, params, action_schemas)

    return AgentRequest(
        request_id=normalized_request_id,
        action=action,
        params=params,
    )


def validate_action_params(
    action: str,
    params: dict[str, Any],
    action_schemas: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> None:
    """Validate the closed, versioned wire schema for one action.

    Scope allowlists and observed-state identity are deliberately enforced by
    the action runner as a second, independent layer.
    """

    schema = action_schemas.get(action)
    if schema is None:
        raise AgentError("ACTION_NOT_ALLOWED", "The requested action is not allowed")
    required = schema.get("required", {})
    optional = schema.get("optional", {})
    missing = sorted(set(required) - set(params))
    unknown = sorted(set(params) - set(required) - set(optional))
    if missing or unknown:
        raise AgentError(
            "INVALID_PARAMS",
            "Action parameters do not match the action schema",
            details={"missing": missing, "unknown": unknown},
        )
    for name, kind in {**required, **optional}.items():
        if name not in params:
            continue
        _validate_value(name, params[name], kind)


def _validate_value(name: str, value: Any, kind: str) -> None:
    if kind == "uuid":
        try:
            normalized = str(UUID(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AgentError("INVALID_PARAMS", f"{name} must be a UUID") from exc
        if value != normalized:
            raise AgentError("INVALID_PARAMS", f"{name} must be a canonical UUID")
        return
    if kind == "scope":
        if not isinstance(value, str) or not _SAFE_NAME.fullmatch(value):
            raise AgentError("INVALID_PARAMS", f"{name} contains unsupported characters")
        return
    if kind == "namespace":
        if not isinstance(value, str) or (value and not _SAFE_NAME.fullmatch(value)):
            raise AgentError("INVALID_PARAMS", f"{name} contains unsupported characters")
        return
    if kind == "image_id":
        if not isinstance(value, str) or not _IMAGE_ID.fullmatch(value):
            raise AgentError("INVALID_PARAMS", f"{name} must be a lowercase hex image ID")
        return
    if kind in {"positive_int", "device_number"}:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AgentError("INVALID_PARAMS", f"{name} must be an integer")
        lower = 1 if kind == "positive_int" else 0
        if value < lower or value > (2**63 - 1):
            raise AgentError("INVALID_PARAMS", f"{name} is outside the supported range")
        return
    raise RuntimeError(f"Unknown protocol field kind: {kind}")


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
