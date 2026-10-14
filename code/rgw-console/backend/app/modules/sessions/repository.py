from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ...db import connection, json_ready
from ...platform.config import ConfigSnapshot
from .domain import CreateSessionCommand, SessionError


class PostgresSessionRepository:
    def create(
        self,
        *,
        session_id: UUID,
        command: CreateSessionCommand,
        snapshot: ConfigSnapshot,
        actual_fsid: str,
        execution_environment: str,
        capabilities: dict,
    ) -> dict:
        profile_payload = {
            "cluster_id": snapshot.cluster_id,
            "expected_fsid": snapshot.expected_fsid,
            "profile_revision": snapshot.profile_revision,
            "ceph_cluster_name": snapshot.payload.get("ceph_cluster_name"),
            "ceph_transport": snapshot.payload.get("ceph_transport"),
            "deployment_scope": {
                "osds": snapshot.payload.get("upgrade_allowed_osds"),
                "hosts": snapshot.payload.get("upgrade_allowed_hosts"),
                "pools": snapshot.payload.get("upgrade_allowed_pools"),
                "device_classes": snapshot.payload.get("upgrade_allowed_device_classes"),
            },
        }
        profile_hash = hashlib.sha256(
            json.dumps(profile_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        policy_payload = {"revision": snapshot.policy_revision}
        policy_hash = hashlib.sha256(
            json.dumps(policy_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        with connection() as conn, conn.transaction():
            profile = conn.execute(
                """
                SELECT id, config_hash
                FROM cluster_profiles
                WHERE cluster_id = %s AND revision = %s
                FOR UPDATE
                """,
                (snapshot.cluster_id, snapshot.profile_revision),
            ).fetchone()
            if profile is None:
                profile_id = uuid4()
                conn.execute(
                    """
                    INSERT INTO cluster_profiles (
                      id, cluster_id, expected_fsid, revision, profile, config_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        profile_id,
                        snapshot.cluster_id,
                        snapshot.expected_fsid,
                        snapshot.profile_revision,
                        Jsonb(profile_payload),
                        profile_hash,
                    ),
                )
            else:
                profile_id = profile["id"]
                if profile["config_hash"] != profile_hash:
                    raise SessionError(
                        "CLUSTER_PROFILE_MISMATCH",
                        "cluster profile revision was reused with different resolved configuration",
                    )

            policy = conn.execute(
                "SELECT id, policy_hash FROM policy_revisions WHERE revision = %s FOR UPDATE",
                (snapshot.policy_revision,),
            ).fetchone()
            if policy is None:
                policy_id = uuid4()
                conn.execute(
                    """
                    INSERT INTO policy_revisions (id, revision, policy, policy_hash)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (policy_id, snapshot.policy_revision, Jsonb(policy_payload), policy_hash),
                )
            else:
                policy_id = policy["id"]
                if policy["policy_hash"] != policy_hash:
                    raise SessionError(
                        "PLAN_REVISION_CONFLICT",
                        "policy revision was reused with different content",
                    )

            conn.execute(
                """
                INSERT INTO config_snapshots (
                  id, cluster_profile_id, policy_revision_id, cluster_id,
                  expected_fsid, actual_fsid, config_hash, resolved_config
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    snapshot.id,
                    profile_id,
                    policy_id,
                    snapshot.cluster_id,
                    snapshot.expected_fsid,
                    actual_fsid,
                    snapshot.config_hash,
                    Jsonb(snapshot.payload),
                ),
            )
            row = conn.execute(
                """
                INSERT INTO sessions (
                  id, cluster_id, fsid, config_snapshot_id, name, execution_environment
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    session_id,
                    snapshot.cluster_id,
                    actual_fsid,
                    snapshot.id,
                    command.name,
                    execution_environment,
                ),
            ).fetchone()
            for workflow_type in command.workflow_types:
                conn.execute(
                    """
                    INSERT INTO session_workflows (id, session_id, workflow_type, status)
                    VALUES (%s, %s, %s, 'CREATED')
                    """,
                    (uuid4(), session_id, workflow_type),
                )
            observed_at_raw = capabilities.get("observed_at")
            try:
                observed_at = datetime.fromisoformat(
                    str(observed_at_raw).replace("Z", "+00:00")
                )
            except (TypeError, ValueError) as exc:
                raise SessionError(
                    "SCRUB_EVIDENCE_INCOMPLETE",
                    "capability observation timestamp is invalid",
                ) from exc
            for capability_name, capability_state in sorted(
                (capabilities.get("capabilities") or {}).items()
            ):
                conn.execute(
                    """
                    INSERT INTO cluster_capabilities (
                      id, cluster_id, fsid, config_snapshot_id, session_id,
                      capability_name, capability_state, evidence, observed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        snapshot.cluster_id,
                        actual_fsid,
                        snapshot.id,
                        session_id,
                        capability_name,
                        capability_state,
                        Jsonb({"source": capabilities.get("source") or {}}),
                        observed_at,
                    ),
                )
            workflows = self._workflows(conn, session_id)
        result = json_ready(row)
        result["workflows"] = workflows
        result["config_hash"] = snapshot.config_hash
        result["capabilities"] = capabilities.get("capabilities") or {}
        return result

    def get(self, session_id: UUID) -> dict | None:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT s.*, cs.config_hash, cp.revision AS cluster_profile_revision,
                       pr.revision AS policy_revision
                FROM sessions AS s
                JOIN config_snapshots AS cs ON cs.id = s.config_snapshot_id
                JOIN cluster_profiles AS cp ON cp.id = cs.cluster_profile_id
                LEFT JOIN policy_revisions AS pr ON pr.id = cs.policy_revision_id
                WHERE s.id = %s
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            workflows = self._workflows(conn, session_id)
        result = json_ready(row)
        result["workflows"] = workflows
        return result

    def list(self, *, cluster_id: str, limit: int = 100) -> list[dict]:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT s.*, cs.config_hash, cp.revision AS cluster_profile_revision,
                       pr.revision AS policy_revision
                FROM sessions AS s
                JOIN config_snapshots AS cs ON cs.id = s.config_snapshot_id
                JOIN cluster_profiles AS cp ON cp.id = cs.cluster_profile_id
                LEFT JOIN policy_revisions AS pr ON pr.id = cs.policy_revision_id
                WHERE s.cluster_id = %s
                ORDER BY s.created_at DESC, s.id
                LIMIT %s
                """,
                (cluster_id, limit),
            ).fetchall()
            results = []
            for row in rows:
                item = json_ready(row)
                item["workflows"] = self._workflows(conn, row["id"])
                results.append(item)
        return results

    def timeline(self, session_id: UUID) -> list[dict]:
        with connection() as conn:
            present = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM sessions WHERE id = %s) AS present",
                (session_id,),
            ).fetchone()
            if not present["present"]:
                raise SessionError("SESSION_NOT_FOUND", "session does not exist")
            rows = conn.execute(
                """
                SELECT id, schema_version, event_type, stream_key, sequence,
                       cluster_id, fsid, session_id, run_id, occurred_at,
                       observed_at, producer, correlation_id, payload
                FROM outbox_events
                WHERE session_id = %s
                ORDER BY occurred_at, stream_key, sequence
                """,
                (session_id,),
            ).fetchall()
        return [json_ready(row) for row in rows]

    def report(self, session_id: UUID) -> dict:
        with connection() as conn:
            session = conn.execute(
                "SELECT * FROM sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
            if session is None:
                raise SessionError("SESSION_NOT_FOUND", "session does not exist")
            workflows = self._workflows(conn, session_id)
            runs = conn.execute(
                """
                SELECT id, strategy, state, operation_result, preflight_result,
                       created_at, updated_at
                FROM upgrade_runs
                WHERE session_id = %s
                ORDER BY created_at
                """,
                (session_id,),
            ).fetchall()
            qos_runs = conn.execute(
                """
                SELECT id, provider, state, qos_result, requested_proof_level,
                       created_at, started_at, completed_at, updated_at
                FROM qos_runs
                WHERE session_id = %s
                ORDER BY created_at
                """,
                (session_id,),
            ).fetchall()
            evidence = conn.execute(
                """
                SELECT count(*) AS artifact_count,
                       COALESCE(sum(size_bytes), 0) AS total_bytes,
                       max(observed_at) AS latest_observed_at
                FROM evidence_artifacts
                WHERE session_id = %s
                """,
                (session_id,),
            ).fetchone()
        by_type = {item["workflow_type"]: item for item in workflows}
        operation_status = (
            "NOT_REQUESTED"
            if "UPGRADE_PRODUCTION" not in by_type
            else "NOT_EXERCISED"
        )
        if runs:
            explicit = [row["operation_result"] for row in runs if row["operation_result"]]
            operation_status = explicit[-1] if explicit else "NOT_EXERCISED"
        qos_status = (
            "NOT_REQUESTED"
            if "QOS_OBSERVER" not in by_type
            else "NOT_EXERCISED"
        )
        if qos_runs:
            qos_status = qos_runs[-1]["qos_result"]
        limitations = []
        if runs and all(row["operation_result"] == "NOT_EXERCISED" for row in runs):
            limitations.append("DRY_RUN_ONLY_NO_PRODUCTION_MUTATION_EXECUTED")
        return {
            "schema_version": 1,
            "session": json_ready(session),
            "operation_result": {
                "status": operation_status,
                "runs": [json_ready(row) for row in runs],
            },
            "qos_result": {
                "status": qos_status,
                "runs": [json_ready(row) for row in qos_runs],
            },
            "lab_result": {
                "status": by_type.get("LAB_TEST", {}).get("status", "NOT_REQUESTED")
            },
            "rollback_result": (
                {"status": by_type["ROLLBACK"]["status"]}
                if "ROLLBACK" in by_type
                else None
            ),
            "evidence_summary": json_ready(evidence),
            "limitations": limitations,
        }

    @staticmethod
    def _workflows(conn, session_id: UUID) -> list[dict]:
        rows = conn.execute(
            """
            SELECT workflow_type, status, run_id, created_at, updated_at
            FROM session_workflows
            WHERE session_id = %s
            ORDER BY created_at, workflow_type
            """,
            (session_id,),
        ).fetchall()
        return [json_ready(row) for row in rows]
