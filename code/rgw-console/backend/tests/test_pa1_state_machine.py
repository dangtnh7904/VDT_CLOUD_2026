from __future__ import annotations

import unittest

from app.modules.replica_validation.domain import ReplicaCheckDecision
from app.modules.upgrade_common.domain import DomainResult
from app.modules.upgrade_pa1 import Pa1Evidence, Pa1State, Pa1StateMachine


PASS_CHECK = ReplicaCheckDecision(
    result=DomainResult.PASS,
    code="REPLICA_ACCEPTED",
    reasons=(),
    mapping_fingerprint="mapping-a",
)


class Pa1StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.machine = Pa1StateMachine()

    def test_drain_requires_absence_from_both_up_and_acting(self):
        decision = self.machine.evaluate(
            Pa1State.DRAINING,
            Pa1Evidence(source_absent_from_up=True, source_absent_from_acting=False),
        )

        self.assertEqual(decision.result, DomainResult.INCONCLUSIVE)
        self.assertEqual(decision.next_state, Pa1State.DRAINING)
        self.assertIn("SOURCE_PRESENT_OR_UNKNOWN_IN_ACTING", decision.reasons)

    def test_wrong_digest_holds_daemon_readiness(self):
        decision = self.machine.evaluate(
            Pa1State.UPGRADING,
            Pa1Evidence(
                daemon_up=True,
                daemon_in=True,
                version_matches=True,
                digest_matches=False,
                incarnation_matches=True,
                target_still_isolated=True,
            ),
        )

        self.assertEqual(decision.result, DomainResult.HOLD)
        self.assertEqual(decision.code, "DIGEST_MISMATCH")
        self.assertEqual(decision.next_state, Pa1State.UPGRADING)

    def test_admission_break_and_unexpected_primary_are_global_holds(self):
        for evidence, code in (
            (Pa1Evidence(admission_broken=True), "HOLD_ADMISSION_BROKEN"),
            (Pa1Evidence(unexpected_primary=True), "HOLD_UNEXPECTED_PRIMARY"),
        ):
            with self.subTest(code=code):
                decision = self.machine.evaluate(Pa1State.REPLICA_CONVERGING, evidence)
                self.assertEqual(decision.result, DomainResult.HOLD)
                self.assertEqual(decision.code, code)

    def test_scrub_state_uses_backend_replica_decisions(self):
        decision = self.machine.evaluate(
            Pa1State.REPLICA_SCRUBBING,
            Pa1Evidence(replica_checks=(PASS_CHECK,)),
        )

        self.assertEqual(decision.result, DomainResult.PASS)
        self.assertEqual(decision.next_state, Pa1State.REPLICA_ACCEPTED)

    def test_affinity_restore_waits_for_every_return_group(self):
        more = self.machine.evaluate(
            Pa1State.REPLICA_ACCEPTED,
            Pa1Evidence(remaining_return_groups=1),
        )
        complete = self.machine.evaluate(
            Pa1State.REPLICA_ACCEPTED,
            Pa1Evidence(remaining_return_groups=0),
        )

        self.assertEqual(more.next_state, Pa1State.REPLICA_RETURN)
        self.assertEqual(complete.next_state, Pa1State.PRIMARY_RESTORE_READY)

    def test_complete_requires_stable_window_and_clean_ledger(self):
        waiting = self.machine.evaluate(
            Pa1State.STABILIZING,
            Pa1Evidence(stable_window_met=True, ledger_clean=False),
        )
        complete = self.machine.evaluate(
            Pa1State.STABILIZING,
            Pa1Evidence(stable_window_met=True, ledger_clean=True),
        )

        self.assertEqual(waiting.result, DomainResult.INCONCLUSIVE)
        self.assertEqual(complete.next_state, Pa1State.COMPLETE)


if __name__ == "__main__":
    unittest.main()
