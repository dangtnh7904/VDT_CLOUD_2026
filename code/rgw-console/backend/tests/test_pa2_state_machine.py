import unittest

from app.modules.upgrade_pa2.domain import (
    Pa2Decision,
    Pa2Evidence,
    Pa2State,
    Pa2StateMachine,
    ReplicaCheck,
    ResumeEvidence,
    assess_final_spare,
    evaluate_resume,
    select_recovery_mapping,
)


def test_p201_spare_chain_requires_reservation_domain_down_set_and_lease() -> None:
    result = Pa2StateMachine.evaluate(
        Pa2State.WAVE_PLANNED,
        Pa2Evidence(
            destination_reserved=True,
            failure_domain_distinct=True,
            down_set_safe=True,
            lease_owned=True,
        ),
    )

    assert result.decision is Pa2Decision.ADVANCE
    assert result.next_state is Pa2State.CHAIN_READY


def test_p202_spare_candidate_fails_closed_on_digest_mismatch() -> None:
    result = Pa2StateMachine.evaluate(
        Pa2State.CHAIN_READY,
        Pa2Evidence(
            destination_reserved=True,
            destination_healthy=True,
            destination_correct_digest=False,
            destination_isolated=True,
        ),
    )

    assert result.decision is Pa2Decision.HOLD
    assert result.reason_code == "SPARE_DIGEST_MISMATCH"


def test_p203_admission_requires_current_lease_and_topology_checks() -> None:
    result = Pa2StateMachine.evaluate(
        Pa2State.SPARE_CANDIDATE,
        Pa2Evidence(
            failure_domain_distinct=True,
            down_set_safe=True,
            lease_owned=False,
        ),
    )

    assert result.decision is Pa2Decision.HOLD
    assert result.next_state is Pa2State.SPARE_CANDIDATE


def test_p204_mapping_change_during_replica_check_holds_group() -> None:
    result = Pa2StateMachine.evaluate(
        Pa2State.HANDOFF_GROUP_SCRUBBING,
        Pa2Evidence(
            replica_checks=(
                ReplicaCheck(
                    pg_id="1.abc",
                    accepted=True,
                    mapping_unchanged=False,
                ),
            ),
        ),
    )

    assert result.decision is Pa2Decision.HOLD
    assert result.reason_code == "MAPPING_CHANGED_DURING_CHECK"


def test_p205_handoff_complete_does_not_mean_wave_complete() -> None:
    result = Pa2StateMachine.evaluate(
        Pa2State.HANDOFF_GROUP_ACCEPTED,
        Pa2Evidence(
            remaining_handoff_groups=0,
            source_absent_from_up=True,
            source_absent_from_acting=True,
            destination_membership_matches=True,
        ),
    )

    assert result.next_state is Pa2State.HANDOFF_COMPLETE
    assert result.next_state is not Pa2State.WAVE_COMPLETE


def test_p206_source_upgrade_blocked_until_absent_from_entire_scope() -> None:
    result = Pa2StateMachine.evaluate(
        Pa2State.HANDOFF_COMPLETE,
        Pa2Evidence(
            source_absent_from_up=True,
            source_absent_from_acting=False,
        ),
    )

    assert result.decision is Pa2Decision.HOLD
    assert result.reason_code == "SOURCE_STILL_MAPPED"


def test_p207_wave_needs_end_state_reconciliation_and_stability() -> None:
    reconciled = Pa2StateMachine.evaluate(
        Pa2State.WAVE_RECONCILING,
        Pa2Evidence(
            end_state_reconciled=True,
            version_coverage_complete=True,
            ownership_resolved=True,
        ),
    )
    completed = Pa2StateMachine.evaluate(
        Pa2State.WAVE_STABILIZING,
        Pa2Evidence(
            stable_window_started=True,
            stable_window_met=True,
            ledger_clean=True,
        ),
    )

    assert reconciled.next_state is Pa2State.WAVE_STABILIZING
    assert completed.decision is Pa2Decision.COMPLETE
    assert completed.next_state is Pa2State.WAVE_COMPLETE


def test_p208_final_spare_without_pg_is_not_exercised() -> None:
    result = assess_final_spare(received_pg=False, replica_checks=())

    assert result.decision is Pa2Decision.NOT_EXERCISED
    assert result.reason_code == "FINAL_SPARE_NOT_EXERCISED"


def test_p209_resume_and_recovery_use_current_observed_state() -> None:
    resume = evaluate_resume(
        Pa2State.HANDOFF_GROUP_CONVERGING,
        ResumeEvidence(
            current_mapping_available=True,
            lease_valid=True,
            ledger_consistent=True,
            prior_actions_reconciled=True,
        ),
    )

    assert resume.decision is Pa2Decision.ADVANCE
    assert resume.next_state is Pa2State.HANDOFF_GROUP_CONVERGING
    assert select_recovery_mapping(("osd.9", "osd.4", "osd.9")) == ("osd.9", "osd.4")


def test_cleanup_cannot_remove_dependency_used_by_another_chain() -> None:
    result = Pa2StateMachine.evaluate(
        Pa2State.SPARE_ROTATED,
        Pa2Evidence(dependency_required_by_other_work=True),
    )

    assert result.decision is Pa2Decision.HOLD
    assert result.reason_code == "DEPENDENCY_STILL_REQUIRED"


def test_empty_current_mapping_cannot_be_used_for_recovery() -> None:
    try:
        select_recovery_mapping(())
    except ValueError as exc:
        assert str(exc) == "current mapping is required for recovery"
    else:
        raise AssertionError("expected an empty current mapping to fail closed")


def test_full_single_rotation_path_reaches_wave_complete() -> None:
    cases = (
        (
            Pa2State.WAVE_PLANNED,
            Pa2Evidence(
                destination_reserved=True,
                failure_domain_distinct=True,
                down_set_safe=True,
                lease_owned=True,
            ),
            Pa2State.CHAIN_READY,
        ),
        (
            Pa2State.CHAIN_READY,
            Pa2Evidence(
                destination_reserved=True,
                destination_healthy=True,
                destination_correct_digest=True,
                destination_isolated=True,
            ),
            Pa2State.SPARE_CANDIDATE,
        ),
        (
            Pa2State.SPARE_CANDIDATE,
            Pa2Evidence(
                failure_domain_distinct=True,
                down_set_safe=True,
                lease_owned=True,
            ),
            Pa2State.SPARE_ADMISSION_ALLOWED,
        ),
        (
            Pa2State.SPARE_ADMISSION_ALLOWED,
            Pa2Evidence(destination_admitted=True),
            Pa2State.HANDOFF_GROUP_CONVERGING,
        ),
        (
            Pa2State.HANDOFF_GROUP_CONVERGING,
            Pa2Evidence(mapping_converged=True),
            Pa2State.HANDOFF_GROUP_SCRUBBING,
        ),
        (
            Pa2State.HANDOFF_GROUP_SCRUBBING,
            Pa2Evidence(replica_checks=(ReplicaCheck(pg_id="1.abc", accepted=True),)),
            Pa2State.HANDOFF_GROUP_ACCEPTED,
        ),
        (
            Pa2State.HANDOFF_GROUP_ACCEPTED,
            Pa2Evidence(
                remaining_handoff_groups=0,
                source_absent_from_up=True,
                source_absent_from_acting=True,
                destination_membership_matches=True,
            ),
            Pa2State.HANDOFF_COMPLETE,
        ),
        (
            Pa2State.HANDOFF_COMPLETE,
            Pa2Evidence(source_absent_from_up=True, source_absent_from_acting=True),
            Pa2State.SOURCE_UPGRADING,
        ),
        (
            Pa2State.SOURCE_UPGRADING,
            Pa2Evidence(
                source_redeployed=True,
                source_healthy=True,
                source_correct_digest=True,
                source_isolated=True,
                source_has_new_incarnation=True,
            ),
            Pa2State.SPARE_ROTATED,
        ),
        (
            Pa2State.SPARE_ROTATED,
            Pa2Evidence(remaining_rotations=0),
            Pa2State.WAVE_RECONCILING,
        ),
        (
            Pa2State.WAVE_RECONCILING,
            Pa2Evidence(
                end_state_reconciled=True,
                version_coverage_complete=True,
                ownership_resolved=True,
            ),
            Pa2State.WAVE_STABILIZING,
        ),
        (
            Pa2State.WAVE_STABILIZING,
            Pa2Evidence(
                stable_window_started=True,
                stable_window_met=True,
                ledger_clean=True,
            ),
            Pa2State.WAVE_COMPLETE,
        ),
    )

    for current, evidence, expected in cases:
        result = Pa2StateMachine.evaluate(current, evidence)
        assert result.next_state is expected


class Pa2StateMachineTests(unittest.TestCase):
    """Expose the pure contract cases to the repository's unittest runner."""

    test_p201_spare_chain_requires_reservation_domain_down_set_and_lease = staticmethod(
        test_p201_spare_chain_requires_reservation_domain_down_set_and_lease
    )
    test_p202_spare_candidate_fails_closed_on_digest_mismatch = staticmethod(
        test_p202_spare_candidate_fails_closed_on_digest_mismatch
    )
    test_p203_admission_requires_current_lease_and_topology_checks = staticmethod(
        test_p203_admission_requires_current_lease_and_topology_checks
    )
    test_p204_mapping_change_during_replica_check_holds_group = staticmethod(
        test_p204_mapping_change_during_replica_check_holds_group
    )
    test_p205_handoff_complete_does_not_mean_wave_complete = staticmethod(
        test_p205_handoff_complete_does_not_mean_wave_complete
    )
    test_p206_source_upgrade_blocked_until_absent_from_entire_scope = staticmethod(
        test_p206_source_upgrade_blocked_until_absent_from_entire_scope
    )
    test_p207_wave_needs_end_state_reconciliation_and_stability = staticmethod(
        test_p207_wave_needs_end_state_reconciliation_and_stability
    )
    test_p208_final_spare_without_pg_is_not_exercised = staticmethod(
        test_p208_final_spare_without_pg_is_not_exercised
    )
    test_p209_resume_and_recovery_use_current_observed_state = staticmethod(
        test_p209_resume_and_recovery_use_current_observed_state
    )
    test_cleanup_cannot_remove_dependency_used_by_another_chain = staticmethod(
        test_cleanup_cannot_remove_dependency_used_by_another_chain
    )
    test_empty_current_mapping_cannot_be_used_for_recovery = staticmethod(
        test_empty_current_mapping_cannot_be_used_for_recovery
    )
    test_full_single_rotation_path_reaches_wave_complete = staticmethod(
        test_full_single_rotation_path_reaches_wave_complete
    )


if __name__ == "__main__":
    unittest.main()
