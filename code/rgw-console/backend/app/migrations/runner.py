from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any, Iterable


MIGRATION_FILE_RE = re.compile(r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$")
MIGRATION_LOCK_KEY = 7_241_990_512_026_092_101

LEGACY_OPERATIONS_COLUMNS = {
    "id": ("int8", False),
    "kind": ("text", False),
    "success": ("bool", False),
    "bytes_count": ("int8", False),
    "latency_ms": ("float8", False),
    "bucket": ("text", False),
    "object_key": ("text", False),
    "client_id": ("text", True),
    "category": ("text", True),
    "source": ("text", True),
    "content_type": ("text", True),
    "error": ("text", True),
    "created_at": ("timestamptz", False),
}
LEGACY_STREAM_JOBS_COLUMNS = {
    "id": ("uuid", False),
    "state": ("text", False),
    "config": ("jsonb", False),
    "sent_count": ("int8", False),
    "failed_count": ("int8", False),
    "bytes_sent": ("int8", False),
    "last_error": ("text", True),
    "created_at": ("timestamptz", False),
    "started_at": ("timestamptz", True),
    "updated_at": ("timestamptz", False),
    "finished_at": ("timestamptz", True),
}

MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class MigrationError(RuntimeError):
    """The database schema cannot be migrated safely."""


class MigrationRequiredError(MigrationError):
    """The application was started before its one-shot migration completed."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    checksum: str
    sql: str


@dataclass(frozen=True)
class MigrationResult:
    current_version: int
    applied_versions: tuple[int, ...]
    stamped_versions: tuple[int, ...]


def load_migrations() -> tuple[Migration, ...]:
    package = resources.files("app.migrations.versions")
    migrations: list[Migration] = []

    for item in package.iterdir():
        match = MIGRATION_FILE_RE.fullmatch(item.name)
        if not match:
            continue
        sql = item.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        migrations.append(
            Migration(
                version=int(match.group("version")),
                name=match.group("name"),
                checksum=checksum,
                sql=sql,
            )
        )

    migrations.sort(key=lambda migration: migration.version)
    if not migrations:
        raise MigrationError("No migration files were found")

    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError("Migration versions must be unique")
    if versions != list(range(1, versions[-1] + 1)):
        raise MigrationError(f"Migration versions must be contiguous from 1: {versions}")
    return tuple(migrations)


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = current_schema()
            AND table_name = %s
            AND table_type = 'BASE TABLE'
        ) AS present
        """,
        (table_name,),
    ).fetchone()
    return bool(row["present"])


def _column_signature(conn: Any, table_name: str) -> dict[str, tuple[str, bool]]:
    rows = conn.execute(
        """
        SELECT column_name, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s
        """,
        (table_name,),
    ).fetchall()
    return {
        row["column_name"]: (row["udt_name"], row["is_nullable"] == "YES")
        for row in rows
    }


def _legacy_kind_constraint_is_expected(conn: Any) -> bool:
    rows = conn.execute(
        """
        SELECT pg_get_constraintdef(constraint_row.oid) AS definition
        FROM pg_constraint AS constraint_row
        JOIN pg_class AS table_row ON table_row.oid = constraint_row.conrelid
        JOIN pg_namespace AS namespace_row ON namespace_row.oid = table_row.relnamespace
        WHERE namespace_row.nspname = current_schema()
          AND table_row.relname = 'operations'
          AND constraint_row.contype = 'c'
        """
    ).fetchall()
    definitions = [row["definition"] for row in rows]
    kind_checks = [definition for definition in definitions if "kind" in definition]
    return (
        len(kind_checks) == 1
        and "'PUT'::text" in kind_checks[0]
        and "'GET'::text" in kind_checks[0]
        and "RBD_" not in kind_checks[0]
    )


def _classify_unversioned_schema(conn: Any) -> str:
    operations_exists = _table_exists(conn, "operations")
    jobs_exists = _table_exists(conn, "stream_jobs")

    if not operations_exists and not jobs_exists:
        return "fresh"
    if operations_exists != jobs_exists:
        return "unknown"

    if (
        _column_signature(conn, "operations") == LEGACY_OPERATIONS_COLUMNS
        and _column_signature(conn, "stream_jobs") == LEGACY_STREAM_JOBS_COLUMNS
        and _legacy_kind_constraint_is_expected(conn)
    ):
        return "legacy_v1"
    return "unknown"


def _read_applied(conn: Any) -> dict[int, dict[str, Any]]:
    rows = conn.execute(
        "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {row["version"]: row for row in rows}


def _validate_applied(
    applied: dict[int, dict[str, Any]], migrations: Iterable[Migration]
) -> None:
    known = {migration.version: migration for migration in migrations}
    unknown_versions = sorted(set(applied) - set(known))
    if unknown_versions:
        raise MigrationError(
            f"Database contains migration versions unknown to this build: {unknown_versions}"
        )

    applied_versions = sorted(applied)
    if applied_versions and applied_versions != list(range(1, applied_versions[-1] + 1)):
        raise MigrationError(
            f"Applied migrations are not a contiguous prefix: {applied_versions}"
        )

    for version, row in applied.items():
        migration = known[version]
        if row["name"] != migration.name or row["checksum"] != migration.checksum:
            raise MigrationError(
                f"Applied migration {version:04d} does not match this build; "
                "do not edit an applied migration"
            )


def migrate(conn: Any) -> MigrationResult:
    migrations = load_migrations()
    applied_versions: list[int] = []
    stamped_versions: list[int] = []

    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_KEY,))
        conn.execute(MIGRATIONS_TABLE_SQL)
        applied = _read_applied(conn)
        _validate_applied(applied, migrations)

        if not applied:
            schema_kind = _classify_unversioned_schema(conn)
            if schema_kind == "legacy_v1":
                baseline = migrations[0]
                conn.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum)
                    VALUES (%s, %s, %s)
                    """,
                    (baseline.version, baseline.name, baseline.checksum),
                )
                applied[baseline.version] = {
                    "version": baseline.version,
                    "name": baseline.name,
                    "checksum": baseline.checksum,
                }
                stamped_versions.append(baseline.version)
            elif schema_kind != "fresh":
                raise MigrationError(
                    "Existing operations/stream_jobs schema does not match the supported "
                    "legacy fingerprint; refusing to guess or overwrite it"
                )

        for migration in migrations:
            if migration.version in applied:
                continue
            conn.execute(migration.sql)
            conn.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum)
                VALUES (%s, %s, %s)
                """,
                (migration.version, migration.name, migration.checksum),
            )
            applied_versions.append(migration.version)

        current_version = migrations[-1].version

    return MigrationResult(
        current_version=current_version,
        applied_versions=tuple(applied_versions),
        stamped_versions=tuple(stamped_versions),
    )


def assert_schema_current(conn: Any) -> int:
    migrations = load_migrations()
    latest = migrations[-1]

    if not _table_exists(conn, "schema_migrations"):
        raise MigrationRequiredError(
            "Database is not migrated; run `python -m app.migrate` before starting the service"
        )

    applied = _read_applied(conn)
    _validate_applied(applied, migrations)
    if not applied or max(applied) != latest.version or set(applied) != {
        migration.version for migration in migrations
    }:
        current = max(applied, default=0)
        raise MigrationRequiredError(
            f"Database schema is at version {current:04d}, but this build requires "
            f"{latest.version:04d}; run `python -m app.migrate`"
        )
    return latest.version
