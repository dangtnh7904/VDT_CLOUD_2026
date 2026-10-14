from datetime import datetime, timedelta, timezone
import unittest

from app.modules.upgrade_common.down_set_assessment import (
    DownSetInventoryAssessmentService,
)


NOW = datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)


def _run(**overrides):
    value = {
        "id": "run-a",
        "cluster_id": "lab-a",
        "cluster_fsid": "fsid-a",
        "session_id": "session-a",
        "config_snapshot_id": "config-a",
        "state": "CREATED",
        "plan_revision": 7,
        "resource_version": 11,
        "source_osds": [1, 2],
        "parameters": {"max_simultaneous_down": 1},
    }
    value.update(overrides)
    return value


def _collection(**overrides):
    value = {
        "id": "collection-a",
        "cluster_id": "lab-a",
        "cluster_fsid": "fsid-a",
        "session_id": "session-a",
        "config_snapshot_id": "config-a",
        "phase": "DURING",
        "collection_state": "COMPLETE",
        "quality_status": "VALID",
        "payload_sha256": "b" * 64,
        "requested_osd_ids": [1, 2, 3],
        "collected_at": NOW - timedelta(seconds=4),
        "osds": [
            {"osd_id": 1, "up": True, "in": True, "quality_status": "VALID"},
            {"osd_id": 2, "up": True, "in": True, "quality_status": "VALID"},
            {"osd_id": 3, "up": True, "in": True, "quality_status": "VALID"},
        ],
    }
    value.update(overrides)
    return value


def _service(run=None, collection=None):
    persisted_run = run or _run()
    persisted_collection = collection or _collection()
    return DownSetInventoryAssessmentService(
        load_run=lambda run_id: persisted_run,
        load_collection=lambda collection_id: persisted_collection,
        allowed_osd_ids=[1, 2, 3],
        max_age_seconds=45,
        clock_skew_seconds=5,
        now=lambda: NOW,
    )


def _assess(service, **overrides):
    request = {
        "run_id": "run-a",
        "collection_id": "collection-a",
        "target_osd_ids": [1],
        "expected_state": "CREATED",
        "expected_plan_revision": 7,
        "expected_config_snapshot_id": "config-a",
        "expected_resource_version": 11,
    }
    request.update(overrides)
    return service.assess(**request)


def test_assessment_loads_persisted_evidence_and_returns_inventory_ready_only():
    loaded = []
    service = DownSetInventoryAssessmentService(
        load_run=lambda run_id: loaded.append(("run", run_id)) or _run(),
        load_collection=lambda collection_id: loaded.append(
            ("collection", collection_id)
        )
        or _collection(),
        allowed_osd_ids=[1, 2, 3],
        max_age_seconds=45,
        clock_skew_seconds=5,
        now=lambda: NOW,
    )

    result = _assess(service)

    assert loaded == [("run", "run-a"), ("collection", "collection-a")]
    assert result["inventory_result"] == "READY"
    assert result["mutation_readiness"] == "BLOCKED"
    assert result["run_id"] == "run-a"
    assert result["collection_id"] == "collection-a"


def test_stale_control_tokens_block_before_inventory_result_is_used():
    service = _service(run=_run(state="PREFLIGHTED", resource_version=12))

    result = _assess(service)

    assert result["inventory_result"] == "BLOCKED"
    assert result["mutation_readiness"] == "BLOCKED"
    assert result["reasons"] == ["RUN_STATE_CHANGED", "RESOURCE_VERSION_CHANGED"]
    assert result["observed"]["actual_state"] == "PREFLIGHTED"
    assert result["observed"]["actual_resource_version"] == 12


def test_revision_and_config_snapshot_are_bound_to_the_request():
    service = _service(run=_run(plan_revision=8, config_snapshot_id="config-b"))

    result = _assess(service)

    assert result["inventory_result"] == "BLOCKED"
    assert result["reasons"] == [
        "PLAN_REVISION_CHANGED",
        "CONFIG_SNAPSHOT_CHANGED",
    ]


def test_persisted_collection_identity_is_still_checked_by_domain_gate():
    service = _service(collection=_collection(session_id="another-session"))

    result = _assess(service)

    assert result["inventory_result"] == "BLOCKED"
    assert result["reasons"] == ["SESSION_ID_MISMATCH"]


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(case)
        for case in (
            test_assessment_loads_persisted_evidence_and_returns_inventory_ready_only,
            test_stale_control_tokens_block_before_inventory_result_is_used,
            test_revision_and_config_snapshot_are_bound_to_the_request,
            test_persisted_collection_identity_is_still_checked_by_domain_gate,
        )
    )
