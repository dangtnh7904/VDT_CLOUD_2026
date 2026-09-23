from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from agent.ceph_cli import ACTION_SCHEMAS, ALLOWED_ACTIONS, CephInventoryRunner
from agent.config import AgentConfigError, _positive_float
from agent.errors import AgentError
from agent.protocol import decode_request
from agent.rbd import RbdActionRunner
from backend.app.services.rbd_agent_client import RbdAgentClient, RbdAgentClientError


class AgentConfigTests(unittest.TestCase):
    def test_float_limits_reject_non_finite_values(self) -> None:
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value), patch.dict(os.environ, {"TEST_TIMEOUT": value}):
                with self.assertRaises(AgentConfigError):
                    _positive_float("TEST_TIMEOUT", "1")


class ProtocolTests(unittest.TestCase):
    def test_duplicate_fields_are_rejected(self) -> None:
        request_id = str(uuid4())
        raw = (
            '{"version":1,"request_id":"'
            + request_id
            + '","action":"health","action":"health","params":{}}'
        ).encode()
        with self.assertRaises(AgentError) as caught:
            decode_request(raw, {"health"})
        self.assertEqual(caught.exception.code, "INVALID_JSON")

    def test_unscoped_rbd_inventory_is_not_exposed(self) -> None:
        self.assertNotIn("rbd.device_list", ALLOWED_ACTIONS)

    def test_rbd_mutation_rejects_unknown_parameters(self) -> None:
        request_id = str(uuid4())
        volume_id = str(uuid4())
        action_id = str(uuid4())
        raw = json.dumps(
            {
                "version": 1,
                "request_id": request_id,
                "action": "rbd.image.create",
                "params": {
                    "volume_id": volume_id,
                    "action_id": action_id,
                    "fence_token": 1,
                    "pool": "rbd-lab",
                    "namespace": "",
                    "image_name": "lab-volume",
                    "size_bytes": 16 * 1024 * 1024,
                    "force": True,
                },
            }
        ).encode()
        with self.assertRaises(AgentError) as caught:
            decode_request(raw, ALLOWED_ACTIONS, ACTION_SCHEMAS)
        self.assertEqual(caught.exception.code, "INVALID_PARAMS")


class BoundedCommandTests(unittest.TestCase):
    @staticmethod
    def _runner(*, limit: int = 1024, timeout: float = 2.0) -> CephInventoryRunner:
        config = SimpleNamespace(
            max_command_output_bytes=limit,
            command_timeout_seconds=timeout,
        )
        return CephInventoryRunner(config)  # type: ignore[arg-type]

    def test_small_output_is_returned(self) -> None:
        result = self._runner()._invoke(
            (sys.executable, "-c", "print('bounded')"),
            "test",
        )
        self.assertEqual(result.strip(), "bounded")

    def test_large_output_is_stopped_at_limit(self) -> None:
        with self.assertRaises(AgentError) as caught:
            self._runner(limit=128)._invoke(
                (sys.executable, "-c", "import sys; sys.stdout.write('x' * 10000)"),
                "test",
            )
        self.assertEqual(caught.exception.code, "COMMAND_OUTPUT_LIMIT")

    def test_timeout_is_retryable(self) -> None:
        with self.assertRaises(AgentError) as caught:
            self._runner(timeout=0.05)._invoke(
                (sys.executable, "-c", "import time; time.sleep(1)"),
                "test",
            )
        self.assertEqual(caught.exception.code, "COMMAND_TIMEOUT")
        self.assertTrue(caught.exception.retryable)


class RbdFenceTests(unittest.TestCase):
    def test_same_in_progress_action_may_reenter_observation_checks(self) -> None:
        runner = RbdActionRunner.__new__(RbdActionRunner)
        params = {
            "volume_id": str(uuid4()),
            "action_id": str(uuid4()),
            "fence_token": 7,
        }
        record = {
            "last_fence_token": 7,
            "actions": {
                params["action_id"]: {
                    "action": "rbd.image.map",
                    "fingerprint": runner._fingerprint(params),
                    "state": "IN_PROGRESS",
                }
            },
        }
        self.assertIsNone(runner._replay_or_fence(record, "rbd.image.map", params))

    def test_distinct_action_requires_a_newer_fence(self) -> None:
        runner = RbdActionRunner.__new__(RbdActionRunner)
        params = {
            "volume_id": str(uuid4()),
            "action_id": str(uuid4()),
            "fence_token": 7,
        }
        with self.assertRaises(AgentError) as caught:
            runner._replay_or_fence(
                {"last_fence_token": 7, "actions": {}},
                "rbd.image.map",
                params,
            )
        self.assertEqual(caught.exception.code, "FENCE_REJECTED")


class ClientProtocolTests(unittest.TestCase):
    def test_rbd_payload_is_unwrapped_and_action_bound(self) -> None:
        payload = RbdAgentClient._rbd_data(
            {
                "fsid": str(uuid4()),
                "action": "rbd.image.info",
                "data": {"image_id": "abc"},
            },
            "rbd.image.info",
        )
        self.assertEqual(payload["image_id"], "abc")
        self.assertIn("fsid", payload)

        with self.assertRaises(RbdAgentClientError):
            RbdAgentClient._rbd_data(
                {"action": "rbd.image.list", "data": {}},
                "rbd.image.info",
            )

    def test_pre_request_error_may_have_null_request_id(self) -> None:
        request_id = str(uuid4())
        raw = json.dumps(
            {
                "version": 1,
                "request_id": None,
                "ok": False,
                "error": {
                    "code": "SERVER_BUSY",
                    "message": "busy",
                    "retryable": True,
                },
            }
        ).encode()
        decoded = RbdAgentClient._decode_response(raw, request_id)
        self.assertFalse(decoded["ok"])

    def test_success_must_match_request_id(self) -> None:
        raw = json.dumps(
            {
                "version": 1,
                "request_id": str(uuid4()),
                "ok": True,
                "result": {},
            }
        ).encode()
        with self.assertRaises(RbdAgentClientError):
            RbdAgentClient._decode_response(raw, str(uuid4()))

    def test_client_rejects_non_finite_timeout(self) -> None:
        with self.assertRaises(ValueError):
            RbdAgentClient(
                Path("/run/rgw-console/ceph-agent.sock"),
                expected_fsid=str(uuid4()),
                timeout_seconds=float("nan"),
            )


if __name__ == "__main__":
    unittest.main()
