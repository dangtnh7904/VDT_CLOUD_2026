from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from agent.ceph_cli import ALLOWED_ACTIONS, CephInventoryRunner
from agent.config import AgentConfigError, _positive_float
from agent.errors import AgentError
from agent.protocol import decode_request
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


class ClientProtocolTests(unittest.TestCase):
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
