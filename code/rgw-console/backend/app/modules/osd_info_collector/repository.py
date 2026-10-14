from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ...db import connection, json_ready
from ...platform.evidence import StoredArtifact
from .domain import OsdInfoError, ValidatedCollection


class PostgresOsdInfoRepository:
    def claim(
        self,
        *,
        session_id: UUID,
        phase: str,
        requested_osd_ids: tuple[int, ...],
        idempotency_key: str,
        fingerprint: str,
        expected_cluster_id: str,
        expected_fsid: str,
        expected_config_hash: str,
    ) -> tuple[UUID | None, dict[str, Any] | None]:
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
            if session is None:
                raise OsdInfoError("SESSION_NOT_FOUND", "session does not exist")
            if session["state"] == "CLOSED":
                raise OsdInfoError("STATE_CONFLICT", "session is closed")
            if session["cluster_id"] != expected_cluster_id or str(session["fsid"]) != expected_fsid:
                raise OsdInfoError("CLUSTER_PROFILE_MISMATCH", "session belongs to a different cluster profile")
            if session["config_hash"] != expected_config_hash:
                raise OsdInfoError("CLUSTER_PROFILE_MISMATCH", "current configuration differs from the session snapshot")
            existing = conn.execute(
                "SELECT * FROM action_jobs WHERE cluster_id = %s AND idempotency_key = %s FOR UPDATE",
                (expected_cluster_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint or existing["action_type"] != "OSD_INFO_COLLECTION":
                    raise OsdInfoError("IDEMPOTENCY_CONFLICT", "idempotency key was reused with different input")
                if existing["state"] == "SUCCEEDED" and existing["result"] is not None:
                    replay = json_ready(existing["result"])
                    replay["replayed"] = True
                    return None, replay
                raise OsdInfoError(
                    "IDEMPOTENCY_IN_PROGRESS" if existing["state"] in {"PENDING", "RUNNING", "RECONCILING"} else "IDEMPOTENCY_TERMINAL",
                    "the same collection is already running" if existing["state"] in {"PENDING", "RUNNING", "RECONCILING"} else "the previous collection attempt is terminal",
                    retryable=existing["state"] in {"PENDING", "RUNNING", "RECONCILING", "FAILED_RETRYABLE"},
                    observed_state={"state": existing["state"]},
                )
            job_id = uuid4()
            collection_id = uuid4()
            request_payload = {"phase": phase, "osd_ids": list(requested_osd_ids)}
            conn.execute(
                """
                INSERT INTO action_jobs (
                  id, cluster_id, fsid, session_id, action_type, state,
                  idempotency_key, request_fingerprint, request_payload,
                  attempt_count, started_at
                ) VALUES (%s, %s, %s, %s, 'OSD_INFO_COLLECTION', 'RUNNING',
                          %s, %s, %s, 1, now())
                """,
                (
                    job_id, expected_cluster_id, expected_fsid, session_id,
                    idempotency_key, fingerprint, Jsonb(request_payload),
                ),
            )
            conn.execute(
                """
                INSERT INTO osd_inventory_collections (
                  id, action_job_id, cluster_id, fsid, config_snapshot_id,
                  session_id, phase, state, requested_osd_ids
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'RUNNING', %s)
                """,
                (
                    collection_id, job_id, expected_cluster_id, expected_fsid,
                    session["config_snapshot_id"], session_id, phase, list(requested_osd_ids),
                ),
            )
        return collection_id, None

    def finish(
        self,
        collection_id: UUID,
        *,
        validated: ValidatedCollection,
        artifact: StoredArtifact,
    ) -> dict[str, Any]:
        with connection() as conn, conn.transaction():
            collection = conn.execute(
                "SELECT * FROM osd_inventory_collections WHERE id = %s FOR UPDATE",
                (collection_id,),
            ).fetchone()
            if collection is None or collection["state"] != "RUNNING":
                raise OsdInfoError("STATE_CONFLICT", "collection is not owned in RUNNING state")
            conn.execute(
                """
                INSERT INTO evidence_artifacts (
                  id, cluster_id, fsid, session_id, run_id, evidence_type,
                  uri, sha256, size_bytes, mime_type, producer, observed_at, metadata
                ) VALUES (%s, %s, %s, %s, NULL, 'OSD_INFO_COLLECTION',
                          %s, %s, %s, %s, 'osd_info_collector', %s, %s)
                """,
                (
                    artifact.id, collection["cluster_id"], collection["fsid"],
                    collection["session_id"], artifact.uri, artifact.sha256,
                    artifact.size_bytes, artifact.mime_type, validated.collected_at,
                    Jsonb({
                        "collection_id": str(collection_id),
                        "phase": collection["phase"],
                        "collector_version": validated.collector_version,
                        "quality": validated.quality.value,
                    }),
                ),
            )
            for record in validated.records:
                conn.execute(
                    """
                    INSERT INTO osd_inventory_records (
                      collection_id, osd_id, quality, warnings, errors,
                      osd_fsid, hostname, crush_location, device_class,
                      public_ip, public_ips, cluster_ip, cluster_ips,
                      data_device_path, data_device_size_bytes, physical_devices,
                      db_device_path, db_device_size_bytes, db_physical_devices,
                      wal_device_path, wal_device_size_bytes, wal_physical_devices,
                      device_ids,
                      total_bytes, used_bytes, available_bytes, used_percent,
                      pg_count, primary_count, up, in_cluster, daemon_status,
                      crush_weight, reweight, primary_affinity,
                      ceph_version, ceph_version_short,
                      container_image, container_image_id, payload
                    ) VALUES (
                      %s, %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s,
                      %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s,
                      %s, %s, %s
                    )
                    """,
                    (
                        collection_id, record["osd_id"], record["quality"],
                        Jsonb(record["warnings"]), Jsonb(record["errors"]),
                        record["osd_fsid"], record["hostname"],
                        Jsonb(record["crush_location"]), record["device_class"],
                        record["public_ip"], Jsonb(record["public_ips"]),
                        record["cluster_ip"], Jsonb(record["cluster_ips"]),
                        record["data_device_path"], record["data_device_size_bytes"],
                        Jsonb(record["physical_devices"]), record["db_device_path"],
                        record["db_device_size_bytes"], Jsonb(record["db_physical_devices"]),
                        record["wal_device_path"], record["wal_device_size_bytes"],
                        Jsonb(record["wal_physical_devices"]), Jsonb(record["device_ids"]),
                        record["total_bytes"],
                        record["used_bytes"], record["available_bytes"], record["used_percent"],
                        record["pg_count"], record["primary_count"], record["up"],
                        record["in"], record["daemon_status"], record["crush_weight"],
                        record["reweight"], record["primary_affinity"],
                        record["ceph_version"], record["ceph_version_short"],
                        record["container_image"], record["container_image_id"],
                        Jsonb(record["payload"]),
                    ),
                )
            conn.execute(
                """
                UPDATE osd_inventory_collections
                SET state = 'COMPLETE', quality = %s, collector_version = %s,
                    evidence_artifact_id = %s, artifact_sha256 = %s,
                    osd_count = %s, collected_at = %s,
                    health_status = %s, health_checks = %s,
                    osdmap_epoch = %s, cluster_flags = %s,
                    pool_summaries = %s, version_summary = %s,
                    cluster_pg_count = %s, cluster_osd_count = %s,
                    cluster_up_osd_count = %s, cluster_in_osd_count = %s,
                    completed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (
                    validated.quality.value, validated.collector_version, artifact.id,
                    artifact.sha256, len(validated.records), validated.collected_at,
                    validated.cluster_summary["health_status"],
                    Jsonb(validated.cluster_summary["health_checks"]),
                    validated.cluster_summary["osdmap_epoch"],
                    Jsonb(validated.cluster_summary["cluster_flags"]),
                    Jsonb(validated.cluster_summary["pool_summaries"]),
                    Jsonb(validated.cluster_summary["version_summary"]),
                    validated.cluster_summary["cluster_pg_count"],
                    validated.cluster_summary["cluster_osd_count"],
                    validated.cluster_summary["cluster_up_osd_count"],
                    validated.cluster_summary["cluster_in_osd_count"],
                    collection_id,
                ),
            )
            result = self._get(conn, collection_id)
            result["replayed"] = False
            conn.execute(
                """
                UPDATE action_jobs
                SET state = 'SUCCEEDED', result = %s, completed_at = now(), updated_at = now()
                WHERE id = %s AND state = 'RUNNING'
                """,
                (Jsonb(result), collection["action_job_id"]),
            )
            self._append_event(
                conn,
                collection=collection,
                quality=validated.quality.value,
                observed_at=validated.collected_at,
                artifact=artifact,
            )
        return result

    def fail(self, collection_id: UUID, *, code: str, message: str, retryable: bool) -> None:
        with connection() as conn, conn.transaction():
            collection = conn.execute(
                "SELECT action_job_id FROM osd_inventory_collections WHERE id = %s FOR UPDATE",
                (collection_id,),
            ).fetchone()
            if collection is None:
                return
            conn.execute(
                """
                UPDATE osd_inventory_collections
                SET state = 'FAILED', error_code = %s, error_message = %s,
                    completed_at = now(), updated_at = now()
                WHERE id = %s AND state = 'RUNNING'
                """,
                (code, message[:1000], collection_id),
            )
            conn.execute(
                """
                UPDATE action_jobs
                SET state = %s, error_code = %s, completed_at = now(), updated_at = now()
                WHERE id = %s AND state = 'RUNNING'
                """,
                ("FAILED_RETRYABLE" if retryable else "FAILED_FINAL", code, collection["action_job_id"]),
            )

    def get(self, collection_id: UUID) -> dict[str, Any]:
        with connection() as conn:
            return self._get(conn, collection_id)

    def list(self, *, session_id: UUID, limit: int) -> dict[str, Any]:
        with connection() as conn:
            session = conn.execute(
                "SELECT id FROM sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
            if session is None:
                raise OsdInfoError("SESSION_NOT_FOUND", "session does not exist")
            rows = conn.execute(
                """
                SELECT c.*, a.uri AS evidence_uri, a.size_bytes AS evidence_size_bytes
                FROM osd_inventory_collections AS c
                LEFT JOIN evidence_artifacts AS a ON a.id = c.evidence_artifact_id
                WHERE c.session_id = %s
                ORDER BY c.created_at DESC, c.id
                LIMIT %s
                """,
                (session_id, limit),
            ).fetchall()
        return {
            "schema_version": 1,
            "session_id": str(session_id),
            "items": [json_ready(row) for row in rows],
        }

    def get_osd(self, collection_id: UUID, osd_id: int) -> dict[str, Any]:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT r.*, c.cluster_id, c.fsid, c.phase, c.collected_at,
                       c.evidence_artifact_id, c.artifact_sha256,
                       a.uri AS evidence_uri, a.size_bytes AS evidence_size_bytes
                FROM osd_inventory_records AS r
                JOIN osd_inventory_collections AS c ON c.id = r.collection_id
                JOIN evidence_artifacts AS a ON a.id = c.evidence_artifact_id
                WHERE r.collection_id = %s AND r.osd_id = %s
                """,
                (collection_id, osd_id),
            ).fetchone()
        if row is None:
            raise OsdInfoError("OSD_INVENTORY_NOT_FOUND", "OSD inventory record does not exist")
        result = json_ready(row)
        result["in"] = result.pop("in_cluster")
        return result

    @staticmethod
    def _get(conn, collection_id: UUID) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT c.*, a.uri AS evidence_uri, a.size_bytes AS evidence_size_bytes
            FROM osd_inventory_collections AS c
            LEFT JOIN evidence_artifacts AS a ON a.id = c.evidence_artifact_id
            WHERE c.id = %s
            """,
            (collection_id,),
        ).fetchone()
        if row is None:
            raise OsdInfoError("OSD_INVENTORY_NOT_FOUND", "OSD inventory collection does not exist")
        result = json_ready(row)
        records = conn.execute(
            """
            SELECT osd_id, quality, warnings, osd_fsid, hostname,
                   crush_location, device_class,
                   public_ip, public_ips, cluster_ip, cluster_ips,
                   data_device_path, data_device_size_bytes, physical_devices,
                   db_device_path, db_device_size_bytes, db_physical_devices,
                   wal_device_path, wal_device_size_bytes, wal_physical_devices,
                   device_ids, total_bytes, used_bytes,
                   available_bytes, used_percent, pg_count, primary_count,
                   up, in_cluster, daemon_status, crush_weight, reweight,
                   primary_affinity, ceph_version, ceph_version_short,
                   container_image, container_image_id
            FROM osd_inventory_records
            WHERE collection_id = %s
            ORDER BY osd_id
            """,
            (collection_id,),
        ).fetchall()
        result["osds"] = []
        for item in records:
            record = json_ready(item)
            record["in"] = record.pop("in_cluster")
            result["osds"].append(record)
        return result

    @staticmethod
    def _append_event(
        conn,
        *,
        collection,
        quality: str,
        observed_at: datetime,
        artifact: StoredArtifact,
    ) -> None:
        stream_key = f"osd-inventory:{collection['id']}"
        now = datetime.now(timezone.utc)
        conn.execute(
            """
            INSERT INTO outbox_events (
              id, event_type, stream_key, sequence, cluster_id, fsid,
              session_id, occurred_at, observed_at, producer, correlation_id, payload
            ) VALUES (%s, 'osd.inventory.collected', %s, 1, %s, %s,
                      %s, %s, %s, 'osd_info_collector', %s, %s)
            """,
            (
                uuid4(), stream_key, collection["cluster_id"], collection["fsid"],
                collection["session_id"], now, observed_at, collection["id"],
                Jsonb({
                    "collection_id": str(collection["id"]),
                    "phase": collection["phase"],
                    "quality": quality,
                    "artifact_id": str(artifact.id),
                    "artifact_sha256": artifact.sha256,
                }),
            ),
        )
