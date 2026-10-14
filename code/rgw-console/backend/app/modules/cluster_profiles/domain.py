from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CapabilityState(str, Enum):
    SUPPORTED = "SUPPORTED"
    DEGRADED = "DEGRADED"
    FALLBACK_LOG_EVIDENCE = "FALLBACK_LOG_EVIDENCE"
    DISABLED = "DISABLED"
    STALE = "STALE"
    UNSUPPORTED = "UNSUPPORTED"


class ObservationQuality(str, Enum):
    VALID = "VALID"
    STALE = "STALE"
    GAP = "GAP"
    UNSUPPORTED = "UNSUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class ClusterIdentity:
    cluster_id: str
    expected_fsid: str
    actual_fsid: str
    observed_at: str


@dataclass(frozen=True)
class CapabilityObservation:
    name: str
    state: CapabilityState
    evidence: dict[str, Any]


class ClusterReadError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        observed_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.observed_state = observed_state or {}
