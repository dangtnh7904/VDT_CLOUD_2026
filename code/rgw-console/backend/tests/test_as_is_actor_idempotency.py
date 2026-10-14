from __future__ import annotations

import base64
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.config import Settings
from app.modules.as_is.api import router
from app.modules.as_is.service import AsIsError, AsIsService
from app.platform.security.middleware import ConsoleSecurityMiddleware


FSID = "11111111-2222-3333-4444-555555555555"
PASSWORD = "test-only-actor-idempotency-password"
SALT = b"test-only-actor-salt"
PASSWORD_HASH = "pbkdf2_sha256$600000$" + base64.b64encode(SALT).decode() + "$" + base64.b64encode(
    hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), SALT, 600_000)
).decode()


class MemoryRepository:
    def __init__(self):
        self.rows = {}
        self.actors = []

    def get(self, collection_id, *, include_deleted=False, **identity):
        row = self.rows.get(str(collection_id))
        if not row or any(str(row.get(key)) != str(value) for key, value in identity.items()):
            return None
        return copy.deepcopy(row)

    def save(self, payload, *, sha256, request_hash, actor):
        self.rows[payload["id"]] = {
            **copy.deepcopy(payload), "payload": copy.deepcopy(payload),
            "sha256": sha256, "request_hash": request_hash, "deleted_at": None,
        }
        self.actors.append(actor)


class ActorIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hash_file = Path(self.directory.name) / "password.hash"
        self.hash_file.write_text(PASSWORD_HASH, encoding="utf-8")
        self.users_file = Path(self.directory.name) / "users.json"
        self.users_file.write_text(json.dumps({"version": 1, "users": [
            {"username": username, "role": "operator", "password_hash": PASSWORD_HASH}
            for username in ("operator-one", "operator-two")
        ]}), encoding="utf-8")

    def settings(self, mode="anonymous"):
        values = {
            "app_env": "test", "execution_environment": "lab", "console_read_only": True,
            "feature_legacy_rgw": False, "feature_legacy_rbd": False,
            "cluster_id": "lab", "ceph_expected_fsid": FSID,
            "console_auth_username": "", "console_auth_password_hash_file": None,
            "console_auth_users_file": None, "console_auth_password_hash": None,
            "cors_origins": "https://console.example.test",
        }
        if mode == "basic":
            values.update(console_auth_username="operator-one", console_auth_password_hash_file=self.hash_file)
        if mode == "users":
            values["console_auth_users_file"] = self.users_file
        return Settings(_env_file=None, **values)

    def service(self, settings):
        repo = MemoryRepository()
        service = AsIsService(settings, repository=repo, client=Mock())
        service.identity = Mock(return_value={"cluster_id": "lab", "fsid": FSID})
        service.observe = Mock(side_effect=lambda **kwargs: {
            "id": str(uuid4()), "cluster_id": "lab", "fsid": FSID,
            "requested_daemon_keys": ["mon.one"], "daemons": [], "quality": "VALID",
        })
        return service, repo

    def collect(self, service, actor, **overrides):
        request = {"daemon_keys": ["mon.one"], "phase": "BEFORE", "note": "shared request",
                   "idempotency_key": "same-client-request-key", "actor": actor}
        request.update(overrides)
        return service.create(**request)

    def test_same_authenticated_actor_replays_without_new_collection_or_event(self):
        for mode in ("basic", "users"):
            with self.subTest(mode=mode):
                service, repo = self.service(self.settings(mode))
                first = self.collect(service, "operator-one")
                replay = self.collect(service, "operator-one")
                self.assertEqual(first, replay)
                self.assertEqual(service.observe.call_count, 1)
                self.assertEqual(repo.actors, ["operator-one"])
                with self.assertRaises(AsIsError) as caught:
                    self.collect(service, "operator-one", phase="AFTER")
                self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")

    def test_different_authenticated_users_share_key_without_sharing_collection_actor(self):
        service, repo = self.service(self.settings("users"))
        first = self.collect(service, "operator-one")
        second = self.collect(service, "operator-two")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual([first["actor"], second["actor"]], ["operator-one", "operator-two"])
        self.assertEqual(repo.actors, ["operator-one", "operator-two"])
        self.assertEqual(service.observe.call_count, 2)
        self.assertEqual(self.collect(service, "operator-two"), second)
        self.assertEqual(repo.actors, ["operator-one", "operator-two"])

    def test_anonymous_lab_uuid_and_historical_replay_remain_unchanged(self):
        service, repo = self.service(self.settings())
        first = self.collect(service, "old-lab-actor")
        expected = str(uuid5(NAMESPACE_URL, f"as-is:lab:{FSID}:same-client-request-key"))
        self.assertEqual(first["id"], expected)
        self.assertEqual(self.collect(service, "new-lab-actor"), first)
        self.assertEqual(repo.actors, ["old-lab-actor"])
        self.assertEqual(service.observe.call_count, 1)

    def test_real_api_scopes_key_to_authenticated_username_even_when_x_actor_is_spoofed(self):
        configured = self.settings("users")
        service, repo = self.service(configured)
        app = FastAPI()
        app.include_router(router)
        app.add_middleware(ConsoleSecurityMiddleware, settings_provider=lambda: configured)
        body = {"daemon_keys": ["mon.one"], "phase": "BEFORE", "note": "shared request"}

        def headers(username):
            return {"Authorization": "Basic " + base64.b64encode(f"{username}:{PASSWORD}".encode()).decode(),
                    "X-Console-Request": "1", "Idempotency-Key": "same-client-request-key", "X-Actor": "spoofed"}

        with patch("app.modules.as_is.api._service", return_value=service), TestClient(app) as client:
            first = client.post("/api/v1/as-is/collections", json=body, headers=headers("operator-one"))
            second = client.post("/api/v1/as-is/collections", json=body, headers=headers("operator-two"))
            replay = client.post("/api/v1/as-is/collections", json=body, headers=headers("operator-one"))
        self.assertEqual([first.status_code, second.status_code, replay.status_code], [201, 201, 201])
        self.assertNotEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(repo.actors, ["operator-one", "operator-two"])
        self.assertEqual(service.observe.call_count, 2)


if __name__ == "__main__":
    unittest.main()
