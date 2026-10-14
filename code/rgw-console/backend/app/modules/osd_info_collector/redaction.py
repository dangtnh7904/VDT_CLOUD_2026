from __future__ import annotations

import re
from typing import Any

from ...services.idempotency import redact_sensitive_data


_SENSITIVE_OPTION = re.compile(
    r"(^|[_-])(authorization|password|passwd|secret|secret_key|access_key|credential|keyring|token|private_key)([_-]|$)",
    re.IGNORECASE,
)
_VALUE_FIELDS = {"value", "raw_value", "default", "effective_value"}
_SENSITIVE_FLAGS = {"--conf", "--key", "--keyring", "--secret", "--token", "--access-key", "--secret-key"}


def _redact_argv(values: list[Any]) -> list[Any]:
    result = list(values)
    redact_next = False
    for index, value in enumerate(result):
        if redact_next:
            result[index] = "[REDACTED]"
            redact_next = False
            continue
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if lowered in _SENSITIVE_FLAGS:
            redact_next = True
            continue
        for flag in _SENSITIVE_FLAGS:
            if lowered.startswith(f"{flag}="):
                result[index] = f"{value.split('=', 1)[0]}=[REDACTED]"
                break
    return result


def _redact_config_rows(value: Any) -> Any:
    if isinstance(value, list):
        return [_redact_config_rows(item) for item in value]
    if not isinstance(value, dict):
        return value

    result = {key: _redact_config_rows(item) for key, item in value.items()}
    option_name = next(
        (
            item
            for key in ("name", "key", "option")
            if isinstance((item := result.get(key)), str)
        ),
        None,
    )
    if option_name and _SENSITIVE_OPTION.search(option_name):
        for key in _VALUE_FIELDS:
            if key in result:
                result[key] = "[REDACTED]"
    for key in ("argv", "command"):
        if isinstance(result.get(key), list):
            result[key] = _redact_argv(result[key])
    return result


def redact_collector_evidence(value: Any) -> Any:
    """Return a response-safe copy without changing the immutable artifact."""

    return _redact_config_rows(redact_sensitive_data(value))
