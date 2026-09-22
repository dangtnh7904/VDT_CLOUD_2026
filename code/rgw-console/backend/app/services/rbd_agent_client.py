from __future__ import annotations

import json
import math
import socket
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4


PROTOCOL_VERSION = 1
READ_ONLY_ACTIONS = frozenset(
    {
        "health",
        "capabilities",
        "ceph.status",
        "ceph.fsid",
        "ceph.versions",
        "ceph.osd_df",
        "ceph.osd_tree",
        "ceph.pool_ls_detail",
        "ceph.crush_rule_dump",
    }
)


class RbdAgentClientError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class RbdAgentClient:
    """Small JSON-lines client for the read-only Unix-socket host agent."""

    def __init__(
        self,
        socket_path: Path | str,
        *,
        expected_fsid: str,
        timeout_seconds: float = 35,
        max_response_bytes: int = 5 * 1024 * 1024,
    ) -> None:
        self.socket_path = Path(socket_path)
        if not self.socket_path.is_absolute() and not PurePosixPath(str(socket_path)).is_absolute():
            raise ValueError("agent socket path must be absolute")
        try:
            self.expected_fsid = str(UUID(expected_fsid))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("expected_fsid must be a UUID") from exc
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    @classmethod
    def from_settings(cls) -> "RbdAgentClient":
        from ..config import get_settings

        settings = get_settings()
        if not settings.ceph_expected_fsid:
            raise ValueError("CEPH_EXPECTED_FSID is required for host-agent calls")
        return cls(
            settings.ceph_agent_socket,
            expected_fsid=settings.ceph_expected_fsid,
        )

    def health(self) -> dict[str, Any]:
        return self.request("health")

    def capabilities(self) -> dict[str, Any]:
        return self.request("capabilities")

    def ceph_status(self) -> dict[str, Any]:
        return self.request("ceph.status")

    def ceph_fsid(self) -> dict[str, Any]:
        return self.request("ceph.fsid")

    def ceph_versions(self) -> dict[str, Any]:
        return self.request("ceph.versions")

    def ceph_osd_df(self) -> dict[str, Any]:
        return self.request("ceph.osd_df")

    def ceph_osd_tree(self) -> dict[str, Any]:
        return self.request("ceph.osd_tree")

    def ceph_pool_ls_detail(self) -> dict[str, Any]:
        return self.request("ceph.pool_ls_detail")

    def ceph_crush_rule_dump(self) -> dict[str, Any]:
        return self.request("ceph.crush_rule_dump")

    def request(self, action: str) -> dict[str, Any]:
        if action not in READ_ONLY_ACTIONS:
            raise RbdAgentClientError(
                "ACTION_NOT_ALLOWED",
                "The client only supports read-only host-agent actions",
            )

        request_id = str(uuid4())
        request = json.dumps(
            {
                "version": PROTOCOL_VERSION,
                "request_id": request_id,
                "action": action,
                "params": {},
            },
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"

        unix_family = getattr(socket, "AF_UNIX", None)
        if unix_family is None:
            raise RbdAgentClientError(
                "UNSUPPORTED_PLATFORM",
                "Unix domain sockets are unavailable on this platform",
            )

        try:
            with socket.socket(unix_family, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.connect(str(self.socket_path))
                connection.sendall(request)
                raw_response = self._read_line(connection)
        except (socket.timeout, TimeoutError) as exc:
            raise RbdAgentClientError(
                "AGENT_TIMEOUT",
                "Timed out while waiting for the Ceph host agent",
                retryable=True,
            ) from exc
        except OSError as exc:
            raise RbdAgentClientError(
                "AGENT_UNAVAILABLE",
                "Could not connect to the Ceph host agent",
                retryable=True,
            ) from exc

        response = self._decode_response(raw_response, request_id)
        if not response["ok"]:
            error = response["error"]
            raise RbdAgentClientError(
                error["code"],
                error["message"],
                retryable=error.get("retryable", False),
                details=error.get("details"),
            )

        result = response["result"]
        self._assert_fsid(result)
        return result

    def _read_line(self, connection: socket.socket) -> bytes:
        response = bytearray()
        while True:
            remaining = self.max_response_bytes + 1 - len(response)
            if remaining <= 0:
                raise RbdAgentClientError(
                    "AGENT_RESPONSE_TOO_LARGE",
                    "Host-agent response exceeded the configured size limit",
                )
            chunk = connection.recv(min(64 * 1024, remaining))
            if not chunk:
                raise RbdAgentClientError(
                    "AGENT_PROTOCOL_ERROR",
                    "Host agent closed the connection before completing a response",
                    retryable=True,
                )
            newline = chunk.find(b"\n")
            if newline >= 0:
                response.extend(chunk[:newline])
                if any(byte not in b" \t\r\n" for byte in chunk[newline + 1 :]):
                    raise RbdAgentClientError(
                        "AGENT_PROTOCOL_ERROR",
                        "Host agent returned data after the response line",
                    )
                break
            response.extend(chunk)
        if len(response) > self.max_response_bytes:
            raise RbdAgentClientError(
                "AGENT_RESPONSE_TOO_LARGE",
                "Host-agent response exceeded the configured size limit",
            )
        return bytes(response)

    @staticmethod
    def _decode_response(raw: bytes, request_id: str) -> dict[str, Any]:
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR",
                "Host agent returned an invalid JSON response",
            ) from exc
        if not isinstance(response, dict):
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR",
                "Host-agent response must be a JSON object",
            )
        if response.get("version") != PROTOCOL_VERSION:
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR",
                "Host agent returned an unsupported protocol version",
            )
        if not isinstance(response.get("ok"), bool):
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR",
                "Host-agent response is missing an ok flag",
            )
        if response["ok"]:
            if response.get("request_id") != request_id:
                raise RbdAgentClientError(
                    "AGENT_PROTOCOL_ERROR",
                    "Host-agent response request_id does not match",
                )
            if not isinstance(response.get("result"), dict):
                raise RbdAgentClientError(
                    "AGENT_PROTOCOL_ERROR",
                    "Successful host-agent response is missing a result object",
                )
        else:
            if response.get("request_id") not in {None, request_id}:
                raise RbdAgentClientError(
                    "AGENT_PROTOCOL_ERROR",
                    "Host-agent error response request_id does not match",
                )
            error = response.get("error")
            if (
                not isinstance(error, dict)
                or not isinstance(error.get("code"), str)
                or not isinstance(error.get("message"), str)
            ):
                raise RbdAgentClientError(
                    "AGENT_PROTOCOL_ERROR",
                    "Failed host-agent response is missing a valid error object",
                )
        return response

    def _assert_fsid(self, result: dict[str, Any]) -> None:
        observed = result.get("fsid")
        try:
            normalized = str(UUID(observed))
        except (ValueError, TypeError, AttributeError) as exc:
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR",
                "Host-agent result is missing a valid cluster FSID",
            ) from exc
        if normalized != self.expected_fsid:
            raise RbdAgentClientError(
                "FSID_MISMATCH",
                "Host-agent result came from an unexpected Ceph cluster",
                details={
                    "expected_fsid": self.expected_fsid,
                    "observed_fsid": normalized,
                },
            )
