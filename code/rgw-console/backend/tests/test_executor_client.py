import unittest
from unittest.mock import patch

import httpx

from app.services.executor_client import ExecutorClient, ExecutorClientError
from app.api.rbd import _executor_status


FSID = "17c77e12-a16a-11f1-838e-cf68e9c001d8"
TOKEN = "test-executor-token-with-at-least-32-characters"


class ExecutorClientTests(unittest.TestCase):
    def client(self, handler):
        return ExecutorClient(
            "http://executor:3001",
            token=TOKEN,
            expected_fsid=FSID,
            transport=httpx.MockTransport(handler),
        )

    def test_authenticated_protocol_and_rbd_payload(self):
        def handler(request: httpx.Request):
            self.assertEqual(request.url.path, "/internal/v1/execute")
            self.assertEqual(request.headers["X-Executor-Token"], TOKEN)
            payload = __import__("json").loads(request.content)
            return httpx.Response(
                200,
                json={
                    "version": 1,
                    "request_id": payload["request_id"],
                    "ok": True,
                    "result": {
                        "action": payload["action"],
                        "fsid": FSID,
                        "collected_at": "2026-09-23T00:00:00Z",
                        "data": {"pools": ["rbd-lab"]},
                    },
                },
            )

        result = self.client(handler).rbd_pool_list()
        self.assertEqual(result["pools"], ["rbd-lab"])
        self.assertEqual(result["fsid"], FSID)

    def test_file_and_terminal_actions_use_the_closed_executor_protocol(self):
        seen = []

        def handler(request: httpx.Request):
            payload = __import__("json").loads(request.content)
            seen.append(payload["action"])
            return httpx.Response(
                200,
                json={
                    "version": 1,
                    "request_id": payload["request_id"],
                    "ok": True,
                    "result": {
                        "action": payload["action"],
                        "fsid": FSID,
                        "data": {"items": []} if payload["action"] == "rbd.files.list" else {"ticket": "opaque"},
                    },
                },
            )

        params = {
            "volume_id": "11111111-1111-4111-8111-111111111111",
            "pool": "rbd-lab",
            "namespace": "",
            "image_name": "lab-test",
            "image_id": "abc123",
            "device_major": 251,
            "device_minor": 0,
            "fs_uuid": "22222222-2222-4222-8222-222222222222",
        }
        client = self.client(handler)
        self.assertEqual(client.rbd_file_action("rbd.files.list", {**params, "path": "/"})["items"], [])
        self.assertEqual(client.terminal_ticket(params)["ticket"], "opaque")
        self.assertEqual(seen, ["rbd.files.list", "rbd.terminal.ticket.create"])
        with self.assertRaises(ExecutorClientError):
            client.rbd_file_action("shell", params)

    def test_executor_error_mapping(self):
        def handler(request: httpx.Request):
            payload = __import__("json").loads(request.content)
            return httpx.Response(
                409,
                json={
                    "version": 1,
                    "request_id": payload["request_id"],
                    "ok": False,
                    "error": {"code": "VOLUME_BUSY", "message": "busy", "retryable": False},
                },
            )

        with self.assertRaises(ExecutorClientError) as raised:
            self.client(handler).request("rbd.device.list")
        self.assertEqual(raised.exception.code, "VOLUME_BUSY")

    def test_fsid_mismatch_is_rejected(self):
        def handler(request: httpx.Request):
            payload = __import__("json").loads(request.content)
            return httpx.Response(
                200,
                json={
                    "version": 1,
                    "request_id": payload["request_id"],
                    "ok": True,
                    "result": {
                        "action": payload["action"],
                        "fsid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                        "data": {},
                    },
                },
            )

        with self.assertRaises(ExecutorClientError) as raised:
            self.client(handler).health()
        self.assertEqual(raised.exception.code, "FSID_MISMATCH")

    def test_configuration_is_fail_closed(self):
        with self.assertRaises(ValueError):
            ExecutorClient("http://user:secret@executor:3001", token=TOKEN, expected_fsid=FSID)
        with self.assertRaises(ValueError):
            ExecutorClient("http://executor:3001", token="short", expected_fsid=FSID)

    @patch("app.api.rbd.ExecutorClient.from_settings")
    def test_public_executor_status_preserves_top_level_capabilities(self, factory):
        factory.return_value.capabilities.return_value = {
            "fsid": FSID,
            "collected_at": "2026-09-24T00:00:00Z",
            "executor_version": "1.0.0",
            "protocol_version": 1,
            "actions": ["health", "capabilities"],
            "rbd_scope": {"pools": ["rbd-lab"]},
        }

        response = _executor_status("capabilities")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["fsid"], FSID)
        self.assertEqual(response["collected_at"], "2026-09-24T00:00:00Z")
        self.assertEqual(response["data"]["actions"], ["health", "capabilities"])
        self.assertEqual(response["data"]["rbd_scope"]["pools"], ["rbd-lab"])


if __name__ == "__main__":
    unittest.main()
