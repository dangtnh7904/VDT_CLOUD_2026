from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..replica_validation.domain import ReplicaCheckDecision
from ..upgrade_common.domain import DomainResult


class Pa1State(str, Enum):
    CREATED = "CREATED"
    PREFLIGHT_READY = "PREFLIGHT_READY"
    BASELINE_READY = "BASELINE_READY"
    DRAINING = "DRAINING"
    DRAINED = "DRAINED"
    MAINTENANCE_APPROVED = "MAINTENANCE_APPROVED"
    UPGRADING = "UPGRADING"
    DAEMON_READY = "DAEMON_READY"
    REPLICA_RETURN = "REPLICA_RETURN"
    REPLICA_CONVERGING = "REPLICA_CONVERGING"
    REPLICA_SCRUBBING = "REPLICA_SCRUBBING"
    REPLICA_ACCEPTED = "REPLICA_ACCEPTED"
    PRIMARY_RESTORE_READY = "PRIMARY_RESTORE_READY"
    PRIMARY_RESTORED = "PRIMARY_RESTORED"
    RESTORING = "RESTORING"
    STABILIZING = "STABILIZING"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class Pa1Evidence:
    preflight_result: DomainResult | None = None
    baseline_valid: bool | None = None
    drain_observed: bool | None = None
    source_absent_from_up: bool | None = None
    source_absent_from_acting: bool | None = None
    maintenance_gate_result: DomainResult | None = None
    redeploy_observed: bool | None = None
    daemon_up: bool | None = None
    daemon_in: bool | None = None
    version_matches: bool | None = None
    digest_matches: bool | None = None
    incarnation_matches: bool | None = None
    target_still_isolated: bool | None = None
    return_admission_observed: bool | None = None
    mapping_converging_observed: bool | None = None
    group_mapping_converged: bool | None = None
    unexpected_primary: bool = False
    admission_broken: bool = False
    replica_checks: tuple[ReplicaCheckDecision, ...] = field(default_factory=tuple)
    remaining_return_groups: int | None = None
    restore_observed: bool | None = None
    restore_data_movement_active: bool | None = None
    stable_window_started: bool | None = None
    stable_window_met: bool | None = None
    ledger_clean: bool | None = None


@dataclass(frozen=True)
class Pa1TransitionDecision:
    result: DomainResult
    current_state: Pa1State
    next_state: Pa1State
    code: str
    reasons: tuple[str, ...] = ()


class Pa1StateMachine:
    """Pure actual-state PA1 transition evaluator.

    Command return codes are intentionally absent from the evidence model.
    Callers must reconcile commands into observed cluster state first.
    """

    def evaluate(self, state: Pa1State, evidence: Pa1Evidence) -> Pa1TransitionDecision:
        if state is Pa1State.COMPLETE:
            return self._pass(state, state, "ALREADY_COMPLETE")
        if evidence.admission_broken:
            return self._stop(state, DomainResult.HOLD, "HOLD_ADMISSION_BROKEN")
        if evidence.unexpected_primary:
            return self._stop(state, DomainResult.HOLD, "HOLD_UNEXPECTED_PRIMARY")

        if state is Pa1State.CREATED:
            if evidence.preflight_result is DomainResult.PASS:
                return self._pass(state, Pa1State.PREFLIGHT_READY, "PREFLIGHT_READY")
            return self._from_gate(state, evidence.preflight_result, "PREFLIGHT_NOT_READY")
        if state is Pa1State.PREFLIGHT_READY:
            return self._bool(state, evidence.baseline_valid, Pa1State.BASELINE_READY, "BASELINE_READY")
        if state is Pa1State.BASELINE_READY:
            return self._bool(state, evidence.drain_observed, Pa1State.DRAINING, "DRAINING_OBSERVED")
        if state is Pa1State.DRAINING:
            if evidence.source_absent_from_up is True and evidence.source_absent_from_acting is True:
                return self._pass(state, Pa1State.DRAINED, "SOURCE_ISOLATED")
            reasons = []
            if evidence.source_absent_from_up is not True:
                reasons.append("SOURCE_PRESENT_OR_UNKNOWN_IN_UP")
            if evidence.source_absent_from_acting is not True:
                reasons.append("SOURCE_PRESENT_OR_UNKNOWN_IN_ACTING")
            return self._wait(state, "ISOLATION_INCOMPLETE", *reasons)
        if state is Pa1State.DRAINED:
            if evidence.maintenance_gate_result is DomainResult.PASS:
                return self._pass(state, Pa1State.MAINTENANCE_APPROVED, "MAINTENANCE_APPROVED")
            return self._from_gate(state, evidence.maintenance_gate_result, "MAINTENANCE_GATE_FAILED")
        if state is Pa1State.MAINTENANCE_APPROVED:
            return self._bool(state, evidence.redeploy_observed, Pa1State.UPGRADING, "REDEPLOY_OBSERVED")
        if state is Pa1State.UPGRADING:
            checks = {
                "DAEMON_NOT_UP": evidence.daemon_up,
                "DAEMON_NOT_IN": evidence.daemon_in,
                "VERSION_MISMATCH": evidence.version_matches,
                "DIGEST_MISMATCH": evidence.digest_matches,
                "INCARNATION_MISMATCH": evidence.incarnation_matches,
                "ISOLATION_BROKEN": evidence.target_still_isolated,
            }
            failed = tuple(name for name, value in checks.items() if value is False)
            unknown = tuple(name.replace("NOT_", "") + "_UNKNOWN" for name, value in checks.items() if value is None)
            if failed:
                return self._stop(state, DomainResult.HOLD, failed[0], *failed)
            if unknown:
                return self._wait(state, "DAEMON_EVIDENCE_INCOMPLETE", *unknown)
            return self._pass(state, Pa1State.DAEMON_READY, "DAEMON_READY")
        if state is Pa1State.DAEMON_READY:
            return self._bool(
                state,
                evidence.return_admission_observed,
                Pa1State.REPLICA_RETURN,
                "RETURN_ADMISSION_OBSERVED",
            )
        if state is Pa1State.REPLICA_RETURN:
            return self._bool(
                state,
                evidence.mapping_converging_observed,
                Pa1State.REPLICA_CONVERGING,
                "REPLICA_CONVERGING",
            )
        if state is Pa1State.REPLICA_CONVERGING:
            return self._bool(
                state,
                evidence.group_mapping_converged,
                Pa1State.REPLICA_SCRUBBING,
                "GROUP_MAPPING_CONVERGED",
            )
        if state is Pa1State.REPLICA_SCRUBBING:
            if not evidence.replica_checks:
                return self._wait(state, "SCRUB_EVIDENCE_INCOMPLETE", "NO_REPLICA_CHECKS")
            non_pass = tuple(check for check in evidence.replica_checks if check.result is not DomainResult.PASS)
            if non_pass:
                result = DomainResult.HOLD if any(check.result is DomainResult.HOLD for check in non_pass) else DomainResult.INCONCLUSIVE
                reasons = tuple(sorted({reason for check in non_pass for reason in check.reasons}))
                return self._stop(state, result, non_pass[0].code, *reasons)
            return self._pass(state, Pa1State.REPLICA_ACCEPTED, "RETURN_GROUP_ACCEPTED")
        if state is Pa1State.REPLICA_ACCEPTED:
            if evidence.remaining_return_groups is None:
                return self._wait(state, "RETURN_GROUP_COUNT_UNKNOWN")
            if evidence.remaining_return_groups < 0:
                return self._stop(state, DomainResult.BLOCKED, "RETURN_GROUP_COUNT_INVALID")
            if evidence.remaining_return_groups > 0:
                return self._pass(state, Pa1State.REPLICA_RETURN, "NEXT_RETURN_GROUP")
            return self._pass(state, Pa1State.PRIMARY_RESTORE_READY, "ALL_RETURN_GROUPS_ACCEPTED")
        if state is Pa1State.PRIMARY_RESTORE_READY:
            return self._bool(
                state,
                evidence.restore_observed,
                Pa1State.PRIMARY_RESTORED,
                "RESTORE_OBSERVED",
            )
        if state is Pa1State.PRIMARY_RESTORED:
            if evidence.restore_data_movement_active is None:
                return self._wait(state, "RESTORE_MOVEMENT_UNKNOWN")
            return self._pass(state, Pa1State.RESTORING, "RESTORE_RECONCILING")
        if state is Pa1State.RESTORING:
            return self._bool(
                state,
                evidence.stable_window_started,
                Pa1State.STABILIZING,
                "STABLE_WINDOW_STARTED",
            )
        if state is Pa1State.STABILIZING:
            if evidence.stable_window_met is True and evidence.ledger_clean is True:
                return self._pass(state, Pa1State.COMPLETE, "PA1_COMPLETE")
            reasons = []
            if evidence.stable_window_met is not True:
                reasons.append("STABLE_WINDOW_NOT_MET")
            if evidence.ledger_clean is not True:
                reasons.append("LEDGER_NOT_CLEAN")
            return self._wait(state, "STABILIZATION_INCOMPLETE", *reasons)
        return self._stop(state, DomainResult.BLOCKED, "STATE_UNSUPPORTED")

    @staticmethod
    def _pass(current: Pa1State, next_state: Pa1State, code: str) -> Pa1TransitionDecision:
        return Pa1TransitionDecision(DomainResult.PASS, current, next_state, code)

    @staticmethod
    def _wait(current: Pa1State, code: str, *reasons: str) -> Pa1TransitionDecision:
        return Pa1TransitionDecision(DomainResult.INCONCLUSIVE, current, current, code, tuple(reasons))

    @staticmethod
    def _stop(
        current: Pa1State,
        result: DomainResult,
        code: str,
        *reasons: str,
    ) -> Pa1TransitionDecision:
        return Pa1TransitionDecision(result, current, current, code, tuple(reasons))

    def _bool(
        self,
        current: Pa1State,
        value: bool | None,
        next_state: Pa1State,
        code: str,
    ) -> Pa1TransitionDecision:
        if value is True:
            return self._pass(current, next_state, code)
        if value is False:
            return self._stop(current, DomainResult.HOLD, f"{code}_CONTRADICTED")
        return self._wait(current, f"{code}_NOT_OBSERVED")

    def _from_gate(
        self,
        current: Pa1State,
        result: DomainResult | None,
        code: str,
    ) -> Pa1TransitionDecision:
        if result is None:
            return self._wait(current, f"{code}_MISSING")
        if result is DomainResult.PASS:
            raise AssertionError("PASS gate must be handled by the caller")
        return self._stop(current, result, code)
