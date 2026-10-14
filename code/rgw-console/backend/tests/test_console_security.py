from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.platform.config import build_config_snapshot
from app.platform.security.middleware import ConsoleSecurityMiddleware


PASSWORD = "test-long-password-for-management"
SALT = b"test-only-salt-16bytes"
PASSWORD_HASH = "pbkdf2_sha256$600000$" + base64.b64encode(SALT).decode() + "$" + base64.b64encode(
    hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), SALT, 600_000)
).decode()
RESOURCE_ID = "11111111-2222-3333-4444-555555555555"


class ConsoleSecurityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hash_file = Path(self.directory.name) / "console-password.hash"
        self.hash_file.write_text(PASSWORD_HASH, encoding="utf-8")
        self.reached = []

    def configured(self, **overrides):
        values = {
            "app_env": "production",
            "execution_environment": "production",
            "console_read_only": True,
            "console_auth_username": "operator",
            "console_auth_password_hash_file": self.hash_file,
            "cors_origins": "https://console.example.test",
            "feature_upgrade": False,
            "feature_legacy_rgw": False,
            "feature_legacy_rbd": False,
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    def client(self, configured=None):
        configured = configured or self.configured()

        async def handler(request):
            self.reached.append((request.method, request.url.path))
            return JSONResponse({"reached": True, "actor": getattr(request.state, "console_actor", None)})

        async def websocket(websocket):
            await websocket.accept()
            await websocket.send_text("unexpected terminal access")

        application = Starlette(routes=[
            Route("/{path:path}", handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
            WebSocketRoute("/{path:path}", websocket),
        ])
        application.add_middleware(ConsoleSecurityMiddleware, settings_provider=lambda: configured)
        return TestClient(application)

    def credentials(self, username="operator", password=PASSWORD):
        return {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()}

    def test_production_requires_read_only_and_file_authentication(self):
        for overrides in (
            {"console_read_only": False},
            {"console_auth_username": "", "console_auth_password_hash_file": None},
            {"console_auth_password_hash_file": None, "console_auth_password_hash": PASSWORD_HASH},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self.configured(**overrides)

    def test_read_only_rejects_each_mutation_capability_even_with_credentials(self):
        for flag in (
            "feature_legacy_rgw", "feature_legacy_rbd", "feature_lab",
            "upgrade_mutations_enabled",
            "lab_validation_enabled", "lab_allow_write",
        ):
            with self.subTest(flag=flag), self.assertRaises(ValidationError):
                self.configured(**{flag: True})
        with self.assertRaises(ValidationError):
            self.configured(capacity_observe_only=False)

    def test_production_rejects_insecure_or_wildcard_origins(self):
        for origins in ("", "*", "http://console.example.test", "https://user:password@console.example.test", "https://console.example.test/path"):
            with self.subTest(origins=origins), self.assertRaises(ValidationError):
                self.configured(cors_origins=origins)

    def test_hash_file_requires_bounded_secure_hash_and_redacts_snapshot(self):
        configured = self.configured()
        encoded = json.dumps(build_config_snapshot(configured).payload)
        self.assertNotIn(PASSWORD_HASH, encoded)
        self.assertNotIn(str(self.hash_file), encoded)
        self.assertNotIn(PASSWORD_HASH, repr(configured))
        self.hash_file.write_text(PASSWORD_HASH.replace("600000", "1000"), encoding="utf-8")
        with self.assertRaises(ValidationError):
            self.configured()

    def test_ui_docs_and_ready_are_authenticated_but_live_is_public(self):
        with self.client() as client:
            for path in ("/", "/assets/main.js", "/docs", "/openapi.json", "/api/ready", "/api/runtime-config"):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 401)
                    self.assertIn("Basic", response.headers["www-authenticate"])
            self.assertEqual(client.get("/api/live").status_code, 200)
            response = client.get("/api/runtime-config", headers=self.credentials())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["actor"], "operator")
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_wrong_malformed_and_oversized_credentials_fail_closed(self):
        with self.client() as client:
            for headers in (
                self.credentials(password="wrong"), self.credentials(username="someone"),
                {"Authorization": "Basic !!!"}, {"Authorization": "Bearer secret"},
                {"Authorization": "Basic " + "x" * 4096},
            ):
                with self.subTest(headers_type=list(headers)):
                    self.assertEqual(client.get("/api/runtime-config", headers=headers).status_code, 401)
        self.assertEqual(self.reached, [])

    def test_valid_auth_cannot_reach_mutations_unknown_api_or_terminal(self):
        with self.client() as client:
            for method, path in (
                ("POST", "/api/uploads/random"), ("DELETE", "/api/objects"),
                ("POST", "/api/jobs"), ("POST", "/api/control/resume"),
                ("POST", "/api/rbd/volumes"), ("GET", "/api/rbd/volumes"),
                ("POST", "/api/v1/qos-runs/" + RESOURCE_ID + "/start"),
                ("POST", "/api/v1/qos-runs/" + RESOURCE_ID + "/cleanup"),
                ("POST", "/api/v1/upgrade-runs/" + RESOURCE_ID + "/execute"),
                ("GET", "/api/future-mutating-get"), ("GET", "/ws/terminal"),
            ):
                with self.subTest(method=method, path=path):
                    response = client.request(method, path, headers={**self.credentials(), "X-Console-Request": "1"})
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["detail"]["code"], "CONSOLE_READ_ONLY")
        self.assertEqual(self.reached, [])

    def test_inventory_and_local_collection_operations_remain_usable_with_request_marker(self):
        with self.client() as client:
            for path in (
                "/api/v1/cluster/inventory", "/api/capacity", "/api/performance/current",
                "/api/v1/osd-inventory/collections/compare-config",
                "/api/v1/sessions/" + RESOURCE_ID + "/report",
                "/api/v1/cluster/collections", "/api/v1/cluster/metric-catalog", "/api/v1/cluster/resources",
                "/api/v1/as-is/collections", "/api/v1/osdmap-previews/capabilities",
            ):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path, headers=self.credentials()).status_code, 200)
            for path in (
                "/api/v1/sessions", "/api/v1/osd-inventory/collections",
                "/api/v1/cluster/collections", "/api/v1/exports",
                "/api/v1/as-is/observe", "/api/v1/as-is/export", "/api/v1/as-is/collections",
                "/api/v1/as-is/compare", "/api/v1/as-is/compare/export",
                "/api/v1/osdmap-previews", "/api/v1/osdmap-previews/" + RESOURCE_ID + "/export",
            ):
                with self.subTest(path=path):
                    self.assertEqual(client.post(path, headers={**self.credentials(), "X-Console-Request": "1"}).status_code, 200)

    def test_csrf_requires_trusted_origin_or_explicit_nonbrowser_marker(self):
        with self.client() as client:
            path = "/api/v1/sessions"
            response = client.post(path, headers=self.credentials())
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["detail"]["code"], "CONSOLE_CSRF_REJECTED")
            for origin in ("null", "https://attacker.test", "https://console.example.test.attacker.test"):
                with self.subTest(origin=origin):
                    self.assertEqual(client.post(path, headers={**self.credentials(), "Origin": origin, "X-Console-Request": "1"}).status_code, 403)
            self.assertEqual(client.post(path, headers={**self.credentials(), "Origin": "https://console.example.test"}).status_code, 200)

    def test_encoded_paths_cannot_bypass_closed_policy(self):
        with self.client() as client:
            for path in ("/api%2fv1/sessions", "/api/%2e%2e/jobs", "/api%5cv1/sessions", "/api/%252e%252e/jobs", "/api//v1/sessions"):
                with self.subTest(path=path):
                    response = client.post(path, headers={**self.credentials(), "X-Console-Request": "1"})
                    self.assertEqual(response.status_code, 400)
        self.assertEqual(self.reached, [])

    def test_direct_websocket_is_denied_with_valid_auth(self):
        with self.client() as client:
            with self.assertRaises(WebSocketDisconnect) as rejected:
                with client.websocket_connect("/ws/terminal", headers=self.credentials()):
                    self.fail("WebSocket must not open")
            self.assertEqual(rejected.exception.code, 1008)

    def test_lab_legacy_mode_preserves_existing_routes(self):
        configured = Settings(_env_file=None, app_env="test", execution_environment="lab",
            console_read_only=False, console_auth_username="", console_auth_password_hash=None,
            console_auth_password_hash_file=None, feature_upgrade=False, feature_lab=False,
            feature_legacy_rgw=False, feature_legacy_rbd=False)
        with self.client(configured) as client:
            self.assertEqual(client.post("/api/jobs").status_code, 200)

    def test_real_app_middleware_and_runtime_config_use_live_settings(self):
        from app.main import app

        configured = self.configured()
        with patch("app.main.get_settings", return_value=configured), patch("app.main.initialize"), patch("app.main.pool.close"):
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/runtime-config").status_code, 401)
                payload = client.get("/api/runtime-config", headers=self.credentials()).json()
                self.assertTrue(payload["console_read_only"])
                self.assertFalse(payload["features"]["legacy_rbd"])
                self.assertEqual(client.post("/api/jobs", headers=self.credentials()).status_code, 403)

    def test_retired_controllers_are_unreachable_in_readonly_and_lab_modes(self):
        from app.main import app
        lab = Settings(_env_file=None, app_env="test", execution_environment="lab",
            console_read_only=False, console_auth_username="", console_auth_password_hash=None,
            console_auth_password_hash_file=None, feature_upgrade=False, feature_lab=False,
            feature_legacy_rgw=False, feature_legacy_rbd=False)
        for configured in (self.configured(), lab):
            with patch("app.main.get_settings", return_value=configured), patch("app.main.initialize"), patch("app.main.pool.close"), \
                patch("app.modules.upgrade_common.api._service") as service:
                with TestClient(app) as client:
                    for path in ("/api/v1/upgrade-runs", "/api/v1/upgrade-batches", "/api/v1/qos-runs"):
                        response = client.post(path, headers={**self.credentials(), "X-Console-Request": "1"}, json={})
                        self.assertIn(response.status_code, {403, 404, 405})
                service.assert_not_called()


if __name__ == "__main__":
    unittest.main()
