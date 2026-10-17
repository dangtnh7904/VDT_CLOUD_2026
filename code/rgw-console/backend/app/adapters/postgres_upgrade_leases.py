from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from ..db import connection
from ..platform.leases import LeaseConflict, LeaseToken


class PostgresUpgradeLeaseRepository:
    """Transactional cluster/resource lease with monotonically increasing fences."""

    def claim(
        self,
        *,
        cluster_id: str,
        resource_type: str,
        resource_id: str,
        owner_run_id: UUID,
        ttl_seconds: int,
    ) -> LeaseToken:
        if ttl_seconds < 1:
            raise ValueError("lease TTL must be positive")
        with connection() as conn, conn.transaction():
            row = conn.execute(
                """
                SELECT *, now() AS database_now
                FROM resource_leases
                WHERE cluster_id = %s AND resource_type = %s AND resource_id = %s
                FOR UPDATE
                """,
                (cluster_id, resource_type, resource_id),
            ).fetchone()
            if row is not None and row["lease_expires_at"] > row["database_now"]:
                if row["owner_run_id"] != owner_run_id:
                    raise LeaseConflict(
                        "resource is owned by another active run",
                        observed_owner=row["owner_run_id"],
                    )
                return self._token(row)
            generation = int(row["lease_generation"]) + 1 if row is not None else 1
            database_now = (
                row["database_now"]
                if row is not None
                else conn.execute("SELECT now() AS database_now").fetchone()["database_now"]
            )
            expires_at = database_now + timedelta(seconds=ttl_seconds)
            updated = conn.execute(
                """
                INSERT INTO resource_leases (
                  cluster_id, resource_type, resource_id, owner_run_id,
                  lease_generation, lease_expires_at, heartbeat_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cluster_id, resource_type, resource_id)
                DO UPDATE SET
                  owner_run_id = EXCLUDED.owner_run_id,
                  lease_generation = EXCLUDED.lease_generation,
                  lease_expires_at = EXCLUDED.lease_expires_at,
                  heartbeat_at = EXCLUDED.heartbeat_at,
                  updated_at = now()
                RETURNING *
                """,
                (
                    cluster_id,
                    resource_type,
                    resource_id,
                    owner_run_id,
                    generation,
                    expires_at,
                    database_now,
                ),
            ).fetchone()
        return self._token(updated)

    def renew(self, token: LeaseToken, *, ttl_seconds: int) -> LeaseToken:
        if ttl_seconds < 1:
            raise ValueError("lease TTL must be positive")
        with connection() as conn, conn.transaction():
            row = conn.execute(
                """
                UPDATE resource_leases
                SET lease_expires_at = now() + (%s * interval '1 second'),
                    heartbeat_at = now(), updated_at = now()
                WHERE cluster_id = %s AND resource_type = %s AND resource_id = %s
                  AND owner_run_id = %s AND lease_generation = %s
                  AND lease_expires_at > now()
                RETURNING *
                """,
                (
                    ttl_seconds,
                    token.cluster_id,
                    token.resource_type,
                    token.resource_id,
                    token.owner_run_id,
                    token.generation,
                ),
            ).fetchone()
            if row is None:
                raise LeaseConflict("lease was lost or expired", observed_owner=None)
        return self._token(row)

    def release(self, token: LeaseToken) -> bool:
        with connection() as conn:
            row = conn.execute(
                """
                DELETE FROM resource_leases
                WHERE cluster_id = %s AND resource_type = %s AND resource_id = %s
                  AND owner_run_id = %s AND lease_generation = %s
                RETURNING owner_run_id
                """,
                (
                    token.cluster_id,
                    token.resource_type,
                    token.resource_id,
                    token.owner_run_id,
                    token.generation,
                ),
            ).fetchone()
            conn.commit()
        return row is not None

    @staticmethod
    def _token(row) -> LeaseToken:
        return LeaseToken(
            cluster_id=row["cluster_id"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            owner_run_id=row["owner_run_id"],
            generation=row["lease_generation"],
            expires_at=row["lease_expires_at"],
        )
