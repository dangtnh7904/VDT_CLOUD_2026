from __future__ import annotations

from uuid import UUID

from psycopg.types.json import Jsonb

from ...db import connection, json_ready


class CollectionRepository:
    def get(self, collection_id: UUID, *, cluster_id: str, fsid: str):
        with connection() as conn:
            row = conn.execute("""SELECT * FROM evidence_artifacts WHERE id=%s AND cluster_id=%s
                AND fsid=%s AND evidence_type='cluster_observation' AND access_policy='operator'""",
                (collection_id, cluster_id, fsid)).fetchone()
        return json_ready(row) if row else None

    def list(self, *, cluster_id: str, fsid: str, limit: int):
        with connection() as conn:
            result = conn.execute("""SELECT id, observed_at, metadata, sha256, size_bytes FROM evidence_artifacts
                WHERE cluster_id=%s AND fsid=%s AND evidence_type='cluster_observation' AND access_policy='operator'
                ORDER BY observed_at DESC, id DESC LIMIT %s""", (cluster_id, fsid, limit)).fetchall()
        return [json_ready(row) for row in result]

    def save(self, collection_id: UUID, *, artifact, payload: dict, request_hash: str, actor: str):
        with connection() as conn, conn.transaction():
            conn.execute("""INSERT INTO evidence_artifacts
                (id, cluster_id, fsid, evidence_type, uri, sha256, size_bytes, mime_type, producer, observed_at, metadata)
                VALUES (%s,%s,%s,'cluster_observation',%s,%s,%s,%s,'cluster_metrics',%s,%s)
                ON CONFLICT (id) DO NOTHING""", (collection_id, payload["cluster_id"], payload["fsid"], artifact.uri,
                artifact.sha256, artifact.size_bytes, artifact.mime_type, payload["observed_at"],
                Jsonb({"request_hash": request_hash, "scopes": payload["requested_scopes"], "quality": payload["quality"],
                       "resource_count": len(payload["resources"]), "actor": actor})))
