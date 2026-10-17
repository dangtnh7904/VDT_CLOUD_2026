from __future__ import annotations

import unittest

from app.modules.rollback import RollbackEvidence, RollbackState, RollbackStateMachine
from app.modules.upgrade_common.domain import DomainResult


class RollbackStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.machine = RollbackStateMachine()

    def test_ok_to_stop_does_not_substitute_for_safe_to_destroy(self):
        decision = self.machine.evaluate(
            RollbackState.SOURCES_READY,
            RollbackEvidence(ok_to_stop=True, safe_to_destroy=None),
        )

        self.assertEqual(decision.result, DomainResult.INCONCLUSIVE)
        self.assertEqual(decision.code, "SAFE_TO_DESTROY_MISSING")
        self.assertIn("OK_TO_STOP_IS_NOT_SAFE_TO_DESTROY", decision.reasons)

    def test_incompatible_old_binary_blocks_every_state(self):
        decision = self.machine.evaluate(
            RollbackState.SAFE_TO_REMOVE,
            RollbackEvidence(old_binary_compatible_with_device=False),
        )

        self.assertEqual(decision.result, DomainResult.BLOCKED)
        self.assertEqual(decision.code, "ROLLBACK_VERSION_INCOMPATIBLE")

    def test_containment_requires_absence_from_up_and_acting(self):
        decision = self.machine.evaluate(
            RollbackState.HOLD,
            RollbackEvidence(
                target_fenced=True,
                target_absent_from_up=True,
                target_absent_from_acting=False,
            ),
        )

        self.assertEqual(decision.result, DomainResult.HOLD)
        self.assertEqual(decision.next_state, RollbackState.HOLD)

    def test_rollback_complete_requires_rebuild_stability_and_clean_ledger(self):
        rebuilt = self.machine.evaluate(
            RollbackState.R_PROVISIONED,
            RollbackEvidence(rebuild_complete=True, rebuild_clean=True),
        )
        complete = self.machine.evaluate(
            RollbackState.R_REBUILT,
            RollbackEvidence(stable_window_met=True, ledger_clean=True),
        )

        self.assertEqual(rebuilt.next_state, RollbackState.R_REBUILT)
        self.assertEqual(complete.next_state, RollbackState.ROLLBACK_COMPLETE)


if __name__ == "__main__":
    unittest.main()
