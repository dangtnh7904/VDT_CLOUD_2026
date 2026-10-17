from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ...db import connection, json_ready
from ...platform.evidence import StoredArtifact
from .domain import UpgradeBatchSpec, UpgradeRunSpec


class UpgradeRepositoryError(RuntimeError):
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


def _iso(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UpgradeRepositoryError(
            "INVALID_EVIDENCE_TIME",
            "cluster observation timestamp is invalid",
        ) from exc
    if parsed.tzinfo is None:
        raise UpgradeRepositoryError(
            "INVALID_EVIDENCE_TIME",
            "cluster observation timestamp must include a timezone",
        )
    return parsed


class PostgresUpgradeRepository:
    def get_session_context(self, session_id: UUID) -> dict[str, Any]:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT s.*, cs.config_hash, cs.id AS snapshot_id,
                       cs.expected_fsid, cs.actual_fsid
                FROM sessions AS s
                JOIN config_snapshots AS cs ON cs.id = s.config_snapshot_id
                WHERE s.id = %s
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            raise UpgradeRepositoryError("SESSION_NOT_FOUND", "session does not exist")
        return json_ready(row)

    def create_batch(
        self,
        *,
        session_id: UUID,
        spec: UpgradeBatchSpec,
        idempotency_key: str,
        fingerprint: str,
        expected_cluster_id: str,
        expected_fsid: str,
        expected_config_hash: str,
    ) -> dict[str, Any]:
        with connection() as conn, conn.transaction():
            session = conn.execute(
                """
                SELECT s.*, cs.config_hash
                FROM sessions AS s
                JOIN config_snapshots AS cs ON cs.id = s.config_snapshot_id
                WHERE s.id = %s
                FOR UPDATE OF s
                """,
                (session_id,),
            ).fetchone()
            self._assert_session(
                session,
                expected_cluster_id=expected_cluster_id,
                expected_fsid=expected_fsid,
                expected_config_hash=expected_config_hash,
            )
            workflow = conn.execute(
                """
                SELECT status FROM session_workflows
                WHERE session_id = %s AND workflow_type = 'UPGRADE_PRODUCTION'
                """,
                (session_id,),
            ).fetchone()
            if workflow is None:
                raise UpgradeRepositoryError(
                    "CAPABILITY_UNSUPPORTED",
                    "session did not request the production upgrade workflow",
                )
            existing = conn.execute(
                """
                SELECT * FROM upgrade_batches
                WHERE cluster_id = %s AND idempotency_key = %s
                """,
                (expected_cluster_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise UpgradeRepositoryError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key was reused with different batch input",
                    )
                result = json_ready(existing)
                result["replayed"] = True
                return result
            row = conn.execute(
                """
                INSERT INTO upgrade_batches (
                  id, session_id, cluster_id, fsid, config_snapshot_id, name,
                  source_osds, destination_osds, parameters,
                  idempotency_key, request_fingerprint
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    session_id,
                    expected_cluster_id,
                    expected_fsid,
                    session["config_snapshot_id"],
                    spec.name.strip(),
                    list(spec.source_osds),
                    list(spec.destination_osds),
                    Jsonb(spec.parameters.__dict__),
                    idempotency_key,
                    fingerprint,
                ),
            ).fetchone()
            self._append_event(
                conn,
                stream_key=f"session:{session_id}",
                event_type="upgrade.batch.planned",
                cluster_id=expected_cluster_id,
                fsid=expected_fsid,
                session_id=session_id,
                run_id=None,
                producer="upgrade_common",
                payload={"batch_id": str(row["id"]), "dry_run_only": True},
            )
        result = json_ready(row)
        result["replayed"] = False
        return result

    def get_batch(self, batch_id: UUID) -> dict[str, Any]:
        with connection() as conn:
            row = conn.execute("SELECT * FROM upgrade_batches WHERE id = %s", (batch_id,)).fetchone()
        if row is None:
            raise UpgradeRepositoryError("BATCH_NOT_FOUND", "upgrade batch does not exist")
        return json_ready(row)

    def create_run(
        self,
        *,
        batch_id: UUID,
        spec: UpgradeRunSpec,
        idempotency_key: str,
        fingerprint: str,
        expected_cluster_id: str,
        expected_fsid: str,
        expected_config_hash: str,
    ) -> dict[str, Any]:
        with connection() as conn, conn.transaction():
            batch = conn.execute(
                """
                SELECT b.*, cs.config_hash
                FROM upgrade_batches AS b
                JOIN config_snapshots AS cs ON cs.id = b.config_snapshot_id
                WHERE b.id = %s
                FOR UPDATE OF b
                """,
                (batch_id,),
            ).fetchone()
            if batch is None:
                raise UpgradeRepositoryError("BATCH_NOT_FOUND", "upgrade batch does not exist")
            self._assert_scope(
                batch,
                expected_cluster_id=expected_cluster_id,
                expected_fsid=expected_fsid,
                expected_config_hash=expected_config_hash,
            )
            existing = conn.execute(
                """
                SELECT * FROM upgrade_runs
                WHERE cluster_id = %s AND idempotency_key = %s
                """,
                (expected_cluster_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise UpgradeRepositoryError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key was reused with different run input",
                    )
                result = json_ready(existing)
                result["replayed"] = True
                return result
            run_id = uuid4()
            run_config = {
                "source_osds": batch["source_osds"],
                "destination_osds": batch["destination_osds"],
                "parameters": batch["parameters"],
                "target_version": spec.target_version,
                "target_image_digest": spec.target_image_digest,
                "pa2_end_state": spec.pa2_end_state.value if spec.pa2_end_state else None,
            }
            row = conn.execute(
                """
                INSERT INTO upgrade_runs (
                  id, batch_id, session_id, cluster_id, fsid, config_snapshot_id,
                  strategy, execution_mode, target_version, target_image_digest,
                  pa2_end_state, run_config, operation_result,
                  idempotency_key, request_fingerprint
                ) VALUES (
                  %s, %s, %s, %s, %s, %s,
                  %s, 'DRY_RUN', %s, %s, %s, %s, 'NOT_EXERCISED', %s, %s
                )
                RETURNING *
                """,
                (
                    run_id,
                    batch_id,
                    batch["session_id"],
                    expected_cluster_id,
                    expected_fsid,
                    batch["config_snapshot_id"],
                    spec.strategy.value,
                    spec.target_version,
                    spec.target_image_digest,
                    spec.pa2_end_state.value if spec.pa2_end_state else None,
                    Jsonb(run_config),
                    idempotency_key,
                    fingerprint,
                ),
            ).fetchone()
            self._append_event(
                conn,
                stream_key=f"run:{run_id}",
                event_type="upgrade.run.created",
                cluster_id=expected_cluster_id,
                fsid=expected_fsid,
                session_id=batch["session_id"],
                run_id=run_id,
                producer="upgrade_common",
                payload={"strategy": spec.strategy.value, "execution_mode": "DRY_RUN"},
            )
            self._append_phase_event(
                conn,
                run_id=run_id,
                sequence=1,
                cluster_id=expected_cluster_id,
                fsid=expected_fsid,
                session_id=batch["session_id"],
                phase="PLANNING",
                event_type="upgrade.run.created",
                result="NOT_EXERCISED",
                payload={"strategy": spec.strategy.value},
            )
        result = json_ready(row)
        result["replayed"] = False
        return result

    def get_run_context(self, run_id: UUID) -> dict[str, Any]:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT r.*, b.source_osds, b.destination_osds, b.parameters,
                       cs.config_hash, p.plan AS dry_run_plan,
                       p.plan_hash, p.placement_plan_id
                FROM upgrade_runs AS r
                JOIN upgrade_batches AS b ON b.id = r.batch_id
                JOIN config_snapshots AS cs ON cs.id = r.config_snapshot_id
                LEFT JOIN LATERAL (
                    SELECT plan, plan_hash, id AS placement_plan_id
                    FROM placement_plans
                    WHERE run_id = r.id AND plan_revision = r.plan_revision
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                ) AS p ON true
                WHERE r.id = %s
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise UpgradeRepositoryError("RUN_NOT_FOUND", "upgrade run does not exist")
        return json_ready(row)

    def bind_inventory(
        self,
        *,
        run_id: UUID,
        collection: dict[str, Any],
        decision: dict[str, Any],
        idempotency_key: str,
        fingerprint: str,
        expected_state: str,
        plan_revision: int,
        resource_version: int,
        config_snapshot_id: UUID,
        reason: str,
        max_age_seconds: float,
    ) -> dict[str, Any]:
        with connection() as conn, conn.transaction():
            run = conn.execute(
                "SELECT * FROM upgrade_runs WHERE id = %s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if run is None:
                raise UpgradeRepositoryError("RUN_NOT_FOUND", "upgrade run does not exist")
            self._assert_revision(
                run,
                expected_state=expected_state,
                plan_revision=plan_revision,
                resource_version=resource_version,
                config_snapshot_id=config_snapshot_id,
            )
            existing = conn.execute(
                """
                SELECT * FROM upgrade_inventory_bindings
                WHERE cluster_id = %s AND idempotency_key = %s
                """,
                (run["cluster_id"], idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise UpgradeRepositoryError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key was reused with different inventory binding input",
                    )
                result = json_ready(existing)
                result["replayed"] = True
                return result
            observed = decision.get("observed") or {}
            binding_id = uuid4()
            row = conn.execute(
                """
                INSERT INTO upgrade_inventory_bindings (
                  id, run_id, collection_id, cluster_id, fsid, session_id,
                  config_snapshot_id, plan_revision, purpose, artifact_sha256,
                  collected_at, max_age_seconds, readiness_result, reasons,
                  observed, idempotency_key, request_fingerprint, reason
                ) VALUES (
                  %s, %s, %s, %s, %s, %s,
                  %s, %s, 'PLAN_BASELINE', %s,
                  %s, %s, 'READY', %s, %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    binding_id,
                    run_id,
                    collection["id"],
                    run["cluster_id"],
                    run["fsid"],
                    run["session_id"],
                    run["config_snapshot_id"],
                    run["plan_revision"],
                    collection["artifact_sha256"],
                    _iso(collection.get("collected_at")),
                    max_age_seconds,
                    Jsonb(decision.get("reasons") or []),
                    Jsonb(observed),
                    idempotency_key,
                    fingerprint,
                    reason,
                ),
            ).fetchone()
            self._append_event(
                conn,
                stream_key=f"run:{run_id}",
                event_type="upgrade.inventory.bound",
                cluster_id=run["cluster_id"],
                fsid=str(run["fsid"]),
                session_id=run["session_id"],
                run_id=run_id,
                producer="upgrade_common",
                payload={
                    "binding_id": str(binding_id),
                    "collection_id": str(collection["id"]),
                    "artifact_sha256": collection["artifact_sha256"],
                    "plan_revision": run["plan_revision"],
                    "readiness_result": "READY",
                },
            )
        result = json_ready(row)
        result["replayed"] = False
        return result

    def get_inventory_binding(
        self,
        *,
        run_id: UUID,
        plan_revision: int,
    ) -> dict[str, Any] | None:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM upgrade_inventory_bindings
                WHERE run_id = %s AND plan_revision = %s AND purpose = 'PLAN_BASELINE'
                ORDER BY bound_at DESC, id DESC
                LIMIT 1
                """,
                (run_id, plan_revision),
            ).fetchone()
        return json_ready(row) if row is not None else None

    def claim_preflight(
        self,
        *,
        run_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        expected_state: str,
        plan_revision: int,
        resource_version: int,
        config_snapshot_id: UUID,
        reason: str,
    ) -> tuple[UUID | None, dict[str, Any] | None]:
        with connection() as conn, conn.transaction():
            run = conn.execute(
                "SELECT * FROM upgrade_runs WHERE id = %s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if run is None:
                raise UpgradeRepositoryError("RUN_NOT_FOUND", "upgrade run does not exist")
            self._assert_revision(
                run,
                expected_state=expected_state,
                plan_revision=plan_revision,
                resource_version=resource_version,
                config_snapshot_id=config_snapshot_id,
            )
            existing = conn.execute(
                """
                SELECT * FROM action_jobs
                WHERE cluster_id = %s AND idempotency_key = %s
                FOR UPDATE
                """,
                (run["cluster_id"], idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise UpgradeRepositoryError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key was reused with different preflight input",
                    )
                if existing["state"] == "SUCCEEDED":
                    replay = dict(existing["result"] or {})
                    replay["replayed"] = True
                    return None, replay
                if existing["state"] == "FAILED_RETRYABLE":
                    conn.execute(
                        """
                        UPDATE action_jobs
                        SET state = 'RUNNING', attempt_count = attempt_count + 1,
                            error_code = NULL, started_at = now(), completed_at = NULL,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (existing["id"],),
                    )
                    return existing["id"], None
                raise UpgradeRepositoryError(
                    "STATE_CONFLICT",
                    "the preflight request is already in progress or previously failed",
                    retryable=existing["state"] in {"RUNNING", "FAILED_RETRYABLE"},
                    observed_state={"job_id": str(existing["id"]), "state": existing["state"]},
                )
            job_id = uuid4()
            conn.execute(
                """
                INSERT INTO action_jobs (
                  id, cluster_id, fsid, session_id, run_id, action_type, state,
                  idempotency_key, request_fingerprint, expected_state,
                  plan_revision, resource_version, request_payload,
                  attempt_count, started_at
                ) VALUES (
                  %s, %s, %s, %s, %s, 'PREFLIGHT', 'RUNNING',
                  %s, %s, %s, %s, %s, %s, 1, now()
                )
                """,
                (
                    job_id,
                    run["cluster_id"],
                    run["fsid"],
                    run["session_id"],
                    run_id,
                    idempotency_key,
                    fingerprint,
                    expected_state,
                    plan_revision,
                    resource_version,
                    Jsonb({"reason": reason, "config_snapshot_id": str(config_snapshot_id)}),
                ),
            )
        return job_id, None

    def finish_preflight(
        self,
        *,
        job_id: UUID,
        context: dict[str, Any],
        inventory: dict[str, Any],
        capabilities: dict[str, Any],
        plan: dict[str, Any],
        artifact: StoredArtifact,
        plan_hash: str,
        reason: str,
        inventory_binding_id: UUID | None = None,
    ) -> dict[str, Any]:
        observed_at = _iso(inventory.get("observed_at"))
        with connection() as conn, conn.transaction():
            job = conn.execute(
                "SELECT * FROM action_jobs WHERE id = %s FOR UPDATE",
                (job_id,),
            ).fetchone()
            if job is None or job["state"] != "RUNNING":
                raise UpgradeRepositoryError("STATE_CONFLICT", "preflight job is not owned in RUNNING state")
            run = conn.execute(
                "SELECT * FROM upgrade_runs WHERE id = %s FOR UPDATE",
                (context["id"],),
            ).fetchone()
            if run is None:
                raise UpgradeRepositoryError("RUN_NOT_FOUND", "upgrade run does not exist")
            self._assert_revision(
                run,
                expected_state=job["expected_state"],
                plan_revision=job["plan_revision"],
                resource_version=job["resource_version"],
                config_snapshot_id=run["config_snapshot_id"],
            )
            if inventory_binding_id is not None:
                binding = conn.execute(
                    """
                    SELECT id FROM upgrade_inventory_bindings
                    WHERE id = %s AND run_id = %s AND plan_revision = %s
                      AND readiness_result = 'READY'
                    FOR UPDATE
                    """,
                    (inventory_binding_id, run["id"], run["plan_revision"]),
                ).fetchone()
                if binding is None:
                    raise UpgradeRepositoryError(
                        "INVENTORY_BINDING_NOT_READY",
                        "placement plan inventory binding is missing or no longer eligible",
                    )
            conn.execute(
                """
                INSERT INTO evidence_artifacts (
                  id, cluster_id, fsid, session_id, run_id, evidence_type,
                  uri, sha256, size_bytes, mime_type, producer, observed_at, metadata
                ) VALUES (%s, %s, %s, %s, %s, 'PREFLIGHT_SNAPSHOT', %s, %s, %s, %s,
                          'upgrade_common', %s, %s)
                """,
                (
                    artifact.id,
                    run["cluster_id"],
                    run["fsid"],
                    run["session_id"],
                    run["id"],
                    artifact.uri,
                    artifact.sha256,
                    artifact.size_bytes,
                    artifact.mime_type,
                    observed_at,
                    Jsonb({"reason": reason, "plan_revision": run["plan_revision"]}),
                ),
            )
            inventory_id = uuid4()
            conn.execute(
                """
                INSERT INTO cluster_inventory_snapshots (
                  id, cluster_id, fsid, config_snapshot_id, session_id,
                  evidence_artifact_id, osdmap_epoch, quality, observed_at, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    inventory_id,
                    run["cluster_id"],
                    run["fsid"],
                    run["config_snapshot_id"],
                    run["session_id"],
                    artifact.id,
                    inventory.get("osdmap_epoch"),
                    inventory.get("quality") or "INCONCLUSIVE",
                    observed_at,
                    Jsonb(inventory),
                ),
            )
            capability_time = _iso(capabilities.get("observed_at"))
            for capability_name, capability_state in sorted(
                (capabilities.get("capabilities") or {}).items()
            ):
                conn.execute(
                    """
                    INSERT INTO cluster_capabilities (
                      id, cluster_id, fsid, config_snapshot_id, session_id,
                      evidence_artifact_id, capability_name, capability_state,
                      evidence, observed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (
                      config_snapshot_id, session_id, capability_name, observed_at
                    ) DO NOTHING
                    """,
                    (
                        uuid4(),
                        run["cluster_id"],
                        run["fsid"],
                        run["config_snapshot_id"],
                        run["session_id"],
                        artifact.id,
                        capability_name,
                        capability_state,
                        Jsonb({"source": capabilities.get("source") or {}}),
                        capability_time,
                    ),
                )
            plan_id = uuid4()
            conn.execute(
                """
                INSERT INTO placement_plans (
                  id, run_id, cluster_id, fsid, plan_revision,
                  inventory_snapshot_id, osd_inventory_binding_id, plan, plan_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    plan_id,
                    run["id"],
                    run["cluster_id"],
                    run["fsid"],
                    run["plan_revision"],
                    inventory_id,
                    inventory_binding_id,
                    Jsonb(plan),
                    plan_hash,
                ),
            )
            for step in plan.get("steps") or []:
                if not isinstance(step, dict) or not step.get("would_mutate"):
                    continue
                step_sequence = step.get("sequence")
                if isinstance(step_sequence, bool) or not isinstance(step_sequence, int):
                    raise UpgradeRepositoryError(
                        "INVALID_DRY_RUN_PLAN",
                        "dry-run step sequence is invalid",
                    )
                action = str(step.get("action") or "unknown")
                resource = str(step.get("resource") or "unknown")
                conn.execute(
                    """
                    INSERT INTO run_changes (
                      id, cluster_id, fsid, session_id, run_id, sequence,
                      resource_type, resource_id, change_type, ownership_state,
                      desired_state, dependent_steps, disposition
                    ) VALUES (%s, %s, %s, %s, %s, %s,
                              'DRY_RUN_STEP', %s, %s, 'PLANNED', %s, %s, 'OBSERVE_ONLY')
                    """,
                    (
                        uuid4(),
                        run["cluster_id"],
                        run["fsid"],
                        run["session_id"],
                        run["id"],
                        step_sequence,
                        f"{step_sequence}:{resource}",
                        action,
                        Jsonb(step),
                        Jsonb(step.get("preconditions") or []),
                    ),
                )
            next_state = "DRY_RUN_READY" if plan.get("dry_run_result") == "PASS" else "PREFLIGHT_BLOCKED"
            updated = conn.execute(
                """
                UPDATE upgrade_runs
                SET state = %s,
                    preflight_result = %s,
                    operation_result = 'NOT_EXERCISED',
                    resource_version = resource_version + 1,
                    updated_at = now()
                WHERE id = %s AND resource_version = %s
                RETURNING *
                """,
                (next_state, Jsonb(plan), run["id"], run["resource_version"]),
            ).fetchone()
            if updated is None:
                raise UpgradeRepositoryError("STATE_CONFLICT", "run resource version changed during preflight")
            sequence = self._append_event(
                conn,
                stream_key=f"run:{run['id']}",
                event_type="upgrade.preflight.completed",
                cluster_id=run["cluster_id"],
                fsid=str(run["fsid"]),
                session_id=run["session_id"],
                run_id=run["id"],
                producer="upgrade_common",
                payload={
                    "dry_run_result": plan.get("dry_run_result"),
                    "execution_readiness": plan.get("execution_readiness"),
                    "evidence_artifact_id": str(artifact.id),
                    "placement_plan_id": str(plan_id),
                },
            )
            self._append_phase_event(
                conn,
                run_id=run["id"],
                sequence=sequence,
                cluster_id=run["cluster_id"],
                fsid=str(run["fsid"]),
                session_id=run["session_id"],
                phase="PREFLIGHT",
                event_type="upgrade.preflight.completed",
                result=plan.get("dry_run_result"),
                payload={"execution_readiness": plan.get("execution_readiness")},
            )
            result = {
                "run_id": str(run["id"]),
                "job_id": str(job_id),
                "state": next_state,
                "operation_result": "NOT_EXERCISED",
                "dry_run_plan": plan,
                "evidence_refs": [str(artifact.id)],
                "placement_plan_id": str(plan_id),
                "resource_version": updated["resource_version"],
                "replayed": False,
            }
            conn.execute(
                """
                UPDATE action_jobs
                SET state = 'SUCCEEDED', result = %s, completed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (Jsonb(result), job_id),
            )
        return result

    def fail_action(self, job_id: UUID, *, code: str, retryable: bool) -> None:
        state = "FAILED_RETRYABLE" if retryable else "FAILED_FINAL"
        with connection() as conn:
            conn.execute(
                """
                UPDATE action_jobs
                SET state = %s, error_code = %s, completed_at = now(), updated_at = now()
                WHERE id = %s AND state = 'RUNNING'
                """,
                (state, code, job_id),
            )
            conn.commit()

    @staticmethod
    def _assert_session(
        session,
        *,
        expected_cluster_id: str,
        expected_fsid: str,
        expected_config_hash: str,
    ) -> None:
        if session is None:
            raise UpgradeRepositoryError("SESSION_NOT_FOUND", "session does not exist")
        PostgresUpgradeRepository._assert_scope(
            session,
            expected_cluster_id=expected_cluster_id,
            expected_fsid=expected_fsid,
            expected_config_hash=expected_config_hash,
        )
        if session["state"] == "CLOSED":
            raise UpgradeRepositoryError("STATE_CONFLICT", "session is closed")

    @staticmethod
    def _assert_scope(
        row,
        *,
        expected_cluster_id: str,
        expected_fsid: str,
        expected_config_hash: str,
    ) -> None:
        if row["cluster_id"] != expected_cluster_id or str(row["fsid"]) != expected_fsid:
            raise UpgradeRepositoryError(
                "CLUSTER_PROFILE_MISMATCH",
                "resource belongs to a different cluster profile",
            )
        if row["config_hash"] != expected_config_hash:
            raise UpgradeRepositoryError(
                "CLUSTER_PROFILE_MISMATCH",
                "current deployment config does not match the session snapshot",
            )

    @staticmethod
    def _assert_revision(
        run,
        *,
        expected_state: str,
        plan_revision: int,
        resource_version: int,
        config_snapshot_id: UUID,
    ) -> None:
        if run["state"] != expected_state:
            raise UpgradeRepositoryError(
                "STATE_CONFLICT",
                "run state does not match expected_state",
                observed_state={"expected": expected_state, "actual": run["state"]},
            )
        if run["plan_revision"] != plan_revision:
            raise UpgradeRepositoryError("PLAN_REVISION_CONFLICT", "plan revision changed")
        if run["resource_version"] != resource_version:
            raise UpgradeRepositoryError("STATE_CONFLICT", "resource version changed")
        if run["config_snapshot_id"] != config_snapshot_id:
            raise UpgradeRepositoryError("CLUSTER_PROFILE_MISMATCH", "config snapshot does not match run")

    @staticmethod
    def _append_event(
        conn,
        *,
        stream_key: str,
        event_type: str,
        cluster_id: str,
        fsid: str,
        session_id: UUID,
        run_id: UUID | None,
        producer: str,
        payload: dict[str, Any],
    ) -> int:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (stream_key,),
        )
        current = conn.execute(
            "SELECT COALESCE(max(sequence), 0) AS sequence FROM outbox_events WHERE stream_key = %s",
            (stream_key,),
        ).fetchone()
        sequence = int(current["sequence"]) + 1
        now = datetime.now(timezone.utc)
        conn.execute(
            """
            INSERT INTO outbox_events (
              id, event_type, stream_key, sequence, cluster_id, fsid,
              session_id, run_id, occurred_at, observed_at,
              producer, correlation_id, payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                event_type,
                stream_key,
                sequence,
                cluster_id,
                fsid,
                session_id,
                run_id,
                now,
                now,
                producer,
                uuid4(),
                Jsonb(payload),
            ),
        )
        return sequence

    @staticmethod
    def _append_phase_event(
        conn,
        *,
        run_id: UUID,
        sequence: int,
        cluster_id: str,
        fsid: str,
        session_id: UUID,
        phase: str,
        event_type: str,
        result: str | None,
        payload: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc)
        conn.execute(
            """
            INSERT INTO phase_events (
              id, cluster_id, fsid, session_id, run_id, sequence,
              phase, event_type, result, occurred_at, observed_at, payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                cluster_id,
                fsid,
                session_id,
                run_id,
                sequence,
                phase,
                event_type,
                result,
                now,
                now,
                Jsonb(payload),
            ),
        )
