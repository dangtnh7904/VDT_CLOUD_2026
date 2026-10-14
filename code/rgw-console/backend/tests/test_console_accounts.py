from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.config import Settings
from app.platform.config import build_config_snapshot, resolve_settings
from app.platform.security.middleware import ConsoleSecurityMiddleware, permitted_role_request


PASSWORD = "test-only-console-accounts-password"
SALT = b"test-only-account-salt"
PASSWORD_HASH = "pbkdf2_sha256$600000$" + base64.b64encode(SALT).decode() + "$" + base64.b64encode(
    hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), SALT, 600_000)
).decode()
RESOURCE_ID = "11111111-2222-3333-4444-555555555555"


class ConsoleAccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.accounts_file = Path(self.directory.name) / "console-users.json"
        self.document = {"version": 1, "users": [
            {"username": role + "-person", "role": role, "password_hash": PASSWORD_HASH}
            for role in ("viewer", "operator", "admin")
        ]}
        self.write(self.document)
        self.reached = []

    def write(self, document):
        self.accounts_file.write_text(json.dumps(document), encoding="utf-8")

    def configured(self, **overrides):
        values = {
            "app_env": "production", "execution_environment": "production",
            "console_read_only": True, "console_auth_users_file": self.accounts_file,
            "console_auth_username": "", "console_auth_password_hash_file": None,
            "console_auth_password_hash": None,
            "cors_origins": "https://console.example.test", "feature_upgrade": False,
            "feature_legacy_rgw": False, "feature_legacy_rbd": False,
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    def credentials(self, role, password=PASSWORD):
        return {
            "Authorization": "Basic " + base64.b64encode(f"{role}-person:{password}".encode()).decode(),
            "X-Console-Request": "1",
        }

    def client(self, provider=None):
        configured = self.configured()

        async def handler(request):
            self.reached.append((request.method, request.url.path))
            return JSONResponse({"actor": request.state.console_actor, "role": request.state.console_role})

        app = Starlette(routes=[Route("/{path:path}", handler, methods=["GET", "HEAD", "POST", "DELETE"])])
        app.add_middleware(ConsoleSecurityMiddleware, settings_provider=provider or (lambda: configured))
        return TestClient(app)

    def test_viewer_reads_observes_exports_and_compares_but_cannot_change_collection(self):
        with self.client() as client:
            for method, path in (
                ("GET", "/api/v1/as-is/collections"), ("GET", "/api/runtime-config"),
                ("POST", "/api/v1/as-is/observe"), ("POST", "/api/v1/as-is/export"),
                ("POST", "/api/v1/as-is/compare"), ("POST", "/api/v1/as-is/compare/export"),
            ):
                with self.subTest(method=method, path=path):
                    response = client.request(method, path, headers=self.credentials("viewer"))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), {"actor": "viewer-person", "role": "viewer"})
            for method, path in (
                ("POST", "/api/v1/as-is/collections"), ("POST", "/api/v1/cluster/collections"),
                ("POST", "/api/v1/sessions"), ("POST", "/api/v1/osdmap-previews"),
                ("DELETE", "/api/v1/as-is/collections/" + RESOURCE_ID),
                ("POST", "/api/v1/as-is/collections/" + RESOURCE_ID + "/restore"),
            ):
                with self.subTest(method=method, path=path):
                    response = client.request(method, path, headers=self.credentials("viewer"))
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["detail"]["code"], "CONSOLE_ROLE_FORBIDDEN")

    def test_operator_can_store_collection_only_admin_deletes_and_restores(self):
        with self.client() as client:
            for role in ("operator", "admin"):
                self.assertEqual(client.post("/api/v1/as-is/collections", headers=self.credentials(role)).status_code, 200)
            for method, path in (
                ("DELETE", "/api/v1/as-is/collections/" + RESOURCE_ID),
                ("POST", "/api/v1/as-is/collections/" + RESOURCE_ID + "/restore"),
            ):
                with self.subTest(method=method):
                    self.assertEqual(client.request(method, path, headers=self.credentials("operator")).status_code, 403)
                    response = client.request(method, path, headers={**self.credentials("admin"), "X-Actor": "spoofed"})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["actor"], "admin-person")

    def test_even_admin_cannot_bypass_ceph_read_only_unknown_route_or_csrf(self):
        with self.client() as client:
            for role in ("viewer", "operator", "admin"):
                for method, path in (("POST", "/api/v1/future-route"), ("POST", "/api/control/resume"), ("GET", "/api/rbd/volumes")):
                    with self.subTest(role=role, path=path):
                        response = client.request(method, path, headers=self.credentials(role))
                        self.assertEqual(response.status_code, 403)
                        self.assertEqual(response.json()["detail"]["code"], "CONSOLE_READ_ONLY")
            self.assertEqual(client.post("/api/v1/as-is/collections", headers={**self.credentials("operator"), "Origin": "https://attacker.test"}).status_code, 403)

    def test_unknown_user_wrong_password_and_spoofed_role_fail_closed(self):
        self.assertFalse(permitted_role_request("owner", "GET", "/api/runtime-config"))
        with self.client() as client:
            for headers in (self.credentials("unknown"), self.credentials("viewer", "wrong")):
                self.assertEqual(client.get("/api/runtime-config", headers=headers).status_code, 401)
            self.assertEqual(client.post("/api/v1/as-is/collections", headers={**self.credentials("viewer"), "X-Console-Role": "admin"}).status_code, 403)
        self.assertEqual(self.reached, [])

    def test_account_configuration_is_file_only_exclusive_read_only_and_redacted(self):
        configured = self.configured()
        encoded = json.dumps(configured.model_dump(), default=str)
        self.assertNotIn(PASSWORD_HASH, encoded)
        self.assertNotIn(str(self.accounts_file), encoded)
        self.assertNotIn("viewer-person", encoded)
        self.assertNotIn(PASSWORD_HASH, repr(configured))
        for overrides in (
            {"console_auth_users": configured.console_auth_users, "console_auth_users_file": None},
            {"console_auth_username": "legacy"}, {"console_auth_password_hash_file": self.accounts_file},
            {"console_read_only": False},
        ):
            with self.subTest(fields=tuple(overrides)), self.assertRaises(ValidationError):
                self.configured(**overrides)

    def test_profile_resolution_retains_authentication_and_snapshot_does_not_expose_accounts(self):
        profile = Path(self.directory.name) / "cluster.yaml"
        profile.write_text("cluster_id: test-cluster\n", encoding="utf-8")
        configured = self.configured(cluster_config_path=profile)
        resolved = resolve_settings(configured)
        self.assertEqual(resolved.console_auth_users["viewer-person"].role, "viewer")
        snapshot = json.dumps(build_config_snapshot(configured).payload)
        self.assertNotIn(PASSWORD_HASH, snapshot)
        self.assertNotIn(str(self.accounts_file), snapshot)
        self.assertNotIn("viewer-person", snapshot)

    def test_malformed_duplicate_oversized_and_unknown_accounts_are_rejected_without_hash_disclosure(self):
        valid_user = self.document["users"][0]
        documents = [
            {"version": True, "users": [valid_user]}, {"version": 2, "users": [valid_user]},
            {"version": 1, "users": []}, {"version": 1, "users": [valid_user, valid_user]},
            {"version": 1, "users": [dict(valid_user, role="owner")]},
            {"version": 1, "users": [dict(valid_user, username="actor:admin")]},
            {"version": 1, "users": [dict(valid_user, password="plaintext")]},
            {"version": 1, "users": [dict(valid_user, password_hash=PASSWORD_HASH.replace("600000", "1000"))]},
            {"version": 1, "users": [dict(valid_user, username=f"user-{index}") for index in range(129)]},
        ]
        for document in documents:
            with self.subTest(version=document["version"], users=len(document["users"])):
                self.write(document)
                with self.assertRaises(ValidationError) as caught:
                    self.configured()
                self.assertNotIn(PASSWORD_HASH, str(caught.exception))
                self.assertNotIn(PASSWORD, str(caught.exception))
        for invalid in ('{"version":1,"version":1,"users":[]}', "{" * 1000, " " * 65_537, "not-json"):
            self.accounts_file.write_text(invalid, encoding="utf-8")
            with self.assertRaises(ValidationError):
                self.configured()

    def test_role_rotation_does_not_reuse_cached_admin_capability(self):
        holder = [self.configured()]
        with self.client(provider=lambda: holder[0]) as client:
            self.assertEqual(client.delete("/api/v1/as-is/collections/" + RESOURCE_ID, headers=self.credentials("admin")).status_code, 200)
            self.document["users"][2]["role"] = "viewer"
            self.write(self.document)
            holder[0] = self.configured()
            self.assertEqual(client.delete("/api/v1/as-is/collections/" + RESOURCE_ID, headers=self.credentials("admin")).status_code, 403)
            self.assertEqual(client.get("/api/runtime-config", headers=self.credentials("admin")).json()["role"], "viewer")

    def test_real_collection_api_uses_authenticated_actor_for_create_delete_and_restore(self):
        from app.modules.as_is.api import router

        calls = []

        class Service:
            def create(self, **kwargs):
                calls.append(("create", kwargs["actor"]))
                return {"id": RESOURCE_ID, "actor": kwargs["actor"]}

            def set_deleted(self, collection_id, *, deleted, actor):
                calls.append(("delete" if deleted else "restore", actor))
                return {"id": str(collection_id), "actor": actor}

        app = FastAPI()
        app.include_router(router)
        configured = self.configured()
        app.add_middleware(ConsoleSecurityMiddleware, settings_provider=lambda: configured)
        with patch("app.modules.as_is.api._service", return_value=Service()), TestClient(app) as client:
            payload = {"daemon_keys": ["osd.2"], "phase": "BEFORE"}
            self.assertEqual(client.post("/api/v1/as-is/collections", json=payload, headers=self.credentials("viewer")).status_code, 403)
            self.assertEqual(client.post("/api/v1/as-is/collections", json=payload, headers={**self.credentials("operator"), "X-Actor": "spoofed"}).status_code, 201)
            self.assertEqual(client.delete("/api/v1/as-is/collections/" + RESOURCE_ID, headers=self.credentials("operator")).status_code, 403)
            self.assertEqual(client.delete("/api/v1/as-is/collections/" + RESOURCE_ID, headers=self.credentials("admin")).status_code, 200)
            self.assertEqual(client.post("/api/v1/as-is/collections/" + RESOURCE_ID + "/restore", headers=self.credentials("admin")).status_code, 200)
        self.assertEqual(calls, [("create", "operator-person"), ("delete", "admin-person"), ("restore", "admin-person")])


if __name__ == "__main__":
    unittest.main()
