from __future__ import annotations

from psycopg.types.json import Jsonb

from ...db import connection, json_ready


class AsIsRepository:
    def get(self, collection_id, *, cluster_id, fsid, include_deleted=False):
        with connection() as conn:
            row = conn.execute("""SELECT * FROM as_is_collections
                WHERE id=%s AND cluster_id=%s AND fsid=%s AND (%s OR deleted_at IS NULL)""",
                (collection_id, cluster_id, fsid, include_deleted)).fetchone()
        return json_ready(row) if row else None

    def list(self, *, cluster_id, fsid, daemon_type=None, start=None, end=None,
             phase=None, include_deleted=False, limit=200, before=None, query=None,
             quality=None, daemon_key=None):
        before_at, before_id = before if before else (None, None)
        with connection() as conn:
            rows = conn.execute("""SELECT id,cluster_id,fsid,phase,note,actor,started_at,completed_at,
                quality,daemon_keys,daemon_types,sha256,deleted_at FROM as_is_collections
                WHERE cluster_id=%s AND fsid=%s AND (%s OR deleted_at IS NULL)
                  AND (%s::text IS NULL OR %s=ANY(daemon_types))
                  AND (%s::timestamptz IS NULL OR started_at >= %s)
                  AND (%s::timestamptz IS NULL OR started_at < %s)
                  AND (%s::text IS NULL OR phase=%s)
                  AND (%s::text IS NULL OR quality=%s)
                  AND (%s::text IS NULL OR %s=ANY(daemon_keys))
                  AND (%s::text IS NULL OR strpos(lower(id::text || ' ' || note || ' ' || array_to_string(daemon_keys,' ')),lower(%s)) > 0)
                  AND (%s::timestamptz IS NULL OR (started_at,id) < (%s::timestamptz,%s::uuid))
                ORDER BY started_at DESC,id DESC LIMIT %s""",
                (cluster_id, fsid, include_deleted, daemon_type, daemon_type,
                 start, start, end, end, phase, phase, quality, quality, daemon_key, daemon_key,
                 query, query, before_at, before_at, before_id, limit)).fetchall()
        return [json_ready(row) for row in rows]

    def save(self, payload, *, sha256, request_hash, actor):
        keys = payload['requested_daemon_keys']
        types = sorted({key.split('.', 1)[0] for key in keys})
        with connection() as conn, conn.transaction():
            inserted = conn.execute("""INSERT INTO as_is_collections
                (id,cluster_id,fsid,phase,note,actor,started_at,completed_at,quality,
                 daemon_keys,daemon_types,payload,sha256,request_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING RETURNING id""",
                (payload['id'], payload['cluster_id'], payload['fsid'], payload['phase'],
                 payload['note'], actor, payload['started_at'], payload['completed_at'], payload['quality'],
                 keys, types, Jsonb(payload), sha256, request_hash)).fetchone()
            if inserted:
                conn.execute("""INSERT INTO as_is_collection_events
                    (collection_id,event_type,actor,sha256) VALUES (%s,'CREATED',%s,%s)""",
                    (payload['id'], actor, sha256))

    def set_deleted(self, collection_id, *, cluster_id, fsid, deleted, actor):
        with connection() as conn, conn.transaction():
            row = conn.execute("""SELECT * FROM as_is_collections
                WHERE id=%s AND cluster_id=%s AND fsid=%s FOR UPDATE""",
                (collection_id, cluster_id, fsid)).fetchone()
            if row is None:
                return None
            if bool(row['deleted_at']) != deleted:
                conn.execute("""UPDATE as_is_collections
                    SET deleted_at=CASE WHEN %s THEN now() ELSE NULL END,
                        deleted_by=CASE WHEN %s THEN %s ELSE NULL END WHERE id=%s""",
                    (deleted, deleted, actor, collection_id))
                conn.execute("""INSERT INTO as_is_collection_events
                    (collection_id,event_type,actor,sha256) VALUES (%s,%s,%s,%s)""",
                    (collection_id, 'DELETED' if deleted else 'RESTORED', actor, row['sha256']))
        return self.get(collection_id, cluster_id=cluster_id, fsid=fsid, include_deleted=True)
