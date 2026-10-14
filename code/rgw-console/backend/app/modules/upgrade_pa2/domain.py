"""Pure PA2 state reconciliation and safety rules.

The state machine consumes observed cluster evidence.  A successful command
return code is intentionally not an input: transitions are based on current
membership, placement and health observations so pause/resume can safely
reconcile work after a process restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Pa2State(str, Enum):
    WAVE_PLANNED = "WAVE_PLANNED"
    CHAIN_READY = "CHAIN_READY"
    SPARE_CANDIDATE = "SPARE_CANDIDATE"
    SPARE_ADMISSION_ALLOWED = "SPARE_ADMISSION_ALLOWED"
    HANDOFF_GROUP_CONVERGING = "HANDOFF_GROUP_CONVERGING"
    HANDOFF_GROUP_SCRUBBING = "HANDOFF_GROUP_SCRUBBING"
    HANDOFF_GROUP_ACCEPTED = "HANDOFF_GROUP_ACCEPTED"
    HANDOFF_COMPLETE = "HANDOFF_COMPLETE"
    SOURCE_UPGRADING = "SOURCE_UPGRADING"
    SPARE_ROTATED = "SPARE_ROTATED"
    WAVE_RECONCILING = "WAVE_RECONCILING"
    WAVE_STABILIZING = "WAVE_STABILIZING"
    WAVE_COMPLETE = "WAVE_COMPLETE"


class Pa2Decision(str, Enum):
    ADVANCE = "ADVANCE"
    WAIT = "WAIT"
    HOLD = "HOLD"
    COMPLETE = "COMPLETE"
    NOT_EXERCISED = "NOT_EXERCISED"


@dataclass(frozen=True)
class Pa2Transition:
    decision: Pa2Decision
    current_state: Pa2State
    next_state: Pa2State
    reason_code: str
    detail: str


@dataclass(frozen=True)
class ReplicaCheck:
    """Accepted result from the shared replica validation boundary."""

    pg_id: str
    accepted: bool
    conclusive: bool = True
    mapping_unchanged: bool = True


@dataclass(frozen=True)
class Pa2Evidence:
    """Observed evidence for exactly one reconciliation decision."""

    chain_conflict: bool = False
    dependency_required_by_other_work: bool = False

    destination_reserved: bool = False
    destination_healthy: bool = False
    destination_correct_digest: bool = False
    destination_isolated: bool = False
    failure_domain_distinct: bool = False
    down_set_safe: bool = False
    lease_owned: bool = False

    destination_admitted: bool = False
    mapping_converged: bool = False
    replica_checks: tuple[ReplicaCheck, ...] = ()
    remaining_handoff_groups: int = 0

    source_absent_from_up: bool = False
    source_absent_from_acting: bool = False
    destination_membership_matches: bool = False

    source_redeployed: bool = False
    source_healthy: bool = False
    source_correct_digest: bool = False
    source_isolated: bool = False
    source_has_new_incarnation: bool = False
    remaining_rotations: int = 0

    end_state_reconciled: bool = False
    version_coverage_complete: bool = False
    ownership_resolved: bool = False
    stable_window_started: bool = False
    stable_window_met: bool = False
    ledger_clean: bool = False


class Pa2StateMachine:
    """Compute one PA2 transition from durable state and fresh observations."""

    @staticmethod
    def evaluate(state: Pa2State, evidence: Pa2Evidence) -> Pa2Transition:
        if evidence.chain_conflict:
            return _hold(state, "CHAIN_CONFLICT", "spare chain ownership conflicts with another wave")
        if evidence.dependency_required_by_other_work:
            return _hold(
                state,
                "DEPENDENCY_STILL_REQUIRED",
                "cleanup or rotation would remove a dependency still used by another chain",
            )

        if state is Pa2State.WAVE_PLANNED:
            required = (
                evidence.destination_reserved,
                evidence.failure_domain_distinct,
                evidence.down_set_safe,
                evidence.lease_owned,
            )
            if not all(required):
                return _hold(
                    state,
                    "CHAIN_NOT_SAFE",
                    "reservation, failure-domain, down-set and lease checks must all pass",
                )
            return _advance(state, Pa2State.CHAIN_READY, "CHAIN_READY")

        if state is Pa2State.CHAIN_READY:
            if not evidence.destination_reserved:
                return _hold(state, "SPARE_NOT_RESERVED", "destination is not reserved for this wave")
            if not evidence.destination_healthy:
                return _hold(state, "SPARE_UNHEALTHY", "destination health checks have not passed")
            if not evidence.destination_correct_digest:
                return _hold(state, "SPARE_DIGEST_MISMATCH", "destination does not run the expected image digest")
            if not evidence.destination_isolated:
                return _hold(state, "SPARE_NOT_ISOLATED", "destination still serves production traffic")
            return _advance(state, Pa2State.SPARE_CANDIDATE, "SPARE_VALIDATED")

        if state is Pa2State.SPARE_CANDIDATE:
            if not (evidence.failure_domain_distinct and evidence.down_set_safe and evidence.lease_owned):
                return _hold(
                    state,
                    "ADMISSION_BLOCKED",
                    "failure-domain, down-set and current lease evidence are required",
                )
            return _advance(state, Pa2State.SPARE_ADMISSION_ALLOWED, "ADMISSION_ALLOWED")

        if state is Pa2State.SPARE_ADMISSION_ALLOWED:
            if not evidence.destination_admitted:
                return _wait(state, "ADMISSION_NOT_OBSERVED", "destination is not yet present in observed membership")
            return _advance(state, Pa2State.HANDOFF_GROUP_CONVERGING, "ADMISSION_OBSERVED")

        if state is Pa2State.HANDOFF_GROUP_CONVERGING:
            if not evidence.mapping_converged:
                return _wait(state, "MAPPING_CONVERGING", "handoff group mapping has not converged")
            return _advance(state, Pa2State.HANDOFF_GROUP_SCRUBBING, "MAPPING_CONVERGED")

        if state is Pa2State.HANDOFF_GROUP_SCRUBBING:
            check = _replica_check_result(evidence.replica_checks)
            if check is not None:
                return Pa2Transition(check[0], state, state, check[1], check[2])
            return _advance(state, Pa2State.HANDOFF_GROUP_ACCEPTED, "GROUP_ACCEPTED")

        if state is Pa2State.HANDOFF_GROUP_ACCEPTED:
            if evidence.remaining_handoff_groups < 0:
                return _hold(state, "INVALID_GROUP_COUNT", "remaining handoff group count cannot be negative")
            if evidence.remaining_handoff_groups > 0:
                return _advance(state, Pa2State.SPARE_ADMISSION_ALLOWED, "NEXT_HANDOFF_GROUP")
            if not (
                evidence.source_absent_from_up
                and evidence.source_absent_from_acting
                and evidence.destination_membership_matches
            ):
                return _hold(
                    state,
                    "HANDOFF_SCOPE_INCOMPLETE",
                    "source must be absent from every up/acting set and destination membership must match",
                )
            return _advance(state, Pa2State.HANDOFF_COMPLETE, "HANDOFF_COMPLETE")

        if state is Pa2State.HANDOFF_COMPLETE:
            if not (evidence.source_absent_from_up and evidence.source_absent_from_acting):
                return _hold(
                    state,
                    "SOURCE_STILL_MAPPED",
                    "source upgrade is blocked while the source remains in any up or acting set",
                )
            return _advance(state, Pa2State.SOURCE_UPGRADING, "SOURCE_UPGRADE_ALLOWED")

        if state is Pa2State.SOURCE_UPGRADING:
            source_ready = (
                evidence.source_redeployed
                and evidence.source_healthy
                and evidence.source_correct_digest
                and evidence.source_isolated
                and evidence.source_has_new_incarnation
            )
            if not source_ready:
                return _wait(
                    state,
                    "SOURCE_NOT_RECONCILED",
                    "redeployed source needs health, digest, isolation and new-incarnation evidence",
                )
            return _advance(state, Pa2State.SPARE_ROTATED, "SOURCE_REJOINED_AS_SPARE")

        if state is Pa2State.SPARE_ROTATED:
            if evidence.remaining_rotations < 0:
                return _hold(state, "INVALID_ROTATION_COUNT", "remaining rotation count cannot be negative")
            if evidence.remaining_rotations > 0:
                return _advance(state, Pa2State.CHAIN_READY, "NEXT_ROTATION")
            return _advance(state, Pa2State.WAVE_RECONCILING, "ROTATIONS_COMPLETE")

        if state is Pa2State.WAVE_RECONCILING:
            if not (
                evidence.end_state_reconciled
                and evidence.version_coverage_complete
                and evidence.ownership_resolved
            ):
                return _hold(
                    state,
                    "END_STATE_UNRESOLVED",
                    "selected end state, version coverage and ownership must reconcile",
                )
            return _advance(state, Pa2State.WAVE_STABILIZING, "WAVE_RECONCILED")

        if state is Pa2State.WAVE_STABILIZING:
            if not evidence.stable_window_started:
                return _wait(state, "STABILITY_WINDOW_NOT_STARTED", "stability window has not started")
            if not evidence.stable_window_met:
                return _wait(state, "STABILITY_WINDOW_ACTIVE", "stability window is still active")
            if not evidence.ledger_clean:
                return _hold(state, "LEDGER_NOT_CLEAN", "unresolved PA2 ledger entries remain")
            return Pa2Transition(
                Pa2Decision.COMPLETE,
                state,
                Pa2State.WAVE_COMPLETE,
                "WAVE_COMPLETE",
                "wave reconciled and stability window passed",
            )

        return Pa2Transition(
            Pa2Decision.COMPLETE,
            state,
            Pa2State.WAVE_COMPLETE,
            "ALREADY_COMPLETE",
            "wave is already complete",
        )


@dataclass(frozen=True)
class ResumeEvidence:
    current_mapping_available: bool
    lease_valid: bool
    ledger_consistent: bool
    prior_actions_reconciled: bool


def evaluate_resume(state: Pa2State, evidence: ResumeEvidence) -> Pa2Transition:
    """Fail closed unless a resumed worker can reconstruct actual state."""

    if not evidence.current_mapping_available:
        return _hold(state, "CURRENT_MAPPING_UNAVAILABLE", "resume requires a fresh mapping snapshot")
    if not evidence.lease_valid:
        return _hold(state, "LEASE_LOST", "resume requires a current lease generation")
    if not evidence.ledger_consistent:
        return _hold(state, "LEDGER_DIVERGED", "durable ledger and observed cluster state disagree")
    if not evidence.prior_actions_reconciled:
        return _wait(state, "ACTION_OUTCOME_UNKNOWN", "prior action outcomes must be reconciled")
    return Pa2Transition(Pa2Decision.ADVANCE, state, state, "RESUME_RECONCILED", "resume is safe")


@dataclass(frozen=True)
class FinalSpareAssessment:
    decision: Pa2Decision
    reason_code: str
    detail: str


def assess_final_spare(received_pg: bool, replica_checks: Iterable[ReplicaCheck]) -> FinalSpareAssessment:
    """Report final-spare coverage without turning no-placement into a false pass."""

    checks = tuple(replica_checks)
    if not received_pg:
        return FinalSpareAssessment(
            Pa2Decision.NOT_EXERCISED,
            "FINAL_SPARE_NOT_EXERCISED",
            "the final spare did not receive a placement group during this run",
        )
    check = _replica_check_result(checks)
    if check is not None:
        return FinalSpareAssessment(check[0], check[1], check[2])
    return FinalSpareAssessment(Pa2Decision.COMPLETE, "FINAL_SPARE_VALIDATED", "final spare replica checks passed")


def select_recovery_mapping(current_mapping: tuple[str, ...]) -> tuple[str, ...]:
    """Recovery must use current authoritative mapping, never a stale planned list."""

    normalized = tuple(dict.fromkeys(item.strip() for item in current_mapping if item.strip()))
    if not normalized:
        raise ValueError("current mapping is required for recovery")
    return normalized


def _replica_check_result(
    checks: tuple[ReplicaCheck, ...],
) -> tuple[Pa2Decision, str, str] | None:
    if not checks:
        return (Pa2Decision.WAIT, "REPLICA_CHECKS_MISSING", "replica checks have not completed")
    if any(not item.conclusive for item in checks):
        return (Pa2Decision.WAIT, "REPLICA_CHECK_INCONCLUSIVE", "at least one replica check is inconclusive")
    if any(not item.mapping_unchanged for item in checks):
        return (Pa2Decision.HOLD, "MAPPING_CHANGED_DURING_CHECK", "mapping changed during replica validation")
    if any(not item.accepted for item in checks):
        return (Pa2Decision.HOLD, "REPLICA_CHECK_FAILED", "at least one replica check failed")
    return None


def _advance(state: Pa2State, next_state: Pa2State, code: str) -> Pa2Transition:
    return Pa2Transition(Pa2Decision.ADVANCE, state, next_state, code, code.replace("_", " ").lower())


def _wait(state: Pa2State, code: str, detail: str) -> Pa2Transition:
    return Pa2Transition(Pa2Decision.WAIT, state, state, code, detail)


def _hold(state: Pa2State, code: str, detail: str) -> Pa2Transition:
    return Pa2Transition(Pa2Decision.HOLD, state, state, code, detail)
