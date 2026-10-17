from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

from app.api.health import compatibility_health, liveness, readiness_snapshot
from app.config import Settings
from app.main import app, frontend_asset


FSID = "11111111-2222-3333-4444-555555555555"
TOKEN = "executor-token-with-at-least-thirty-two-characters"


def settings(**overrides) -> Settings:
    values = {
        # Health/routing fixtures are lab-policy tests, independent of the
        # image's safe production read-only environment defaults.
        "app_env": "test",
        "execution_environment": "lab",
        "console_read_only": False,
        "console_auth_username": "",
        "console_auth_password_hash": None,
        "console_auth_password_hash_file": None,
        "feature_upgrade": True,
        "feature_lab": False,
        "feature_legacy_rgw": False,
        "feature_legacy_rbd": False,
        "cluster_id": "lab-a",
        "ceph_expected_fsid": FSID,
        "ceph_executor_token": TOKEN,
        "performance_source": "application_only",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _Cursor:
    def execute(self, _query):
        return self

    def fetchone(self):
        return {"version": 19}


@contextmanager
def database_connection():
    yield _Cursor()


class HealthContractTests(unittest.TestCase):
    def test_liveness_is_process_only(self):
        self.assertEqual(liveness(), {"status": "ok"})

    def test_upgrade_only_readiness_never_calls_rgw(self):
        configured = settings()
        executor = Mock()
        executor.health.return_value = {"ok": True}

        with (
            patch("app.api.health.connection", database_connection),
            patch("app.api.health.s3_client") as rgw,
            patch("app.api.health.ExecutorClient", return_value=executor),
        ):
            payload, status_code = readiness_snapshot(configured)

        self.assertEqual(status_code, 200)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["dependencies"]["rgw"]["status"], "disabled")
        self.assertEqual(payload["dependencies"]["ceph_executor"]["status"], "ready")
        rgw.assert_not_called()

    def test_required_executor_failure_blocks_readiness_without_secret_details(self):
        configured = settings()
        with (
            patch("app.api.health.connection", database_connection),
            patch("app.api.health.ExecutorClient", side_effect=RuntimeError(TOKEN)),
        ):
            payload, status_code = readiness_snapshot(configured)

        self.assertEqual(status_code, 503)
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["blocking_dependencies"], ["ceph_executor"])
        self.assertEqual(
            payload["dependencies"]["ceph_executor"]["code"],
            "EXECUTOR_UNAVAILABLE",
        )
        self.assertNotIn(TOKEN, json.dumps(payload))

    def test_invalid_feature_config_is_not_probed(self):
        configured = settings(
            feature_upgrade=False,
            feature_legacy_rgw=True,
            feature_legacy_rbd=False,
            ceph_expected_fsid=None,
            ceph_executor_token=None,
            rgw_endpoint_url=None,
            rgw_access_key=None,
            rgw_secret_key=None,
        )
        with (
            patch("app.api.health.connection", database_connection),
            patch("app.api.health.s3_client") as rgw,
            patch("app.api.health.ExecutorClient") as executor,
        ):
            payload, status_code = readiness_snapshot(configured)

        self.assertEqual(status_code, 503)
        self.assertEqual(payload["dependencies"]["rgw"]["code"], "RGW_CONFIG_INVALID")
        self.assertEqual(payload["dependencies"]["ceph_executor"]["status"], "disabled")
        rgw.assert_not_called()
        executor.assert_not_called()

    def test_compatibility_health_is_ok_when_rgw_is_disabled(self):
        configured = settings()
        executor = Mock()
        executor.health.return_value = {"ok": True}
        with (
            patch("app.api.health.get_settings", return_value=configured),
            patch("app.api.health.connection", database_connection),
            patch("app.api.health.s3_client") as rgw,
            patch("app.api.health.ExecutorClient", return_value=executor),
        ):
            response = compatibility_health()

        self.assertIsInstance(response, dict)
        self.assertEqual(response["status"], "ok")
        self.assertIsNone(response["endpoint"])
        rgw.assert_not_called()

    def test_configured_frontend_is_required_for_readiness(self):
        configured = settings(frontend_dist_path=Path("missing-frontend-build"))
        executor = Mock()
        with (
            patch("app.api.health.connection", database_connection),
            patch("app.api.health.ExecutorClient", return_value=executor),
        ):
            payload, status_code = readiness_snapshot(configured)

        self.assertEqual(status_code, 503)
        self.assertIn("frontend", payload["blocking_dependencies"])


class FrontendStaticTests(unittest.TestCase):
    def test_serves_assets_and_spa_fallback_from_configured_root(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            (root / "assets").mkdir()
            (root / "index.html").write_text("<main>console</main>", encoding="utf-8")
            (root / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
            configured = settings(frontend_dist_path=root)

            with patch("app.main.get_settings", return_value=configured):
                asset = frontend_asset("assets/app.js")
                fallback = frontend_asset("upgrade/runs/active")

            self.assertIsInstance(asset, FileResponse)
            self.assertEqual(Path(asset.path), root / "assets" / "app.js")
            self.assertIsInstance(fallback, FileResponse)
            self.assertEqual(Path(fallback.path), root / "index.html")

    def test_asgi_route_order_keeps_api_outside_spa_fallback(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            (root / "index.html").write_text("<main>console</main>", encoding="utf-8")
            configured = settings(frontend_dist_path=root)

            with patch("app.main.get_settings", return_value=configured):
                client = TestClient(app)
                self.assertEqual(client.get("/upgrade/runs").status_code, 200)
                self.assertEqual(client.get("/api/not-a-route").status_code, 404)
                self.assertEqual(client.get("/ws/not-a-route").status_code, 404)

    def test_frontend_fallback_never_handles_api_or_websocket_paths(self):
        configured = settings(frontend_dist_path=Path("missing"))
        with patch("app.main.get_settings", return_value=configured):
            for path in ("api/unknown", "ws/session"):
                with self.subTest(path=path), self.assertRaises(HTTPException) as raised:
                    frontend_asset(path)
                self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
