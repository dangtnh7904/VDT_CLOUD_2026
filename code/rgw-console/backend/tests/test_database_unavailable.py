"""Transient DB errors are safe 503s, never silent data or masked SQL bugs."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import psycopg
from psycopg_pool import PoolClosed, PoolTimeout
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.main import database_unavailable_handler
from app.modules.as_is import api as as_is_api
from app.platform.database_errors import DatabaseUnavailableError, is_connection_unavailable


PRIVATE_DRIVER_MESSAGE = "postgresql://private:never-report-password@private/db SQL private-note"
COLLECTION_A = "11111111-2222-4333-8444-555555555555"
COLLECTION_B = "11111111-2222-4333-8444-555555555556"


class FakePool:
    def __init__(self, *, acquire_error=None, exit_error=None, closed=False, broken=False):
        self.closed = closed
        self.conn = SimpleNamespace(closed=False, broken=broken)
        self.acquire_error, self.exit_error = acquire_error, exit_error
        self.timeouts, self.open_calls = [], []

    @contextmanager
    def connection(self, timeout=None):
        self.timeouts.append(timeout)
        if self.acquire_error:
            raise self.acquire_error
        yield self.conn
        if self.exit_error:
            raise self.exit_error

    def open(self, *, wait, timeout):
        self.open_calls.append({"wait": wait, "timeout": timeout})
        self.closed = False

    def close(self):
        self.closed = True


class ClassificationTests(unittest.TestCase):
    def test_pool_exhaustion_and_closed_pool_are_transient(self):
        for error in (PoolTimeout(PRIVATE_DRIVER_MESSAGE), PoolClosed(PRIVATE_DRIVER_MESSAGE)):
            with self.subTest(error_type=type(error).__name__):
                self.assertTrue(is_connection_unavailable(error))

    def test_connection_and_server_shutdown_sqlstates_are_transient(self):
        for error_type in (psycopg.errors.ConnectionException, psycopg.errors.ConnectionFailure,
                           psycopg.errors.AdminShutdown, psycopg.errors.CrashShutdown,
                           psycopg.errors.CannotConnectNow):
            with self.subTest(error_type=error_type.__name__):
                self.assertTrue(is_connection_unavailable(error_type(PRIVATE_DRIVER_MESSAGE)))

    def test_generic_driver_errors_require_acquisition_or_actual_broken_connection(self):
        for error_type in (psycopg.OperationalError, psycopg.InterfaceError):
            error = error_type(PRIVATE_DRIVER_MESSAGE)
            with self.subTest(error_type=error_type.__name__):
                self.assertTrue(is_connection_unavailable(error, acquiring=True))
                self.assertTrue(is_connection_unavailable(error, SimpleNamespace(closed=True, broken=False)))
                self.assertTrue(is_connection_unavailable(error, SimpleNamespace(closed=False, broken=True)))
                self.assertFalse(is_connection_unavailable(error, SimpleNamespace(closed=False, broken=False)))
                self.assertFalse(is_connection_unavailable(error))

    def test_sql_schema_transaction_cancellation_and_programming_errors_are_not_hidden(self):
        for error_type in (psycopg.errors.QueryCanceled, psycopg.errors.SerializationFailure,
                           psycopg.errors.DeadlockDetected, psycopg.errors.UndefinedTable,
                           psycopg.errors.UniqueViolation, psycopg.ProgrammingError,
                           ValueError, RuntimeError):
            with self.subTest(error_type=error_type.__name__):
                error = error_type(PRIVATE_DRIVER_MESSAGE)
                self.assertFalse(is_connection_unavailable(error, acquiring=True))
                self.assertFalse(is_connection_unavailable(error, SimpleNamespace(closed=True, broken=True)))

    def test_domain_error_never_contains_original_driver_details(self):
        self.assertEqual(DatabaseUnavailableError().code, "DATABASE_UNAVAILABLE")
        self.assertNotIn("private", str(DatabaseUnavailableError()))
        self.assertNotIn("password", str(DatabaseUnavailableError()))


class ConnectionBoundaryTests(unittest.TestCase):
    def test_pool_timeout_is_safe_domain_error_with_five_second_acquire_budget(self):
        pool = FakePool(acquire_error=PoolTimeout(PRIVATE_DRIVER_MESSAGE))
        with patch.object(db, "pool", pool), self.assertRaises(DatabaseUnavailableError) as caught:
            with db.connection():
                self.fail("Timed-out acquisition must not execute the endpoint body")
        self.assertEqual(pool.timeouts, [5.0])
        self.assertNotIn("password", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_connection_acquisition_operational_error_is_safe(self):
        pool = FakePool(acquire_error=psycopg.OperationalError(PRIVATE_DRIVER_MESSAGE))
        with patch.object(db, "pool", pool), self.assertRaises(DatabaseUnavailableError):
            with db.connection():
                pass

    def test_network_drop_in_query_or_commit_is_safe(self):
        for commit in (False, True):
            with self.subTest(commit=commit):
                error = psycopg.OperationalError(PRIVATE_DRIVER_MESSAGE)
                pool = FakePool(broken=True, exit_error=error if commit else None)
                with patch.object(db, "pool", pool), self.assertRaises(DatabaseUnavailableError):
                    with db.connection():
                        if not commit:
                            raise error

    def test_query_and_programming_failures_are_rethrown_unchanged(self):
        for error_type in (psycopg.errors.QueryCanceled, psycopg.ProgrammingError,
                           psycopg.OperationalError, ValueError):
            error = error_type(PRIVATE_DRIVER_MESSAGE)
            with self.subTest(error_type=error_type.__name__):
                with patch.object(db, "pool", FakePool()), self.assertRaises(error_type) as caught:
                    with db.connection():
                        raise error
                self.assertIs(caught.exception, error)

    def test_initialization_bounds_pool_open_and_schema_acquisition(self):
        pool = FakePool(closed=True)
        with patch.object(db, "pool", pool), patch.object(db, "assert_schema_current"):
            db.initialize()
        self.assertEqual(pool.open_calls, [{"wait": True, "timeout": 5.0}])
        self.assertEqual(pool.timeouts, [5.0])

    def test_initialization_closes_pool_but_does_not_mask_schema_failure(self):
        pool = FakePool()
        error = psycopg.errors.UndefinedTable(PRIVATE_DRIVER_MESSAGE)
        with patch.object(db, "pool", pool), patch.object(db, "assert_schema_current", side_effect=error):
            with self.assertRaises(psycopg.errors.UndefinedTable) as caught:
                db.initialize()
        self.assertIs(caught.exception, error)
        self.assertTrue(pool.closed)


class HttpContractTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(as_is_api.router)
        self.app.add_exception_handler(DatabaseUnavailableError, database_unavailable_handler)
        self.client = TestClient(self.app)

    def test_history_saved_export_comparison_delete_restore_all_return_defined_503(self):
        cases = [
            ("GET", "/api/v1/as-is/collections", None, "list"),
            ("GET", f"/api/v1/as-is/collections/{COLLECTION_A}", None, "get"),
            ("GET", f"/api/v1/as-is/collections/{COLLECTION_A}/export", None, "export_view"),
            ("POST", "/api/v1/as-is/compare", {"collection_a_id": COLLECTION_A,
                "collection_b_id": COLLECTION_B, "daemon_type": "osd"}, "compare"),
            ("POST", "/api/v1/as-is/compare/export", {"collection_a_id": COLLECTION_A,
                "collection_b_id": COLLECTION_B, "daemon_type": "osd"}, "compare"),
            ("DELETE", f"/api/v1/as-is/collections/{COLLECTION_A}", None, "set_deleted"),
            ("POST", f"/api/v1/as-is/collections/{COLLECTION_A}/restore", None, "set_deleted"),
        ]
        for method, path, payload, operation in cases:
            with self.subTest(method=method, path=path):
                service = Mock()
                getattr(service, operation).side_effect = DatabaseUnavailableError()
                with patch.object(as_is_api, "_service", return_value=service):
                    response = self.client.request(method, path, json=payload)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["detail"]["code"], "DATABASE_UNAVAILABLE")
                self.assertTrue(response.json()["detail"]["retryable"])
                self.assertEqual(response.headers["retry-after"], "2")
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertNotIn("private", response.text)
                self.assertNotEqual(response.json(), [])

    def test_unrelated_endpoint_programming_error_is_not_converted_to_503(self):
        for error_type in (psycopg.ProgrammingError, ValueError):
            service = Mock()
            service.list.side_effect = error_type(PRIVATE_DRIVER_MESSAGE)
            with self.subTest(error_type=error_type.__name__):
                with patch.object(as_is_api, "_service", return_value=service):
                    with self.assertRaises(error_type):
                        self.client.get("/api/v1/as-is/collections")


if __name__ == "__main__":
    unittest.main()
