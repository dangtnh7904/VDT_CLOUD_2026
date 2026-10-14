"""Application service for read-only pre-down-set inventory assessment."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from app.modules.osd_info_collector.down_set_readiness import (
    MUTATION_LIMITATIONS,
    evaluate_down_set_inventory,
)


Loader = Callable[[str], Mapping[str, Any]]


class DownSetInventoryAssessmentService:
    """Bind a down-set assessment to persisted run and collection state.

    Loaders are injected so this service remains independent of HTTP and a
    particular database adapter.  The caller cannot supply either persisted
    object directly, which prevents request data from impersonating evidence.
    """

    def __init__(
        self,
        *,
        load_run: Loader,
        load_collection: Loader,
        allowed_osd_ids: Iterable[int],
        max_age_seconds: int,
        clock_skew_seconds: int,
        now: Callable[[], datetime],
    ) -> None:
        self._load_run = load_run
        self._load_collection = load_collection
        self._allowed_osd_ids = tuple(int(value) for value in allowed_osd_ids)
        self._max_age_seconds = max_age_seconds
        self._clock_skew_seconds = clock_skew_seconds
        self._now = now

    @staticmethod
    def _blocked(
        *,
        run_id: str,
        collection_id: str,
        target_osd_ids: Iterable[int],
        reasons: list[str],
        observed: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "collection_id": collection_id,
            "inventory_result": "BLOCKED",
            "mutation_readiness": "BLOCKED",
            "reasons": reasons,
            "limitations": list(MUTATION_LIMITATIONS),
            "target_osd_ids": sorted({int(value) for value in target_osd_ids}),
            "observed": dict(observed),
        }

    def assess(
        self,
        *,
        run_id: str,
        collection_id: str,
        target_osd_ids: Iterable[int],
        expected_state: str,
        expected_plan_revision: int,
        expected_config_snapshot_id: str,
        expected_resource_version: int,
    ) -> dict[str, Any]:
        run = self._load_run(run_id)
        collection = self._load_collection(collection_id)
        targets = tuple(int(value) for value in target_osd_ids)

        actual_plan_revision = run.get("plan_revision", run.get("revision"))
        observed = {
            "expected_state": expected_state,
            "actual_state": run.get("state"),
            "expected_plan_revision": expected_plan_revision,
            "actual_plan_revision": actual_plan_revision,
            "expected_config_snapshot_id": expected_config_snapshot_id,
            "actual_config_snapshot_id": run.get("config_snapshot_id"),
            "expected_resource_version": expected_resource_version,
            "actual_resource_version": run.get("resource_version"),
        }
        stale_reasons: list[str] = []
        if run.get("state") != expected_state:
            stale_reasons.append("RUN_STATE_CHANGED")
        if actual_plan_revision != expected_plan_revision:
            stale_reasons.append("PLAN_REVISION_CHANGED")
        if run.get("config_snapshot_id") != expected_config_snapshot_id:
            stale_reasons.append("CONFIG_SNAPSHOT_CHANGED")
        if run.get("resource_version") != expected_resource_version:
            stale_reasons.append("RESOURCE_VERSION_CHANGED")
        if stale_reasons:
            return self._blocked(
                run_id=run_id,
                collection_id=collection_id,
                target_osd_ids=targets,
                reasons=stale_reasons,
                observed=observed,
            )

        result = evaluate_down_set_inventory(
            run=run,
            collection=collection,
            target_osd_ids=targets,
            allowed_osd_ids=self._allowed_osd_ids,
            now=self._now(),
            max_age_seconds=self._max_age_seconds,
            clock_skew_seconds=self._clock_skew_seconds,
        )
        result["run_id"] = run_id
        result["collection_id"] = collection_id
        result["observed"] = {**observed, **result["observed"]}
        return result
