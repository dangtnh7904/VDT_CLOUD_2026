from datetime import datetime, timedelta, timezone
import unittest

from app.modules.osd_info_collector.down_set_readiness import (
    MUTATION_LIMITATIONS,
    evaluate_down_set_inventory,
)


NOW = datetime(2026, 10, 9, 2, 0, tzinfo=timezone.utc)


def _run(**overrides):
    value = {
        "cluster_id": "lab-a",
        "cluster_fsid": "fsid-a",
        "session_id": "session-a",
        "config_snapshot_id": "config-a",
        "source_osds": [1, 2],
        "parameters": {"max_simultaneous_down": 1},
    }
    value.update(overrides)
    return value


def _collection(**overrides):
    value = {
        "cluster_id": "lab-a",
        "cluster_fsid": "fsid-a",
        "session_id": "session-a",
        "config_snapshot_id": "config-a",
        "phase": "DURING",
        "collection_state": "COMPLETE",
        "quality_status": "VALID",
        "payload_sha256": "a" * 64,
        "requested_osd_ids": [1, 2, 3],
        "collected_at": NOW - timedelta(seconds=5),
        "osds": [
            {"osd_id": 1, "up": True, "in": True, "quality_status": "VALID"},
            {"osd_id": 2, "up": True, "in": True, "quality_status": "VALID"},
            {"osd_id": 3, "up": True, "in": True, "quality_status": "VALID"},
        ],
    }
    value.update(overrides)
    return value


def _evaluate(collection=None, run=None, targets=(1,)):
    return evaluate_down_set_inventory(
        run=run or _run(),
        collection=collection or _collection(),
        target_osd_ids=targets,
        allowed_osd_ids=[1, 2, 3],
        now=NOW,
        max_age_seconds=45,
        clock_skew_seconds=5,
    )


def test_inventory_can_be_ready_but_never_authorizes_mutation():
    result = _evaluate()

    assert result["inventory_result"] == "READY"
    assert result["mutation_readiness"] == "BLOCKED"
    assert result["reasons"] == []
    assert result["limitations"] == list(MUTATION_LIMITATIONS)
    assert result["observed"]["projected_unavailable_osd_ids"] == [1]


def test_requires_a_fresh_cluster_wide_snapshot():
    stale = _collection(collected_at=NOW - timedelta(seconds=46))
    assert _evaluate(stale)["inventory_result"] == "HOLD"
    assert _evaluate(stale)["reasons"] == ["COLLECTION_STALE"]

    partial = _collection(requested_osd_ids=[1, 2])
    assert _evaluate(partial)["inventory_result"] == "BLOCKED"
    assert _evaluate(partial)["reasons"] == ["COLLECTION_NOT_CLUSTER_WIDE"]


def test_unknown_state_is_not_coerced_to_up_or_down():
    collection = _collection()
    collection["osds"][2]["up"] = None

    result = _evaluate(collection)

    assert result["inventory_result"] == "INCONCLUSIVE"
    assert result["reasons"] == ["OSD_UP_IN_STATE_UNKNOWN"]
    assert result["observed"]["unknown_state_osd_ids"] == [3]


def test_existing_unavailable_osds_are_counted_in_projected_budget():
    collection = _collection()
    collection["osds"][2]["up"] = False

    result = _evaluate(collection, targets=(1,))

    assert result["inventory_result"] == "HOLD"
    assert result["reasons"] == ["MAX_SIMULTANEOUS_DOWN_EXCEEDED"]
    assert result["observed"]["already_unavailable_osd_ids"] == [3]
    assert result["observed"]["projected_unavailable_osd_ids"] == [1, 3]


def test_target_must_belong_to_the_upgrade_source_set():
    result = _evaluate(targets=(3,))

    assert result["inventory_result"] == "BLOCKED"
    assert result["reasons"] == ["TARGET_OUTSIDE_UPGRADE_SOURCE_SET"]


def test_source_and_target_must_stay_inside_the_configured_allowlist():
    result = _evaluate(run=_run(source_osds=[1, 4]), targets=(4,))

    assert result["inventory_result"] == "BLOCKED"
    assert result["reasons"] == [
        "RUN_SOURCE_OUTSIDE_ALLOWLIST",
        "TARGET_OUTSIDE_ALLOWLIST",
    ]


def test_record_scope_must_exactly_match_the_allowlist():
    collection = _collection()
    collection["osds"].append(
        {"osd_id": 4, "up": True, "in": True, "quality_status": "VALID"}
    )

    result = _evaluate(collection)

    assert result["inventory_result"] == "INCONCLUSIVE"
    assert result["reasons"] == ["OSD_RECORD_SCOPE_MISMATCH"]
    assert result["observed"]["missing_osd_ids"] == []
    assert result["observed"]["unexpected_osd_ids"] == [4]


def test_payload_hash_must_be_a_sha256_hex_digest():
    result = _evaluate(_collection(payload_sha256="not-a-digest"))

    assert result["inventory_result"] == "BLOCKED"
    assert result["reasons"] == ["ARTIFACT_SHA256_INVALID"]


def test_accepts_the_persisted_collection_schema():
    run = _run()
    run["fsid"] = run.pop("cluster_fsid")
    collection = _collection()
    collection["fsid"] = collection.pop("cluster_fsid")
    collection["state"] = collection.pop("collection_state")
    collection["quality"] = collection.pop("quality_status")
    collection["artifact_sha256"] = collection.pop("payload_sha256")
    for record in collection["osds"]:
        record["quality"] = record.pop("quality_status")

    result = _evaluate(collection, run=run)

    assert result["inventory_result"] == "READY"


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(case)
        for case in (
            test_inventory_can_be_ready_but_never_authorizes_mutation,
            test_requires_a_fresh_cluster_wide_snapshot,
            test_unknown_state_is_not_coerced_to_up_or_down,
            test_existing_unavailable_osds_are_counted_in_projected_budget,
            test_target_must_belong_to_the_upgrade_source_set,
            test_source_and_target_must_stay_inside_the_configured_allowlist,
            test_record_scope_must_exactly_match_the_allowlist,
            test_payload_hash_must_be_a_sha256_hex_digest,
            test_accepts_the_persisted_collection_schema,
        )
    )
