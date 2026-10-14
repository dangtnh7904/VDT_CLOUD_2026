from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.modules.replica_validation import (
    MappingObservation,
    ReplicaValidationInput,
    ScrubObservation,
    validate_replica,
)
from app.modules.upgrade_common.domain import DomainResult


NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def valid_input():
    mapping = MappingObservation(
        pgid="1.a",
        up=(0, 1, 2),
        acting=(0, 1, 2),
        actual_primary=0,
        interval_id="42:1",
        source_incarnation="osd.3@old",
        target_incarnation="osd.2@new",
        active=True,
        clean=True,
        observed_at=NOW,
        fresh=True,
    )
    scrub = ScrubObservation(
        requested_at=NOW + timedelta(seconds=1),
        started_at=NOW + timedelta(seconds=2),
        completed_at=NOW + timedelta(seconds=3),
        result_clean=True,
        mapping_fingerprint=mapping.fingerprint,
        inconsistency_count=0,
        io_error_count=0,
        repair_event_count=0,
        fresh=True,
    )
    return ReplicaValidationInput(
        target_osd=2,
        expected_role="REPLICA",
        convergence_observed_at=NOW,
        mapping=mapping,
        scrub=scrub,
        target_allowed_for_pgid=True,
    )


class ReplicaValidationTests(unittest.TestCase):
    def test_clean_new_scrub_on_actual_replica_passes(self):
        decision = validate_replica(valid_input())

        self.assertEqual(decision.result, DomainResult.PASS)
        self.assertEqual(decision.code, "REPLICA_ACCEPTED")

    def test_target_primary_before_restore_holds(self):
        value = valid_input()
        changed = replace(
            value,
            mapping=replace(value.mapping, actual_primary=2),
        )
        changed = replace(
            changed,
            scrub=replace(changed.scrub, mapping_fingerprint=changed.mapping.fingerprint),
        )

        decision = validate_replica(changed)

        self.assertEqual(decision.result, DomainResult.HOLD)
        self.assertIn("UNEXPECTED_PRIMARY", decision.reasons)

    def test_scrub_request_without_completion_is_inconclusive(self):
        value = valid_input()
        changed = replace(value, scrub=replace(value.scrub, started_at=None, completed_at=None))

        decision = validate_replica(changed)

        self.assertEqual(decision.result, DomainResult.INCONCLUSIVE)
        self.assertIn("SCRUB_COMPLETION_MISSING", decision.reasons)

    def test_mapping_change_invalidates_scrub_evidence(self):
        value = valid_input()
        changed = replace(value, mapping=replace(value.mapping, interval_id="43:1"))

        decision = validate_replica(changed)

        self.assertEqual(decision.result, DomainResult.INCONCLUSIVE)
        self.assertIn("MAPPING_CHANGED_AFTER_SCRUB", decision.reasons)

    def test_repair_event_is_preserved_as_hold(self):
        value = valid_input()
        changed = replace(value, scrub=replace(value.scrub, repair_event_count=1))

        decision = validate_replica(changed)

        self.assertEqual(decision.result, DomainResult.HOLD)
        self.assertIn("REPAIR_EVENT_DETECTED", decision.reasons)


if __name__ == "__main__":
    unittest.main()
