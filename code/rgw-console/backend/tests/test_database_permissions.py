from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql

from app.platform.security.database_permissions import (
    DatabasePermissionsError,
    _configure_runtime_role,
    main,
    read_runtime_password,
    validate_runtime_password,
)


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
PASSWORD = "test-only-runtime-password-32-characters"


class DatabasePermissionsTests(unittest.TestCase):
    def test_invalid_passwords_have_stable_non_secret_errors(self):
        for password in ("short", "x" * 1025, "x" * 32 + "\x00", "x" * 32 + "\n"):
            with self.subTest(length=len(password)):
                with self.assertRaises(DatabasePermissionsError) as caught:
                    validate_runtime_password(password)
                self.assertEqual(str(caught.exception), "DATABASE_RUNTIME_PASSWORD_INVALID")
                self.assertNotIn(password, str(caught.exception))

    def test_secret_file_preserves_sql_punctuation_and_requires_explicit_file(self):
        password = PASSWORD + "'\\; DO $$BEGIN RAISE EXCEPTION 'secret'; END$$;"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime-password"
            path.write_text(password + "\n", encoding="utf-8")
            with patch.dict(os.environ, {"DATABASE_RUNTIME_PASSWORD_FILE": str(path)}, clear=True):
                self.assertEqual(read_runtime_password(), password)
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(DatabasePermissionsError) as caught:
                read_runtime_password()
            self.assertEqual(str(caught.exception), "DATABASE_RUNTIME_PASSWORD_FILE_REQUIRED")
            with patch.dict(os.environ, {"DATABASE_RUNTIME_PASSWORD_FILE": str(path / "missing")}, clear=True):
                with self.assertRaises(DatabasePermissionsError) as caught:
                    read_runtime_password()
            self.assertEqual(str(caught.exception), "DATABASE_RUNTIME_PASSWORD_FILE_UNREADABLE")

    def test_cli_sanitizes_driver_connection_errors(self):
        stderr = io.StringIO()
        with patch("app.platform.security.database_permissions.read_runtime_password", return_value=PASSWORD):
            with patch("app.platform.security.database_permissions.get_settings", side_effect=RuntimeError("postgresql://admin:SUPERSECRET@host/database")):
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(main(), 1)
        self.assertEqual(stderr.getvalue(), "DATABASE_RUNTIME_PERMISSIONS_FAILED\n")
        self.assertNotIn("SUPERSECRET", stderr.getvalue())


@unittest.skipUnless(DATABASE_URL, "set TEST_DATABASE_URL to run PostgreSQL permission tests")
class DatabasePermissionsIntegrationTests(unittest.TestCase):
    """Role/schema creation and grants are rolled back, leaving public untouched."""

    def setUp(self):
        self.conn = psycopg.connect(DATABASE_URL)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        suffix = uuid.uuid4().hex
        self.schema = "permissions_test_" + suffix
        self.role = "permissions_runtime_" + suffix
        self.parent_role = "permissions_parent_" + suffix
        self.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn.execute(sql.SQL(
            "CREATE TABLE {} (id BIGSERIAL PRIMARY KEY, payload TEXT NOT NULL)"
        ).format(sql.Identifier(self.schema, "observations")))
        self.conn.execute(sql.SQL(
            "CREATE TABLE {} (version INTEGER PRIMARY KEY)"
        ).format(sql.Identifier(self.schema, "schema_migrations")))
        self.conn.execute(sql.SQL("INSERT INTO {} VALUES (19)").format(sql.Identifier(self.schema, "schema_migrations")))
        self.conn.execute(sql.SQL("GRANT CREATE ON SCHEMA {} TO PUBLIC").format(sql.Identifier(self.schema)))

    def configure(self, password=PASSWORD):
        _configure_runtime_role(
            self.conn, password,
            role_name=self.role, schema_name=self.schema,
            configure_database_acl=False,
        )

    def as_runtime(self):
        self.conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(self.role)))

    def assert_denied(self, statement):
        # A savepoint preserves the provisioning transaction after denial.
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.conn.transaction():
                self.conn.execute(statement)

    def test_flags_memberships_and_idempotent_password_rotation_are_restricted(self):
        self.conn.execute(sql.SQL("CREATE ROLE {} SUPERUSER CREATEDB CREATEROLE REPLICATION BYPASSRLS").format(sql.Identifier(self.role)))
        self.conn.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(self.parent_role)))
        self.conn.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(self.parent_role), sql.Identifier(self.role)))
        # Punctuation cannot escape the safely composed password literal.
        self.configure(PASSWORD + "'; DROP ROLE definitely_not_a_role; --")
        self.configure(PASSWORD + "-rotated")
        flags = self.conn.execute(
            "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit FROM pg_roles WHERE rolname=%s",
            (self.role,),
        ).fetchone()
        self.assertEqual(flags, (True, False, False, False, False, False, False))
        memberships = self.conn.execute(
            "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)",
            (self.role,),
        ).fetchone()[0]
        self.assertEqual(memberships, 0)

    def test_runtime_can_store_metadata_but_cannot_modify_schema_or_migrations(self):
        self.configure()
        self.as_runtime()
        observations = sql.Identifier(self.schema, "observations")
        migrations = sql.Identifier(self.schema, "schema_migrations")
        row_id = self.conn.execute(sql.SQL("INSERT INTO {} (payload) VALUES ('inventory') RETURNING id").format(observations)).fetchone()[0]
        self.conn.execute(sql.SQL("UPDATE {} SET payload='dry-run' WHERE id=%s").format(observations), (row_id,))
        self.assertEqual(self.conn.execute(sql.SQL("SELECT payload FROM {}").format(observations)).fetchone()[0], "dry-run")
        self.assertEqual(self.conn.execute(sql.SQL("SELECT version FROM {}").format(migrations)).fetchone()[0], 19)
        for statement in (
            sql.SQL("CREATE TABLE {} (id INTEGER)").format(sql.Identifier(self.schema, "unsafe")),
            sql.SQL("ALTER TABLE {} ADD COLUMN unsafe TEXT").format(observations),
            sql.SQL("DROP TABLE {}").format(observations),
            sql.SQL("TRUNCATE {}").format(observations),
            sql.SQL("INSERT INTO {} VALUES (20)").format(migrations),
            sql.SQL("UPDATE {} SET version=20").format(migrations),
            sql.SQL("DELETE FROM {}").format(migrations),
        ):
            with self.subTest(statement=statement.as_string(self.conn)):
                self.assert_denied(statement)
        self.conn.execute(sql.SQL("DELETE FROM {} WHERE id=%s").format(observations), (row_id,))
        self.assertEqual(self.conn.execute(sql.SQL("SELECT count(*) FROM {}").format(observations)).fetchone()[0], 0)

    def test_runtime_owner_is_rejected_and_public_functions_are_not_inherited(self):
        self.conn.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(self.role)))
        self.conn.execute(sql.SQL("ALTER TABLE {} OWNER TO {}").format(sql.Identifier(self.schema, "observations"), sql.Identifier(self.role)))
        with self.assertRaises(DatabasePermissionsError) as caught:
            self.configure()
        self.assertEqual(str(caught.exception), "DATABASE_RUNTIME_ROLE_OWNS_OBJECTS")
        self.conn.execute(sql.SQL("ALTER TABLE {} OWNER TO CURRENT_USER").format(sql.Identifier(self.schema, "observations")))
        self.conn.execute(sql.SQL("CREATE FUNCTION {}() RETURNS INT LANGUAGE SQL SECURITY DEFINER AS 'SELECT 1'").format(sql.Identifier(self.schema, "privileged")))
        self.configure()
        self.as_runtime()
        self.assert_denied(sql.SQL("SELECT {}()").format(sql.Identifier(self.schema, "privileged")))

    def test_job_refreshes_grants_for_tables_added_by_next_migration(self):
        self.configure()
        self.conn.execute(sql.SQL("CREATE TABLE {} (payload TEXT)").format(sql.Identifier(self.schema, "new_inventory")))
        self.configure()
        self.as_runtime()
        self.conn.execute(sql.SQL("INSERT INTO {} VALUES ('new metadata')").format(sql.Identifier(self.schema, "new_inventory")))

    def test_dedicated_database_acl_denies_create_schema_and_temporary_tables(self):
        # The DB-level production branch is exercised only in a new disposable
        # database. Neither TEST_DATABASE_URL's public schema nor its ACL change.
        database = "permissions_database_" + uuid.uuid4().hex
        with psycopg.connect(DATABASE_URL, autocommit=True) as administrator:
            administrator.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            try:
                with psycopg.connect(DATABASE_URL, dbname=database) as isolated:
                    try:
                        isolated.execute("CREATE TABLE public.schema_migrations (version INTEGER PRIMARY KEY)")
                        # Test non-default PUBLIC grants as well as PostgreSQL's
                        # default PUBLIC TEMP permission.
                        isolated.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO PUBLIC").format(sql.Identifier(database)))
                        _configure_runtime_role(
                            isolated, PASSWORD, role_name=self.role,
                            schema_name="public", configure_database_acl=True,
                        )
                        isolated.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(self.role)))
                        self.assertEqual(isolated.execute("SELECT version FROM public.schema_migrations").fetchall(), [])
                        for statement in (
                            "CREATE TEMP TABLE unsafe (id INTEGER)",
                            "CREATE SCHEMA unsafe",
                            "CREATE TABLE public.unsafe (id INTEGER)",
                        ):
                            with self.subTest(statement=statement):
                                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                                    with isolated.transaction():
                                        isolated.execute(statement)
                    finally:
                        isolated.rollback()
            finally:
                administrator.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))


if __name__ == "__main__":
    unittest.main()
