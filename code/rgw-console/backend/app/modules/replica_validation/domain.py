from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..upgrade_common.domain import DomainResult


@dataclass(frozen=True)
class MappingObservation:
    pgid: str
    up: tuple[int, ...]
    acting: tuple[int, ...]
    actual_primary: int | None
    interval_id: str
    source_incarnation: str
    target_incarnation: str
    active: bool
    clean: bool
    observed_at: datetime
    fresh: bool

    @property
    def fingerprint(self) -> str:
        return "|".join(
            (
                self.pgid,
                ",".join(map(str, self.up)),
                ",".join(map(str, self.acting)),
                str(self.actual_primary),
                self.interval_id,
                self.source_incarnation,
                self.target_incarnation,
            )
        )


@dataclass(frozen=True)
class ScrubObservation:
    requested_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    result_clean: bool | None
    mapping_fingerprint: str | None
    inconsistency_count: int | None
    io_error_count: int | None
    repair_event_count: int | None
    fresh: bool


@dataclass(frozen=True)
class ReplicaValidationInput:
    target_osd: int
    expected_role: str
    convergence_observed_at: datetime | None
    mapping: MappingObservation
    scrub: ScrubObservation
    target_allowed_for_pgid: bool


@dataclass(frozen=True)
class ReplicaCheckDecision:
    result: DomainResult
    code: str
    reasons: tuple[str, ...]
    mapping_fingerprint: str


def validate_replica(value: ReplicaValidationInput) -> ReplicaCheckDecision:
    reasons: list[str] = []
    mapping = value.mapping
    scrub = value.scrub
    if value.expected_role != "REPLICA":
        return ReplicaCheckDecision(
            DomainResult.UNSUPPORTED,
            "ROLE_UNSUPPORTED",
            ("production checker only accepts an expected REPLICA role before restore",),
            mapping.fingerprint,
        )
    if not mapping.fresh or not scrub.fresh:
        reasons.append("EVIDENCE_STALE")
    if not value.target_allowed_for_pgid:
        reasons.append("ADMISSION_BROKEN")
    if value.target_osd not in mapping.up or value.target_osd not in mapping.acting:
        reasons.append("TARGET_NOT_IN_ACTUAL_UP_AND_ACTING")
    if mapping.actual_primary == value.target_osd:
        reasons.append("UNEXPECTED_PRIMARY")
    if not mapping.active or not mapping.clean:
        reasons.append("PG_NOT_ACTIVE_CLEAN")
    if value.convergence_observed_at is None:
        reasons.append("CONVERGENCE_MARKER_MISSING")
    if scrub.requested_at is None:
        reasons.append("SCRUB_REQUEST_MISSING")
    elif value.convergence_observed_at is not None and scrub.requested_at <= value.convergence_observed_at:
        reasons.append("SCRUB_NOT_NEW_AFTER_CONVERGENCE")
    if scrub.started_at is None or scrub.completed_at is None:
        reasons.append("SCRUB_COMPLETION_MISSING")
    elif scrub.completed_at < scrub.started_at:
        reasons.append("SCRUB_TIME_INVALID")
    elif scrub.requested_at is not None and (
        scrub.started_at < scrub.requested_at or scrub.completed_at < scrub.requested_at
    ):
        reasons.append("SCRUB_TIME_INVALID")
    if scrub.mapping_fingerprint != mapping.fingerprint:
        reasons.append("MAPPING_CHANGED_AFTER_SCRUB")
    if scrub.result_clean is not True:
        reasons.append("SCRUB_RESULT_NOT_CLEAN")
    for name, count in (
        ("INCONSISTENCY_DETECTED", scrub.inconsistency_count),
        ("IO_ERROR_DETECTED", scrub.io_error_count),
        ("REPAIR_EVENT_DETECTED", scrub.repair_event_count),
    ):
        if count is None:
            reasons.append(f"{name}_COUNT_UNKNOWN")
        elif count > 0:
            reasons.append(name)

    unique = tuple(sorted(set(reasons)))
    if not unique:
        return ReplicaCheckDecision(
            DomainResult.PASS,
            "REPLICA_ACCEPTED",
            (),
            mapping.fingerprint,
        )
    hold_reasons = {
        "ADMISSION_BROKEN",
        "UNEXPECTED_PRIMARY",
        "INCONSISTENCY_DETECTED",
        "IO_ERROR_DETECTED",
        "REPAIR_EVENT_DETECTED",
        "SCRUB_RESULT_NOT_CLEAN",
    }
    result = (
        DomainResult.HOLD
        if any(reason in hold_reasons for reason in unique)
        else DomainResult.INCONCLUSIVE
    )
    return ReplicaCheckDecision(result, unique[0], unique, mapping.fingerprint)
