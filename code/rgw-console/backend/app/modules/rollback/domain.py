from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..upgrade_common.domain import DomainResult


class RollbackState(str, Enum):
    HOLD = "HOLD"
    CONTAINED = "CONTAINED"
    SOURCES_READY = "SOURCES_READY"
    SAFE_TO_REMOVE = "SAFE_TO_REMOVE"
    R_PROVISIONED = "R_PROVISIONED"
    R_REBUILT = "R_REBUILT"
    ROLLBACK_COMPLETE = "ROLLBACK_COMPLETE"


@dataclass(frozen=True)
class RollbackEvidence:
    target_fenced: bool | None = None
    target_absent_from_up: bool | None = None
    target_absent_from_acting: bool | None = None
    current_sources_known: bool | None = None
    current_sources_healthy: bool | None = None
    safe_to_destroy: bool | None = None
    ok_to_stop: bool | None = None
    replacement_device_clean: bool | None = None
    replacement_incarnation_new: bool | None = None
    old_binary_compatible_with_device: bool | None = None
    service_spec_pinned: bool | None = None
    replacement_provisioned: bool | None = None
    rebuild_complete: bool | None = None
    rebuild_clean: bool | None = None
    stable_window_met: bool | None = None
    ledger_clean: bool | None = None


@dataclass(frozen=True)
class RollbackTransitionDecision:
    result: DomainResult
    current_state: RollbackState
    next_state: RollbackState
    code: str
    reasons: tuple[str, ...] = ()


class RollbackStateMachine:
    def evaluate(
        self,
        state: RollbackState,
        evidence: RollbackEvidence,
    ) -> RollbackTransitionDecision:
        if state is RollbackState.ROLLBACK_COMPLETE:
            return self._pass(state, state, "ALREADY_COMPLETE")
        if evidence.old_binary_compatible_with_device is False:
            return self._stop(
                state,
                DomainResult.BLOCKED,
                "ROLLBACK_VERSION_INCOMPATIBLE",
                "OLD_BINARY_MUST_NOT_OPEN_UPGRADED_BLUESTORE",
            )
        if state is RollbackState.HOLD:
            checks = {
                "TARGET_NOT_FENCED": evidence.target_fenced,
                "TARGET_PRESENT_OR_UNKNOWN_IN_UP": evidence.target_absent_from_up,
                "TARGET_PRESENT_OR_UNKNOWN_IN_ACTING": evidence.target_absent_from_acting,
            }
            return self._all_true(state, checks, RollbackState.CONTAINED, "TARGET_CONTAINED")
        if state is RollbackState.CONTAINED:
            checks = {
                "CURRENT_SOURCES_UNKNOWN": evidence.current_sources_known,
                "CURRENT_SOURCES_NOT_HEALTHY": evidence.current_sources_healthy,
            }
            return self._all_true(state, checks, RollbackState.SOURCES_READY, "SOURCES_READY")
        if state is RollbackState.SOURCES_READY:
            if evidence.safe_to_destroy is True:
                return self._pass(state, RollbackState.SAFE_TO_REMOVE, "SAFE_TO_REMOVE")
            if evidence.safe_to_destroy is False:
                return self._stop(state, DomainResult.HOLD, "SAFE_TO_DESTROY_FAILED")
            if evidence.ok_to_stop is True:
                return self._stop(
                    state,
                    DomainResult.INCONCLUSIVE,
                    "SAFE_TO_DESTROY_MISSING",
                    "OK_TO_STOP_IS_NOT_SAFE_TO_DESTROY",
                )
            return self._stop(state, DomainResult.INCONCLUSIVE, "REMOVAL_EVIDENCE_MISSING")
        if state is RollbackState.SAFE_TO_REMOVE:
            checks = {
                "REPLACEMENT_DEVICE_NOT_CLEAN": evidence.replacement_device_clean,
                "REPLACEMENT_INCARNATION_NOT_NEW": evidence.replacement_incarnation_new,
                "ROLLBACK_VERSION_COMPATIBILITY_UNKNOWN": evidence.old_binary_compatible_with_device,
                "SERVICE_SPEC_NOT_PINNED": evidence.service_spec_pinned,
                "REPLACEMENT_NOT_PROVISIONED": evidence.replacement_provisioned,
            }
            return self._all_true(state, checks, RollbackState.R_PROVISIONED, "REPLACEMENT_PROVISIONED")
        if state is RollbackState.R_PROVISIONED:
            checks = {
                "REBUILD_INCOMPLETE": evidence.rebuild_complete,
                "REBUILD_NOT_CLEAN": evidence.rebuild_clean,
            }
            return self._all_true(state, checks, RollbackState.R_REBUILT, "REBUILD_COMPLETE")
        if state is RollbackState.R_REBUILT:
            checks = {
                "STABLE_WINDOW_NOT_MET": evidence.stable_window_met,
                "LEDGER_NOT_CLEAN": evidence.ledger_clean,
            }
            return self._all_true(state, checks, RollbackState.ROLLBACK_COMPLETE, "ROLLBACK_COMPLETE")
        return self._stop(state, DomainResult.BLOCKED, "ROLLBACK_STATE_UNSUPPORTED")

    def _all_true(
        self,
        current: RollbackState,
        checks: dict[str, bool | None],
        next_state: RollbackState,
        code: str,
    ) -> RollbackTransitionDecision:
        contradicted = tuple(name for name, value in checks.items() if value is False)
        if contradicted:
            return self._stop(current, DomainResult.HOLD, contradicted[0], *contradicted)
        unknown = tuple(name for name, value in checks.items() if value is None)
        if unknown:
            return self._stop(current, DomainResult.INCONCLUSIVE, f"{code}_EVIDENCE_MISSING", *unknown)
        return self._pass(current, next_state, code)

    @staticmethod
    def _pass(
        current: RollbackState,
        next_state: RollbackState,
        code: str,
    ) -> RollbackTransitionDecision:
        return RollbackTransitionDecision(DomainResult.PASS, current, next_state, code)

    @staticmethod
    def _stop(
        current: RollbackState,
        result: DomainResult,
        code: str,
        *reasons: str,
    ) -> RollbackTransitionDecision:
        return RollbackTransitionDecision(result, current, current, code, tuple(reasons))
