from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ...config import Settings
from ...platform.config import build_config_snapshot, resolve_settings
from ...platform.evidence import FilesystemArtifactStore
from ...services.idempotency import canonical_request_fingerprint
from ..cluster_profiles.domain import ClusterReadError
from ..cluster_profiles.ports import ClusterObservationPort
from ..cluster_profiles.service import ClusterProfileService
from .down_set_assessment import DownSetInventoryAssessmentService
from .domain import (
    BatchParameters,
    DryRunPlanner,
    Pa2EndState,
    Strategy,
    UpgradeBatchSpec,
    UpgradeDomainError,
    UpgradeRunSpec,
    evaluate_inventory_binding,
)
from .ports import OsdInventoryQueryPort
from .repository import PostgresUpgradeRepository, UpgradeRepositoryError


IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class UpgradeApplicationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        observed_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.observed_state = observed_state or {}


@dataclass(frozen=True)
class PreflightEnvelope:
    expected_state: str
    plan_revision: int
    config_snapshot_id: UUID
    resource_version: int
    reason: str

    def __post_init__(self) -> None:
        if self.expected_state != "CREATED":
            raise UpgradeApplicationError(
                "STATE_CONFLICT",
                "first dry-run preflight must expect the CREATED state",
            )
        if self.plan_revision < 1 or self.resource_version < 1:
            raise UpgradeApplicationError(
                "INVALID_REQUEST",
                "plan_revision and resource_version must be positive",
            )
        if not self.reason.strip() or len(self.reason.strip()) > 1000:
            raise UpgradeApplicationError(
                "INVALID_REQUEST",
                "operator reason must contain 1 to 1000 characters",
            )


@dataclass(frozen=True)
class InventoryBindingEnvelope:
    collection_id: UUID
    expected_state: str
    plan_revision: int
    config_snapshot_id: UUID
    resource_version: int
    reason: str

    def __post_init__(self) -> None:
        if self.expected_state != "CREATED":
            raise UpgradeApplicationError(
                "STATE_CONFLICT",
                "plan baseline binding must expect the CREATED state",
            )
        if self.plan_revision < 1 or self.resource_version < 1:
            raise UpgradeApplicationError(
                "INVALID_REQUEST",
                "plan_revision and resource_version must be positive",
            )
        if not self.reason.strip() or len(self.reason.strip()) > 1000:
            raise UpgradeApplicationError(
                "INVALID_REQUEST",
                "operator reason must contain 1 to 1000 characters",
            )


@dataclass(frozen=True)
class DownSetInventoryEnvelope:
    collection_id: UUID
    target_osd_ids: tuple[int, ...]
    expected_state: str
    plan_revision: int
    config_snapshot_id: UUID
    resource_version: int

    def __post_init__(self) -> None:
        if not self.expected_state.strip() or len(self.expected_state) > 64:
            raise UpgradeApplicationError("INVALID_REQUEST", "expected_state is required")
        if self.plan_revision < 1 or self.resource_version < 1:
            raise UpgradeApplicationError(
                "INVALID_REQUEST",
                "plan_revision and resource_version must be positive",
            )
        if not self.target_osd_ids or len(self.target_osd_ids) > 128:
            raise UpgradeApplicationError(
                "INVALID_REQUEST",
                "target_osd_ids must contain 1 to 128 OSD IDs",
            )
        if len(set(self.target_osd_ids)) != len(self.target_osd_ids) or any(
            osd_id < 0 for osd_id in self.target_osd_ids
        ):
            raise UpgradeApplicationError(
                "INVALID_REQUEST",
                "target_osd_ids must be unique non-negative integers",
            )


class UpgradeApplicationService:
    def __init__(
        self,
        settings: Settings,
        repository: PostgresUpgradeRepository,
        observations: ClusterObservationPort | None = None,
        inventory_query: OsdInventoryQueryPort | None = None,
    ) -> None:
        self.settings = resolve_settings(settings)
        self.repository = repository
        self.observations = observations
        self.inventory_query = inventory_query

    def create_batch(
        self,
        *,
        session_id: UUID,
        spec: UpgradeBatchSpec,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_upgrade_enabled()
        self._validate_idempotency_key(idempotency_key)
        snapshot = build_config_snapshot(self.settings)
        fingerprint = canonical_request_fingerprint(
            "POST",
            "/api/v1/upgrade-batches",
            {
                "session_id": str(session_id),
                "name": spec.name.strip(),
                "source_osds": list(spec.source_osds),
                "destination_osds": list(spec.destination_osds),
                "parameters": spec.parameters.__dict__,
            },
        )
        return self.repository.create_batch(
            session_id=session_id,
            spec=spec,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            expected_cluster_id=self.settings.cluster_id,
            expected_fsid=self._expected_fsid(),
            expected_config_hash=snapshot.config_hash,
        )

    def get_batch(self, batch_id: UUID) -> dict[str, Any]:
        return self.repository.get_batch(batch_id)

    def create_run(
        self,
        *,
        batch_id: UUID,
        spec: UpgradeRunSpec,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_upgrade_enabled()
        self._validate_idempotency_key(idempotency_key)
        snapshot = build_config_snapshot(self.settings)
        fingerprint = canonical_request_fingerprint(
            "POST",
            "/api/v1/upgrade-runs",
            {
                "batch_id": str(batch_id),
                "strategy": spec.strategy.value,
                "target_version": spec.target_version,
                "target_image_digest": spec.target_image_digest,
                "pa2_end_state": spec.pa2_end_state.value if spec.pa2_end_state else None,
                "execution_mode": "DRY_RUN",
            },
        )
        return self.repository.create_run(
            batch_id=batch_id,
            spec=spec,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            expected_cluster_id=self.settings.cluster_id,
            expected_fsid=self._expected_fsid(),
            expected_config_hash=snapshot.config_hash,
        )

    def get_run(self, run_id: UUID) -> dict[str, Any]:
        return self.repository.get_run_context(run_id)

    def bind_inventory(
        self,
        *,
        run_id: UUID,
        envelope: InventoryBindingEnvelope,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_upgrade_enabled()
        self._validate_idempotency_key(idempotency_key)
        if self.inventory_query is None:
            raise UpgradeApplicationError(
                "CAPABILITY_UNSUPPORTED",
                "OSD inventory query adapter is required for plan binding",
            )
        context = self.repository.get_run_context(run_id)
        snapshot = build_config_snapshot(self.settings)
        self._assert_context(context, snapshot.config_hash)
        try:
            collection = self.inventory_query.get_collection(envelope.collection_id)
        except Exception as exc:
            raise self._translate(exc) from exc
        decision = evaluate_inventory_binding(
            context,
            collection,
            now=datetime.now(timezone.utc),
            max_age_seconds=self.settings.upgrade_inventory_max_age_seconds,
            clock_skew_seconds=self.settings.telemetry_clock_skew_max_seconds,
        )
        if decision.result != "READY":
            raise UpgradeApplicationError(
                "INVENTORY_BINDING_NOT_READY",
                "OSD inventory collection is not eligible for this plan",
                observed_state=decision.to_dict(),
            )
        fingerprint = canonical_request_fingerprint(
            "POST",
            f"/api/v1/upgrade-runs/{run_id}/inventory-bindings",
            {
                "collection_id": str(envelope.collection_id),
                "expected_state": envelope.expected_state,
                "plan_revision": envelope.plan_revision,
                "config_snapshot_id": str(envelope.config_snapshot_id),
                "resource_version": envelope.resource_version,
                "reason": envelope.reason.strip(),
            },
        )
        return self.repository.bind_inventory(
            run_id=run_id,
            collection=collection,
            decision=decision.to_dict(),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            expected_state=envelope.expected_state,
            plan_revision=envelope.plan_revision,
            resource_version=envelope.resource_version,
            config_snapshot_id=envelope.config_snapshot_id,
            reason=envelope.reason.strip(),
            max_age_seconds=self.settings.upgrade_inventory_max_age_seconds,
        )

    def inventory_readiness(self, run_id: UUID) -> dict[str, Any]:
        self._require_upgrade_enabled()
        if self.inventory_query is None:
            raise UpgradeApplicationError(
                "CAPABILITY_UNSUPPORTED",
                "OSD inventory query adapter is required for readiness evaluation",
            )
        context = self.repository.get_run_context(run_id)
        snapshot = build_config_snapshot(self.settings)
        self._assert_context(context, snapshot.config_hash)
        binding = self.repository.get_inventory_binding(
            run_id=run_id,
            plan_revision=context["plan_revision"],
        )
        if binding is None:
            return {
                "schema_version": 1,
                "run_id": str(run_id),
                "plan_revision": context["plan_revision"],
                "result": "INCONCLUSIVE",
                "reasons": ["OSD_INFO_BASELINE_NOT_BOUND"],
                "observed": {
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                    "max_age_seconds": self.settings.upgrade_inventory_max_age_seconds,
                },
                "binding": None,
            }
        try:
            collection = self.inventory_query.get_collection(UUID(str(binding["collection_id"])))
        except Exception as exc:
            raise self._translate(exc) from exc
        decision = evaluate_inventory_binding(
            context,
            collection,
            now=datetime.now(timezone.utc),
            max_age_seconds=self.settings.upgrade_inventory_max_age_seconds,
            clock_skew_seconds=self.settings.telemetry_clock_skew_max_seconds,
        ).to_dict()
        return {
            "schema_version": 1,
            "run_id": str(run_id),
            "plan_revision": context["plan_revision"],
            **decision,
            "binding": binding,
        }

    def assess_down_set_inventory(
        self,
        *,
        run_id: UUID,
        envelope: DownSetInventoryEnvelope,
    ) -> dict[str, Any]:
        """Evaluate fresh collector evidence without authorizing mutation."""
        self._require_upgrade_enabled()
        if self.inventory_query is None:
            raise UpgradeApplicationError(
                "CAPABILITY_UNSUPPORTED",
                "OSD inventory query adapter is required for down-set assessment",
            )
        context = self.repository.get_run_context(run_id)
        snapshot = build_config_snapshot(self.settings)
        self._assert_context(context, snapshot.config_hash)
        try:
            collection = self.inventory_query.get_collection(envelope.collection_id)
        except Exception as exc:
            raise self._translate(exc) from exc

        evaluator = DownSetInventoryAssessmentService(
            load_run=lambda _: context,
            load_collection=lambda _: collection,
            allowed_osd_ids=self._allowed_osd_ids(),
            max_age_seconds=self.settings.upgrade_inventory_max_age_seconds,
            clock_skew_seconds=self.settings.telemetry_clock_skew_max_seconds,
            now=lambda: datetime.now(timezone.utc),
        )
        return {
            "schema_version": 1,
            **evaluator.assess(
                run_id=str(run_id),
                collection_id=str(envelope.collection_id),
                target_osd_ids=envelope.target_osd_ids,
                expected_state=envelope.expected_state,
                expected_plan_revision=envelope.plan_revision,
                expected_config_snapshot_id=str(envelope.config_snapshot_id),
                expected_resource_version=envelope.resource_version,
            ),
        }

    def preflight(
        self,
        *,
        run_id: UUID,
        envelope: PreflightEnvelope,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_upgrade_enabled()
        self._validate_idempotency_key(idempotency_key)
        if self.observations is None:
            raise UpgradeApplicationError(
                "CAPABILITY_UNSUPPORTED",
                "cluster observation adapter is required for preflight",
            )
        context = self.repository.get_run_context(run_id)
        snapshot = build_config_snapshot(self.settings)
        self._assert_context(context, snapshot.config_hash)
        fingerprint = canonical_request_fingerprint(
            "POST",
            f"/api/v1/upgrade-runs/{run_id}/preflight",
            {
                "expected_state": envelope.expected_state,
                "plan_revision": envelope.plan_revision,
                "config_snapshot_id": str(envelope.config_snapshot_id),
                "resource_version": envelope.resource_version,
                "reason": envelope.reason.strip(),
            },
        )
        job_id, replay = self.repository.claim_preflight(
            run_id=run_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            expected_state=envelope.expected_state,
            plan_revision=envelope.plan_revision,
            resource_version=envelope.resource_version,
            config_snapshot_id=envelope.config_snapshot_id,
            reason=envelope.reason.strip(),
        )
        if replay is not None:
            return replay
        assert job_id is not None
        try:
            cluster = ClusterProfileService(self.settings, self.observations)
            capabilities = cluster.capabilities()
            inventory = cluster.inventory()
            batch = UpgradeBatchSpec(
                name="persisted-batch",
                source_osds=tuple(context["source_osds"]),
                destination_osds=tuple(context["destination_osds"]),
                parameters=BatchParameters(**context["parameters"]),
            )
            run = UpgradeRunSpec(
                strategy=Strategy(context["strategy"]),
                target_version=context["target_version"],
                target_image_digest=context["target_image_digest"],
                pa2_end_state=(
                    Pa2EndState(context["pa2_end_state"])
                    if context.get("pa2_end_state")
                    else None
                ),
            )
            plan = DryRunPlanner().build(
                batch,
                run,
                inventory=inventory,
                capabilities=capabilities,
                expected_fsid=self._expected_fsid(),
            ).to_dict()
            inventory_readiness = self.inventory_readiness(run_id)
            plan["osd_inventory_binding"] = inventory_readiness
            inventory_binding_id = None
            if inventory_readiness["result"] == "READY":
                inventory_binding_id = UUID(str(inventory_readiness["binding"]["id"]))
            else:
                plan["execution_readiness"] = "BLOCKED"
                plan["warnings"] = sorted(
                    set(plan.get("warnings") or [])
                    | {f"OSD_INFO_BASELINE_NOT_READY:{inventory_readiness['result']}"}
                )
            evidence_payload = {
                "schema_version": 1,
                "kind": "PREFLIGHT_SNAPSHOT",
                "cluster_id": self.settings.cluster_id,
                "fsid": self._expected_fsid(),
                "session_id": str(context["session_id"]),
                "run_id": str(run_id),
                "config_hash": snapshot.config_hash,
                "inventory": inventory,
                "capabilities": capabilities,
                "dry_run_plan": plan,
            }
            artifact = FilesystemArtifactStore(
                self.settings.evidence_root,
                max_artifact_bytes=self.settings.evidence_max_artifact_bytes,
            ).put_json(
                evidence_payload,
                cluster_id=self.settings.cluster_id,
                session_id=context["session_id"],
                run_id=run_id,
            )
            plan_hash = hashlib.sha256(
                json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            return self.repository.finish_preflight(
                job_id=job_id,
                context=context,
                inventory=inventory,
                capabilities=capabilities,
                plan=plan,
                artifact=artifact,
                plan_hash=plan_hash,
                reason=envelope.reason.strip(),
                inventory_binding_id=inventory_binding_id,
            )
        except (ClusterReadError, UpgradeRepositoryError, UpgradeDomainError) as exc:
            retryable = bool(getattr(exc, "retryable", False))
            self.repository.fail_action(job_id, code=getattr(exc, "code", "PREFLIGHT_FAILED"), retryable=retryable)
            raise self._translate(exc) from exc
        except Exception:
            self.repository.fail_action(job_id, code="PREFLIGHT_FAILED", retryable=False)
            raise

    def _assert_context(self, context: dict[str, Any], config_hash: str) -> None:
        if context["cluster_id"] != self.settings.cluster_id:
            raise UpgradeApplicationError(
                "CLUSTER_PROFILE_MISMATCH",
                "run belongs to a different cluster ID",
            )
        if str(context["fsid"]) != self._expected_fsid():
            raise UpgradeApplicationError(
                "CLUSTER_PROFILE_MISMATCH",
                "run belongs to a different cluster FSID",
            )
        if context["config_hash"] != config_hash:
            raise UpgradeApplicationError(
                "CLUSTER_PROFILE_MISMATCH",
                "current deployment config does not match the run snapshot",
            )

    def _require_upgrade_enabled(self) -> None:
        if not self.settings.feature_upgrade:
            raise UpgradeApplicationError(
                "CAPABILITY_UNSUPPORTED",
                "upgrade workspace is disabled",
            )
        if not self.settings.cluster_id or not self.settings.ceph_expected_fsid:
            raise UpgradeApplicationError(
                "CLUSTER_PROFILE_MISMATCH",
                "CLUSTER_ID and CEPH_EXPECTED_FSID are required",
            )

    def _expected_fsid(self) -> str:
        assert self.settings.ceph_expected_fsid is not None
        return self.settings.ceph_expected_fsid

    def _allowed_osd_ids(self) -> tuple[int, ...]:
        result: set[int] = set()
        for value in self.settings.upgrade_allowed_osd_set:
            normalized = value[4:] if value.startswith("osd.") else value
            if not normalized.isdigit():
                raise UpgradeApplicationError(
                    "SCOPE_NOT_ALLOWED",
                    "UPGRADE_ALLOWED_OSDS must contain numeric OSD IDs",
                )
            result.add(int(normalized))
        if not result:
            raise UpgradeApplicationError(
                "SCOPE_NOT_ALLOWED",
                "UPGRADE_ALLOWED_OSDS must not be empty",
            )
        return tuple(sorted(result))

    @staticmethod
    def _validate_idempotency_key(value: str) -> None:
        if not IDEMPOTENCY_KEY_RE.fullmatch(value):
            raise UpgradeApplicationError(
                "INVALID_IDEMPOTENCY_KEY",
                "Idempotency-Key must contain 8 to 128 safe characters",
            )

    @staticmethod
    def _translate(exc: Exception) -> UpgradeApplicationError:
        return UpgradeApplicationError(
            getattr(exc, "code", "UPGRADE_ERROR"),
            getattr(exc, "message", str(exc)),
            retryable=bool(getattr(exc, "retryable", False)),
            observed_state=getattr(exc, "observed_state", {}),
        )
