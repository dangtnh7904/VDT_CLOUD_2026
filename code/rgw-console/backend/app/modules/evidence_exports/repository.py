from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ...db import connection, json_ready
from .rendering import ExportError


class ExportSourceRepository:
    """Only registered references and fixed, bounded read queries are accepted."""

    def artifact(self, artifact_id: UUID) -> dict:
        with connection() as conn, conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '5000ms'")
            row = conn.execute("SELECT * FROM evidence_artifacts WHERE id = %s", (artifact_id,)).fetchone()
        if row is None:
            raise ExportError("EXPORT_SOURCE_NOT_FOUND", "Registered evidence artifact was not found", 404)
        if row["access_policy"] != "operator":
            raise ExportError("EXPORT_SCOPE_REJECTED", "Evidence is not available to the console operator", 403)
        return json_ready(row)

    def run_artifacts(self, run_id: UUID) -> list[dict]:
        with connection() as conn, conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '5000ms'")
            rows = conn.execute(
                """SELECT * FROM evidence_artifacts
                   WHERE run_id = %s AND access_policy = 'operator'
                   ORDER BY observed_at, id LIMIT 33""", (run_id,),
            ).fetchall()
        if len(rows) > 32:
            raise ExportError("EXPORT_LIMIT_EXCEEDED", "Run contains too many artifacts for a synchronous export", 413)
        return [json_ready(row) for row in rows]

    def assert_performance_query_bounded(
        self, *, fsid: str, source: str, scope_type: str, scope: str,
        sample_kind: str, started_at: datetime, ended_at: datetime,
    ) -> None:
        with connection() as conn, conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '5000ms'")
            rows = conn.execute(
                """SELECT captured_at FROM performance_samples
                   WHERE fsid = %s AND source = %s AND scope_type = %s AND scope_id = %s
                     AND sample_kind = %s AND captured_at >= %s AND captured_at <= %s
                   LIMIT 5001""",
                (fsid, source, scope_type, scope, sample_kind, started_at, ended_at),
            ).fetchall()
        if len(rows) > 5000:
            raise ExportError("EXPORT_LIMIT_EXCEEDED", "Metric window contains over 5000 source rows; reduce the window or request rollups", 413)

