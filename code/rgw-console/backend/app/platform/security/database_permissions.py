"""Provision the fixed application login after migrations, using an admin login.

The API may write local inventory/dry-run metadata but must never own the
database, schema, or application objects. Run this job after every migration;
it refreshes grants for newly created tables before application startup.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

from ...config import get_settings


RUNTIME_ROLE = "storage_lab_runtime"
APPLICATION_SCHEMA = "public"
MIN_PASSWORD_LENGTH = 32


class DatabasePermissionsError(RuntimeError):
    """A provisioning failure with a stable, non-secret diagnostic code."""


def validate_runtime_password(password: str) -> str:
    if (
        not isinstance(password, str)
        or not MIN_PASSWORD_LENGTH <= len(password) <= 1024
        or any(ord(character) < 32 or ord(character) == 127 for character in password)
    ):
        raise DatabasePermissionsError("DATABASE_RUNTIME_PASSWORD_INVALID")
    return password


def read_runtime_password() -> str:
    configured_path = os.environ.get("DATABASE_RUNTIME_PASSWORD_FILE", "")
    if not configured_path:
        raise DatabasePermissionsError("DATABASE_RUNTIME_PASSWORD_FILE_REQUIRED")
    try:
        password = Path(configured_path).read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeError):
        raise DatabasePermissionsError("DATABASE_RUNTIME_PASSWORD_FILE_UNREADABLE") from None
    return validate_runtime_password(password)


def configure_runtime_role(conn: psycopg.Connection, password: str) -> None:
    """Configure the single supported login in the dedicated application DB.

    This deliberately has no role/schema arguments or environment overrides.
    The caller owns the transaction and commits only when every grant succeeds.
    """

    _configure_runtime_role(
        conn, password, role_name=RUNTIME_ROLE,
        schema_name=APPLICATION_SCHEMA, configure_database_acl=True,
    )


def _configure_runtime_role(
    conn: psycopg.Connection,
    password: str,
    *,
    role_name: str,
    schema_name: str,
    configure_database_acl: bool,
) -> None:
    """Internal SQL helper; tests isolate their role/schema and database ACLs."""

    validate_runtime_password(password)
    role = sql.Identifier(role_name)
    schema = sql.Identifier(schema_name)
    # Serialize provisioning jobs for this login, including CREATE ROLE races.
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"storage-lab-runtime:{role_name}",))
    exists = conn.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,),
    ).fetchone()
    if not exists:
        conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(role))

    # A role owning an object can always change/drop it even after REVOKE.
    # Refuse unsafe pre-existing ownership instead of reassigning user objects.
    owns_objects = conn.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM pg_shdepend dependency
            JOIN pg_roles runtime ON runtime.oid = dependency.refobjid
            WHERE runtime.rolname = %s
              AND dependency.refclassid = 'pg_authid'::regclass
              AND dependency.deptype = 'o'
        )
        """,
        (role_name,),
    ).fetchone()[0]
    if owns_objects:
        raise DatabasePermissionsError("DATABASE_RUNTIME_ROLE_OWNS_OBJECTS")

    conn.execute(sql.SQL(
        "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
    ).format(role, sql.Literal(password)))
    conn.execute(sql.SQL("ALTER ROLE {} RESET ALL").format(role))
    memberships = conn.execute(
        """
        SELECT parent.rolname FROM pg_auth_members membership
        JOIN pg_roles parent ON parent.oid = membership.roleid
        JOIN pg_roles member ON member.oid = membership.member
        WHERE member.rolname = %s
        """,
        (role_name,),
    ).fetchall()
    for membership in memberships:
        conn.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(membership[0]), role))

    if configure_database_acl:
        database_name = conn.execute("SELECT current_database()").fetchone()[0]
        database = sql.Identifier(database_name)
        # TEMP is inherited through PUBLIC by default; a direct role REVOKE is
        # insufficient. This job is for the dedicated console database only.
        conn.execute(sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(database))
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(database, role))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))

    migration_table = sql.Identifier(schema_name, "schema_migrations")
    if not conn.execute("SELECT to_regclass(%s)", (migration_table.as_string(conn),)).fetchone()[0]:
        raise DatabasePermissionsError("DATABASE_MIGRATIONS_REQUIRED")
    conn.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM PUBLIC").format(schema))
    conn.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(schema, role))
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, role))
    conn.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(schema, role))
    conn.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM PUBLIC").format(schema))
    conn.execute(sql.SQL(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}"
    ).format(schema, role))
    conn.execute(sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(migration_table, role))
    _revoke_column_privileges(conn, schema_name, "schema_migrations", role, privilege="ALL")
    _revoke_column_privileges(conn, schema_name, "schema_migrations", sql.SQL("PUBLIC"), privilege="ALL")
    conn.execute(sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(migration_table, role))
    # Collection create/delete/restore record audit events atomically. The
    # runtime can append an event but must never rewrite or remove history.
    events_table = sql.Identifier(schema_name, "as_is_collection_events")
    if conn.execute("SELECT to_regclass(%s)", (events_table.as_string(conn),)).fetchone()[0]:
        _revoke_column_privileges(conn, schema_name, "as_is_collection_events", role)
        _revoke_column_privileges(conn, schema_name, "as_is_collection_events", sql.SQL("PUBLIC"))
        conn.execute(sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(events_table, role))
        conn.execute(sql.SQL("GRANT SELECT, INSERT ON TABLE {} TO {}").format(events_table, role))
    collections_table = sql.Identifier(schema_name, "as_is_collections")
    if conn.execute("SELECT to_regclass(%s)", (collections_table.as_string(conn),)).fetchone()[0]:
        # Deletion/restoration changes deleted_at through UPDATE. A runtime
        # physical DELETE must not bypass retention or cascade audit records.
        _revoke_column_privileges(conn, schema_name, "as_is_collections", role)
        _revoke_column_privileges(conn, schema_name, "as_is_collections", sql.SQL("PUBLIC"))
        conn.execute(sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON TABLE {} FROM {}").format(collections_table, role))
        conn.execute(sql.SQL("GRANT UPDATE (deleted_at, deleted_by) ON TABLE {} TO {}").format(collections_table, role))
    conn.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM {}").format(schema, role))
    conn.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM PUBLIC").format(schema))
    conn.execute(sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA {} TO {}").format(schema, role))
    # Do not inherit arbitrary SECURITY DEFINER functions exposed via PUBLIC.
    conn.execute(sql.SQL("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {} FROM {}").format(schema, role))
    conn.execute(sql.SQL("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA {} FROM PUBLIC").format(schema))


def _revoke_column_privileges(conn, schema_name, table_name, role, *, privilege="UPDATE"):
    # Explicitly clear old column grants before applying the protected-table
    # policy. Migration columns are read-only; audit/collection updates are
    # limited to append-only events and the two soft-delete fields.
    if privilege not in {"ALL", "UPDATE"}:
        raise ValueError("unsupported protected-table column privilege")
    rows = conn.execute("""SELECT attribute.attname FROM pg_attribute attribute
        JOIN pg_class relation ON relation.oid=attribute.attrelid
        JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
        WHERE namespace.nspname=%s AND relation.relname=%s
          AND attribute.attnum>0 AND NOT attribute.attisdropped
        ORDER BY attribute.attnum""", (schema_name, table_name)).fetchall()
    if rows:
        columns = sql.SQL(', ').join(sql.Identifier(row[0]) for row in rows)
        conn.execute(sql.SQL("REVOKE {} ({}) ON TABLE {} FROM {}").format(sql.SQL(privilege), columns, sql.Identifier(schema_name, table_name), role))


def main() -> int:
    try:
        password = read_runtime_password()
        with psycopg.connect(get_settings().database_url, connect_timeout=10) as conn:
            configure_runtime_role(conn, password)
        print("DATABASE_RUNTIME_PERMISSIONS_CONFIGURED")
        return 0
    except DatabasePermissionsError as exc:
        print(str(exc), file=sys.stderr)
    except Exception:
        # Connection errors may include the admin connection string; never log
        # raw driver/config exceptions or the password-bearing SQL statement.
        print("DATABASE_RUNTIME_PERMISSIONS_FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
