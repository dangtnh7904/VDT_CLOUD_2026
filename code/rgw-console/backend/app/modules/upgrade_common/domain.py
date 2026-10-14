from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ARTIFACT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class Strategy(str, Enum):
    PA1 = "PA1_PRODUCTION"
    PA2 = "PA2_ROTATING_SPARE"


class DomainResult(str, Enum):
    PASS = "PASS"
    HOLD = "HOLD"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_REQUESTED = "NOT_REQUESTED"
    NOT_EXERCISED = "NOT_EXERCISED"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class Pa2EndState(str, Enum):
    KEEP_ROTATED = "KEEP_ROTATED_PLACEMENT"
    RECONCILE = "RECONCILE_TO_POLICY"


class UpgradeDomainError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BatchParameters:
    batch_size: int
    drain_parallelism: int
    max_simultaneous_down: int
    return_parallelism: int
    scrub_concurrency: int
    promotion_parallelism: int
    chain_parallelism: int
    handoff_parallelism: int
    max_pg_per_handoff_group: int
    max_bytes_per_handoff_group: int

    def __post_init__(self) -> None:
        integer_values = asdict(self)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in integer_values.values()):
            raise UpgradeDomainError("INVALID_BATCH_PARAMETERS", "all batch parameters must be positive integers")
        if self.max_simultaneous_down > self.batch_size:
            raise UpgradeDomainError(
                "INVALID_BATCH_PARAMETERS",
                "max_simultaneous_down cannot exceed batch_size",
            )
        for field_name in (
            "drain_parallelism",
            "return_parallelism",
            "promotion_parallelism",
            "chain_parallelism",
            "handoff_parallelism",
        ):
            if getattr(self, field_name) > self.batch_size:
                raise UpgradeDomainError(
                    "INVALID_BATCH_PARAMETERS",
                    f"{field_name} cannot exceed batch_size",
                )


@dataclass(frozen=True)
class UpgradeBatchSpec:
    name: str
    source_osds: tuple[int, ...]
    destination_osds: tuple[int, ...]
    parameters: BatchParameters

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name.strip()) > 255:
            raise UpgradeDomainError("INVALID_BATCH", "batch name must contain 1 to 255 characters")
        if not self.source_osds or not self.destination_osds:
            raise UpgradeDomainError("INVALID_BATCH", "source and destination OSD sets are required")
        if any(isinstance(osd, bool) or not isinstance(osd, int) or osd < 0 for osd in self.source_osds + self.destination_osds):
            raise UpgradeDomainError("INVALID_BATCH", "OSD IDs must be non-negative integers")
        if len(set(self.source_osds)) != len(self.source_osds) or len(set(self.destination_osds)) != len(self.destination_osds):
            raise UpgradeDomainError("INVALID_BATCH", "OSD IDs must be unique within each set")
        if set(self.source_osds) & set(self.destination_osds):
            raise UpgradeDomainError("INVALID_BATCH", "source and destination OSD sets must not overlap")
        if len(self.source_osds) > self.parameters.batch_size:
            raise UpgradeDomainError("INVALID_BATCH", "source OSD count cannot exceed batch_size")


@dataclass(frozen=True)
class UpgradeRunSpec:
    strategy: Strategy
    target_version: str
    target_image_digest: str
    pa2_end_state: Pa2EndState | None = None

    def __post_init__(self) -> None:
        if not self.target_version.strip() or len(self.target_version) > 128:
            raise UpgradeDomainError("INVALID_RUN_CONFIG", "target_version is required")
        if not IMAGE_DIGEST_RE.fullmatch(self.target_image_digest):
            raise UpgradeDomainError(
                "INVALID_RUN_CONFIG",
                "target_image_digest must be a pinned sha256 digest",
            )
        if self.strategy is Strategy.PA1 and self.pa2_end_state is not None:
            raise UpgradeDomainError("INVALID_RUN_CONFIG", "PA1 must not define a PA2 end state")
        if self.strategy is Strategy.PA2 and self.pa2_end_state is None:
            raise UpgradeDomainError("INVALID_RUN_CONFIG", "PA2 requires an explicit end state")


@dataclass(frozen=True)
class DryRunPlan:
    schema_version: int
    strategy: str
    dry_run_result: str
    execution_readiness: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    steps: tuple[dict[str, Any], ...]
    invariants: tuple[str, ...]
    inventory_epoch: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SafetyGateDecision:
    result: str
    blockers: tuple[str, ...]
    observed: dict[str, Any]


@dataclass(frozen=True)
class InventoryBindingDecision:
    result: str
    reasons: tuple[str, ...]
    observed: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _evidence_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def evaluate_inventory_binding(
    run: dict[str, Any],
    collection: dict[str, Any],
    *,
    now: datetime,
    max_age_seconds: float,
    clock_skew_seconds: float = 5,
) -> InventoryBindingDecision:
    """Fail-closed readiness for binding an immutable OSD snapshot to a plan."""

    now = now.astimezone(timezone.utc)
    blocked: list[str] = []
    inconclusive: list[str] = []
    holds: list[str] = []

    identity_fields = (
        ("cluster_id", "CLUSTER_ID_MISMATCH"),
        ("fsid", "FSID_MISMATCH"),
        ("session_id", "SESSION_MISMATCH"),
        ("config_snapshot_id", "CONFIG_SNAPSHOT_MISMATCH"),
    )
    for field, reason in identity_fields:
        if str(collection.get(field) or "") != str(run.get(field) or ""):
            blocked.append(reason)
    if collection.get("phase") != "BEFORE":
        blocked.append("BEFORE_PHASE_REQUIRED")
    if collection.get("state") != "COMPLETE":
        holds.append("COLLECTION_NOT_COMPLETE")
    if collection.get("quality") != "VALID":
        inconclusive.append("COLLECTION_QUALITY_NOT_VALID")
    if not ARTIFACT_HASH_RE.fullmatch(str(collection.get("artifact_sha256") or "")):
        inconclusive.append("ARTIFACT_HASH_MISSING")

    required_ids = {
        int(item)
        for item in (run.get("source_osds") or []) + (run.get("destination_osds") or [])
        if isinstance(item, int) and not isinstance(item, bool)
    }
    records = collection.get("osds")
    if not isinstance(records, list):
        records = []
        inconclusive.append("OSD_RECORDS_MISSING")
    by_id: dict[int, dict[str, Any]] = {}
    duplicate_ids: set[int] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        osd_id = record.get("osd_id")
        if isinstance(osd_id, bool) or not isinstance(osd_id, int):
            continue
        if osd_id in by_id:
            duplicate_ids.add(osd_id)
        by_id[osd_id] = record
    if duplicate_ids:
        inconclusive.append("OSD_SCOPE_AMBIGUOUS")
    missing_ids = sorted(required_ids - set(by_id))
    if missing_ids:
        inconclusive.append("PLAN_OSD_SCOPE_MISSING")
    invalid_ids = sorted(
        osd_id for osd_id in required_ids & set(by_id)
        if by_id[osd_id].get("quality") != "VALID"
    )
    if invalid_ids:
        inconclusive.append("PLAN_OSD_QUALITY_NOT_VALID")

    collected_at = _evidence_time(collection.get("collected_at"))
    age_seconds: float | None = None
    expires_at: datetime | None = None
    if collected_at is None:
        inconclusive.append("COLLECTED_AT_INVALID")
    else:
        age_seconds = (now - collected_at).total_seconds()
        expires_at = collected_at + timedelta(seconds=max_age_seconds)
        if age_seconds < -clock_skew_seconds:
            inconclusive.append("COLLECTED_AT_IN_FUTURE")
        elif age_seconds > max_age_seconds:
            holds.append("INVENTORY_STALE")

    reasons = tuple(sorted(set(blocked + inconclusive + holds)))
    if blocked:
        result = DomainResult.BLOCKED.value
    elif inconclusive:
        result = DomainResult.INCONCLUSIVE.value
    elif holds:
        result = DomainResult.HOLD.value
    else:
        result = "READY"
    return InventoryBindingDecision(
        result=result,
        reasons=reasons,
        observed={
            "collection_id": str(collection.get("id") or ""),
            "artifact_sha256": collection.get("artifact_sha256"),
            "phase": collection.get("phase"),
            "quality": collection.get("quality"),
            "required_osd_ids": sorted(required_ids),
            "observed_osd_ids": sorted(by_id),
            "missing_osd_ids": missing_ids,
            "invalid_osd_ids": invalid_ids,
            "collected_at": collected_at.isoformat() if collected_at else None,
            "evaluated_at": now.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
        },
    )


class UpgradeSafetyGate:
    """Actual-state-only safety gate shared by both strategy planners."""

    def evaluate(
        self,
        batch: UpgradeBatchSpec,
        *,
        inventory: dict[str, Any],
        expected_fsid: str,
    ) -> SafetyGateDecision:
        blockers: list[str] = []
        if inventory.get("fsid") != expected_fsid:
            blockers.append("FSID_MISMATCH")
        quality = inventory.get("quality")
        if quality != "VALID":
            blockers.append("STALE_INVENTORY" if quality == "STALE" else "INVENTORY_INCONCLUSIVE")
        if inventory.get("osdmap_epoch") is None:
            blockers.append("OSDMAP_EPOCH_MISSING")
        if inventory.get("health") != "HEALTH_OK":
            blockers.append("CLUSTER_HEALTH_NOT_OK")

        osds = {
            int(item["osd_id"]): item
            for item in inventory.get("osds", [])
            if isinstance(item, dict) and isinstance(item.get("osd_id"), int)
        }
        scoped_ids = batch.source_osds + batch.destination_osds
        for osd_id in scoped_ids:
            observed = osds.get(osd_id)
            if observed is None:
                blockers.append(f"OSD_NOT_FOUND:{osd_id}")
                continue
            if not observed.get("allowed"):
                blockers.append(f"OSD_OUTSIDE_ALLOWLIST:{osd_id}")
            if observed.get("up") is not True or observed.get("in") is not True:
                blockers.append(f"OSD_NOT_UP_IN:{osd_id}")

        source_hosts = {osds[item].get("host") for item in batch.source_osds if item in osds}
        for destination in batch.destination_osds:
            destination_host = osds.get(destination, {}).get("host")
            if destination_host and destination_host in source_hosts:
                blockers.append(f"FAILURE_DOMAIN_CONFLICT:{destination}")

        scoped_pools = [pool for pool in inventory.get("pools", []) if pool.get("allowed")]
        if not scoped_pools:
            blockers.append("UPGRADE_POOL_SCOPE_EMPTY")
        for pool in scoped_pools:
            if pool.get("type") != "replicated":
                blockers.append(f"UNSUPPORTED_POOL_TYPE:{pool.get('name')}")
            if not isinstance(pool.get("size"), int) or not isinstance(pool.get("min_size"), int):
                blockers.append(f"POOL_REPLICATION_UNKNOWN:{pool.get('name')}")
            elif pool["min_size"] >= pool["size"]:
                blockers.append(f"POOL_NO_FAILURE_HEADROOM:{pool.get('name')}")

        unique = tuple(sorted(set(blockers)))
        return SafetyGateDecision(
            result="PASS" if not unique else "BLOCKED",
            blockers=unique,
            observed={
                "fsid": inventory.get("fsid"),
                "quality": quality,
                "health": inventory.get("health"),
                "osdmap_epoch": inventory.get("osdmap_epoch"),
                "source_osds": list(batch.source_osds),
                "destination_osds": list(batch.destination_osds),
                "scoped_pools": [pool.get("name") for pool in scoped_pools],
            },
        )


class DryRunPlanner:
    """Pure planner: it cannot execute commands or mutate cluster state."""

    REQUIRED_LIVE_CAPABILITIES = (
        "query_osd_inventory",
        "query_pg_up_acting_primary",
        "query_osd_image_digest",
        "deep_scrub_completion_marker",
        "cephadm_redeploy_target_image",
    )

    def build(
        self,
        batch: UpgradeBatchSpec,
        run: UpgradeRunSpec,
        *,
        inventory: dict[str, Any],
        capabilities: dict[str, Any],
        expected_fsid: str,
    ) -> DryRunPlan:
        safety = UpgradeSafetyGate().evaluate(
            batch,
            inventory=inventory,
            expected_fsid=expected_fsid,
        )
        blockers = list(safety.blockers)
        warnings: list[str] = []

        capability_matrix = capabilities.get("capabilities") or {}
        for capability in self.REQUIRED_LIVE_CAPABILITIES:
            if capability_matrix.get(capability) != "SUPPORTED":
                warnings.append(f"LIVE_CAPABILITY_NOT_READY:{capability}")

        blockers = sorted(set(blockers))
        warnings = sorted(set(warnings))
        steps = self._pa1_steps(batch) if run.strategy is Strategy.PA1 else self._pa2_steps(batch, run)
        return DryRunPlan(
            schema_version=1,
            strategy=run.strategy.value,
            dry_run_result="PASS" if not blockers else "BLOCKED",
            execution_readiness="READY" if not blockers and not warnings else "BLOCKED",
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            steps=tuple(steps),
            invariants=(
                "NO_CLUSTER_MUTATION_IN_DRY_RUN",
                "ACTUAL_STATE_RECHECK_BEFORE_EACH_LIVE_ACTION",
                "BOTH_UP_AND_ACTING_REQUIRED_FOR_ISOLATION",
                "NEW_DEEP_SCRUB_COMPLETION_REQUIRED_AFTER_CONVERGENCE",
                "UI_CANNOT_SUBMIT_PASS_OR_ACTUAL_ROLE",
            ),
            inventory_epoch=inventory.get("osdmap_epoch"),
        )

    @staticmethod
    def _step(sequence: int, action: str, resource: str, *preconditions: str) -> dict[str, Any]:
        return {
            "sequence": sequence,
            "action": action,
            "resource": resource,
            "would_mutate": action not in {
                "probe_capabilities",
                "capture_baseline",
                "verify_isolation",
                "verify_daemon",
                "replica_check",
                "wait_stable_window",
                "reconcile_actual_state",
            },
            "preconditions": list(preconditions),
        }

    def _pa1_steps(self, batch: UpgradeBatchSpec) -> list[dict[str, Any]]:
        steps = [
            self._step(1, "probe_capabilities", "cluster", "FSID_MATCH"),
            self._step(2, "capture_baseline", "batch", "FRESH_INVENTORY"),
        ]
        sequence = 3
        destinations = list(batch.destination_osds)
        for index, source in enumerate(batch.source_osds):
            destination = destinations[index % len(destinations)]
            resource = f"osd.{source}->osd.{destination}"
            for action, preconditions in (
                ("reduce_primary_duty", ("PLAN_REVISION_MATCH",)),
                ("drain", ("UPGRADE_SAFETY_GATE_PASS", "LEASE_OWNED")),
                ("verify_isolation", ("SOURCE_ABSENT_FROM_UP_AND_ACTING",)),
                ("maintenance_gate", ("CURRENT_DOWN_SET_WITHIN_BUDGET",)),
                ("redeploy", ("TARGET_DIGEST_PINNED", "ISOLATION_VALID")),
                ("verify_daemon", ("TARGET_VERSION_AND_DIGEST_MATCH",)),
                ("return_replica_groups", ("ADMISSION_SCOPE_BOUND",)),
                ("replica_check", ("ACTIVE_CLEAN", "NEW_DEEP_SCRUB_COMPLETE")),
                ("restore_affinity", ("ALL_RETURN_GROUPS_ACCEPTED",)),
                ("wait_stable_window", ("LEDGER_CLEAN",)),
            ):
                steps.append(self._step(sequence, action, resource, *preconditions))
                sequence += 1
        return steps

    def _pa2_steps(self, batch: UpgradeBatchSpec, run: UpgradeRunSpec) -> list[dict[str, Any]]:
        steps = [
            self._step(1, "probe_capabilities", "cluster", "FSID_MATCH"),
            self._step(2, "capture_baseline", "wave", "FRESH_INVENTORY"),
        ]
        sequence = 3
        current_spare = batch.destination_osds[0]
        for source in batch.source_osds:
            resource = f"osd.{source}->osd.{current_spare}"
            for action, preconditions in (
                ("reserve_spare", ("FAILURE_DOMAIN_DISTINCT", "LEASE_OWNED")),
                ("admission_precheck", ("CURRENT_MAPPING_MATCH", "DOWN_SET_WITHIN_BUDGET")),
                ("handoff_replica_groups", ("DESTINATION_REPLICA_ONLY",)),
                ("replica_check", ("ACTIVE_CLEAN", "NEW_DEEP_SCRUB_COMPLETE")),
                ("handoff_commit", ("ALL_HANDOFF_GROUPS_ACCEPTED", "SOURCE_ISOLATED")),
                ("redeploy_source", ("TARGET_DIGEST_PINNED", "MAINTENANCE_GATE_PASS")),
                ("verify_daemon", ("SOURCE_HEALTHY_AND_ISOLATED",)),
                ("reconcile_actual_state", ("NO_GATE_REUSE_FROM_PRIOR_ROTATION",)),
            ):
                steps.append(self._step(sequence, action, resource, *preconditions))
                sequence += 1
            current_spare = source
        steps.append(
            self._step(
                sequence,
                "reconcile_end_state",
                run.pa2_end_state.value if run.pa2_end_state else "missing",
                "VERSION_COVERAGE_COMPLETE",
                "OWNERSHIP_DISPOSITION_RESOLVED",
            )
        )
        steps.append(self._step(sequence + 1, "wait_stable_window", "wave", "LEDGER_CLEAN"))
        return steps
