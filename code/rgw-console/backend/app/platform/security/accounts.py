"""Bounded, file-only console accounts for authenticated read-only deployments."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .passwords import validate_password_hash


ConsoleRole = Literal["viewer", "operator", "admin"]
MAX_ACCOUNTS_FILE_BYTES = 65_536
MAX_ACCOUNTS = 128
USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$"


class ConsoleAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    username: str = Field(pattern=USERNAME_PATTERN)
    role: ConsoleRole
    password_hash: SecretStr = Field(repr=False)

    @field_validator("password_hash")
    @classmethod
    def secure_hash(cls, value: SecretStr) -> SecretStr:
        validate_password_hash(value.get_secret_value())
        return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate account JSON property")
        result[key] = value
    return result


def load_console_accounts(path: Path) -> dict[str, ConsoleAccount]:
    """Reject malformed records without including credential contents in errors.

    Account files are loaded at settings construction. Restart services after
    rotating the file so every worker enforces the same account revision.
    """

    try:
        with path.open("rb") as source:
            content = source.read(MAX_ACCOUNTS_FILE_BYTES + 1)
        if len(content) > MAX_ACCOUNTS_FILE_BYTES:
            raise ValueError
        document = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
        if (
            not isinstance(document, dict)
            or set(document) != {"version", "users"}
            or type(document["version"]) is not int
            or document["version"] != 1
            or not isinstance(document["users"], list)
            or not 1 <= len(document["users"]) <= MAX_ACCOUNTS
        ):
            raise ValueError
        accounts = {}
        for record in document["users"]:
            account = ConsoleAccount.model_validate(record)
            if not re.fullmatch(USERNAME_PATTERN, account.username) or account.username in accounts:
                raise ValueError
            accounts[account.username] = account
        return accounts
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        raise ValueError("CONSOLE_AUTH_USERS_FILE must contain valid, unique version 1 console accounts") from None
