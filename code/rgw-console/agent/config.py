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
_SAFE_SCOPE = re.compile(r"^[A-Za-z0-9_.-]+$")


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


def _csv_allowlist(
    name: str,
    default: str,
    *,
    allow_default_namespace: bool = False,
) -> frozenset[str]:
    """Parse a mandatory, deliberately narrow agent-side allowlist.

    The token ``@default`` represents the empty RBD namespace.  Empty CSV
    elements are ignored so a typo such as a trailing comma cannot silently
    enable the default namespace.
    """

    raw = os.environ.get(name, default)
    values: set[str] = set()
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        if allow_default_namespace and value == "@default":
            values.add("")
            continue
        if not _SAFE_SCOPE.fullmatch(value):
            raise AgentConfigError(f"{name} contains an unsupported value")
        values.add(value)
    if not values:
        raise AgentConfigError(f"{name} must contain at least one value")
    return frozenset(values)


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
    wipefs_binary: Path
    blkid_binary: Path
    mkfs_ext4_binary: Path
    mount_binary: Path
    umount_binary: Path
    sync_binary: Path
    rbd_allowed_pools: frozenset[str]
    rbd_allowed_namespaces: frozenset[str]
    rbd_allowed_image_prefixes: frozenset[str]
    rbd_mount_root: Path
    rbd_state_root: Path
    sysfs_root: Path
    proc_mountinfo_path: Path
    rbd_min_size_bytes: int
    rbd_max_size_bytes: int
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
        mount_root = _absolute_path("CEPH_RBD_MOUNT_ROOT", "/srv/ceph-lab/rbd")
        state_root = _absolute_path(
            "CEPH_RBD_STATE_ROOT", "/var/lib/rgw-console-agent"
        )
        if str(mount_root) in {"/", "\\"}:
            raise AgentConfigError("CEPH_RBD_MOUNT_ROOT must not be a filesystem root")
        if mount_root == state_root:
            raise AgentConfigError(
                "CEPH_RBD_STATE_ROOT must be separate from CEPH_RBD_MOUNT_ROOT"
            )
        min_size = _positive_int(
            "CEPH_RBD_MIN_SIZE_BYTES", str(16 * 1024 * 1024)
        )
        max_size = _positive_int(
            "CEPH_RBD_MAX_SIZE_BYTES", str(1024 * 1024 * 1024 * 1024)
        )
        if min_size > max_size:
            raise AgentConfigError(
                "CEPH_RBD_MIN_SIZE_BYTES must not exceed CEPH_RBD_MAX_SIZE_BYTES"
            )

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
            wipefs_binary=_absolute_path("WIPEFS_BINARY", "/usr/sbin/wipefs"),
            blkid_binary=_absolute_path("BLKID_BINARY", "/usr/sbin/blkid"),
            mkfs_ext4_binary=_absolute_path(
                "MKFS_EXT4_BINARY", "/usr/sbin/mkfs.ext4"
            ),
            mount_binary=_absolute_path("MOUNT_BINARY", "/usr/bin/mount"),
            umount_binary=_absolute_path("UMOUNT_BINARY", "/usr/bin/umount"),
            sync_binary=_absolute_path("SYNC_BINARY", "/usr/bin/sync"),
            rbd_allowed_pools=_csv_allowlist(
                "CEPH_RBD_ALLOWED_POOLS", "rbd-lab"
            ),
            rbd_allowed_namespaces=_csv_allowlist(
                "CEPH_RBD_ALLOWED_NAMESPACES",
                "@default",
                allow_default_namespace=True,
            ),
            rbd_allowed_image_prefixes=_csv_allowlist(
                "CEPH_RBD_ALLOWED_IMAGE_PREFIXES", "lab-"
            ),
            rbd_mount_root=mount_root,
            rbd_state_root=state_root,
            sysfs_root=_absolute_path("CEPH_AGENT_SYSFS_ROOT", "/sys"),
            proc_mountinfo_path=_absolute_path(
                "CEPH_AGENT_MOUNTINFO_PATH", "/proc/self/mountinfo"
            ),
            rbd_min_size_bytes=min_size,
            rbd_max_size_bytes=max_size,
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
