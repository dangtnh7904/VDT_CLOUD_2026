from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class LeaseConflict(RuntimeError):
    def __init__(self, message: str, *, observed_owner: UUID | None = None) -> None:
        super().__init__(message)
        self.code = "LEASE_CONFLICT"
        self.message = message
        self.observed_owner = observed_owner


@dataclass(frozen=True)
class LeaseToken:
    cluster_id: str
    resource_type: str
    resource_id: str
    owner_run_id: UUID
    generation: int
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.cluster_id or not self.resource_type or not self.resource_id:
            raise ValueError("lease resource identity must be non-empty")
        if self.generation < 1:
            raise ValueError("lease generation must be positive")
        if self.expires_at.tzinfo is None:
            raise ValueError("lease expiry must include a timezone")
