from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID


class AgentConfigError(ValueError):
    """The host-agent configuration is unsafe or incomplete."""


_SAFE_ENTITY = re.compile(r"^[A-Za-z0-9_.-]+$")


def _positive_int(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise AgentConfigError(f"{name} must be an integer") from exc
    if value <= 0:
        raise AgentConfigError(f"{name} must be greater than zero")
    return value


def _positive_float(name: str, default: str) -> float:
    raw = os.environ.get(name, default)
    try:
        value = float(raw)
    except ValueError as exc:
        raise AgentConfigError(f"{name} must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise AgentConfigError(f"{name} must be greater than zero")
    return value


def _absolute_path(name: str, default: str) -> Path:
    raw = os.environ.get(name, default)
    value = Path(raw)
    if not value.is_absolute() and not PurePosixPath(raw).is_absolute():
        raise AgentConfigError(f"{name} must be an absolute path")
    return value


def _expected_fsid() -> str:
    raw = os.environ.get("CEPH_EXPECTED_FSID", "").strip()
    if not raw:
        raise AgentConfigError("CEPH_EXPECTED_FSID is required")
    try:
        return str(UUID(raw))
    except ValueError as exc:
        raise AgentConfigError("CEPH_EXPECTED_FSID must be a UUID") from exc


def _allowed_uids() -> frozenset[int]:
    raw = os.environ.get("CEPH_AGENT_ALLOWED_UIDS", "0")
    try:
        values = frozenset(int(item.strip()) for item in raw.split(",") if item.strip())
    except ValueError as exc:
        raise AgentConfigError("CEPH_AGENT_ALLOWED_UIDS must contain numeric UIDs") from exc
    if not values or any(value < 0 for value in values):
        raise AgentConfigError("CEPH_AGENT_ALLOWED_UIDS must contain non-negative UIDs")
    return values


def _socket_mode() -> int:
    raw = os.environ.get("CEPH_AGENT_SOCKET_MODE", "0660")
    try:
        mode = int(raw, 8)
    except ValueError as exc:
        raise AgentConfigError("CEPH_AGENT_SOCKET_MODE must be an octal mode") from exc
    if mode not in {0o600, 0o660}:
        raise AgentConfigError("CEPH_AGENT_SOCKET_MODE must be 0600 or 0660")
    return mode


@dataclass(frozen=True)
class AgentConfig:
    expected_fsid: str
    socket_path: Path
    socket_mode: int
    socket_group: str | None
    allowed_uids: frozenset[int]
    cluster_name: str
    conf_path: Path
    keyring_path: Path
    client_entity: str
    ceph_binary: Path
    rbd_binary: Path
    command_timeout_seconds: float
    client_timeout_seconds: float
    max_command_output_bytes: int
    max_request_bytes: int
    max_response_bytes: int
    max_connections: int

    @classmethod
    def from_env(cls) -> "AgentConfig":
        cluster_name = os.environ.get("CEPH_CLUSTER_NAME", "ceph").strip()
        if not cluster_name or not _SAFE_ENTITY.fullmatch(cluster_name):
            raise AgentConfigError("CEPH_CLUSTER_NAME contains unsupported characters")

        client_id = os.environ.get("CEPH_CLIENT_ID", "admin").strip()
        if not client_id or not _SAFE_ENTITY.fullmatch(client_id):
            raise AgentConfigError("CEPH_CLIENT_ID contains unsupported characters")
        client_entity = client_id if client_id.startswith("client.") else f"client.{client_id}"

        socket_path = _absolute_path(
            "CEPH_AGENT_SOCKET", "/run/rgw-console/ceph-agent.sock"
        )
        if len(os.fsencode(socket_path)) > 100:
            raise AgentConfigError("CEPH_AGENT_SOCKET is too long for a Unix socket")

        socket_group = os.environ.get("CEPH_AGENT_SOCKET_GROUP", "rgw-console").strip()

        return cls(
            expected_fsid=_expected_fsid(),
            socket_path=socket_path,
            socket_mode=_socket_mode(),
            socket_group=socket_group or None,
            allowed_uids=_allowed_uids(),
            cluster_name=cluster_name,
            conf_path=_absolute_path("CEPH_CONF_PATH", "/etc/ceph/ceph.conf"),
            keyring_path=_absolute_path(
                "CEPH_KEYRING_PATH", "/etc/ceph/ceph.client.admin.keyring"
            ),
            client_entity=client_entity,
            ceph_binary=_absolute_path("CEPH_BINARY", "/usr/bin/ceph"),
            rbd_binary=_absolute_path("RBD_BINARY", "/usr/bin/rbd"),
            command_timeout_seconds=_positive_float(
                "CEPH_AGENT_COMMAND_TIMEOUT_SECONDS", "15"
            ),
            client_timeout_seconds=_positive_float(
                "CEPH_AGENT_CLIENT_TIMEOUT_SECONDS", "10"
            ),
            max_command_output_bytes=_positive_int(
                "CEPH_AGENT_MAX_COMMAND_OUTPUT_BYTES", str(4 * 1024 * 1024)
            ),
            max_request_bytes=_positive_int(
                "CEPH_AGENT_MAX_REQUEST_BYTES", str(64 * 1024)
            ),
            max_response_bytes=_positive_int(
                "CEPH_AGENT_MAX_RESPONSE_BYTES", str(5 * 1024 * 1024)
            ),
            max_connections=_positive_int("CEPH_AGENT_MAX_CONNECTIONS", "16"),
        )
