from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from ...platform.config import ConfigSnapshot


WORKFLOW_TYPES = frozenset(
    {"UPGRADE_PRODUCTION", "QOS_OBSERVER", "LAB_TEST", "ROLLBACK", "LEGACY"}
)


class SessionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        observed_state: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.observed_state = observed_state or {}


@dataclass(frozen=True)
class CreateSessionCommand:
    name: str
    workflow_types: tuple[str, ...]


class SessionRepository(Protocol):
    def create(
        self,
        *,
        session_id: UUID,
        command: CreateSessionCommand,
        snapshot: ConfigSnapshot,
        actual_fsid: str,
        execution_environment: str,
        capabilities: dict,
    ) -> dict: ...

    def get(self, session_id: UUID) -> dict | None: ...
