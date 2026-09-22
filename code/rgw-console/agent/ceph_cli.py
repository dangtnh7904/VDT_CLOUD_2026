from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from . import AGENT_VERSION
from .config import AgentConfig
from .errors import AgentError
from .protocol import PROTOCOL_VERSION, validate_action_params
from .rbd import RBD_ACTIONS, RBD_ACTION_SCHEMAS, RbdActionRunner


INVENTORY_COMMANDS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "ceph.status": ("ceph", ("status", "--format=json"), "json"),
    "ceph.fsid": ("ceph", ("fsid",), "fsid"),
    "ceph.versions": ("ceph", ("versions", "--format=json"), "json"),
    "ceph.osd_df": ("ceph", ("osd", "df", "--format=json"), "json"),
    "ceph.osd_tree": ("ceph", ("osd", "tree", "--format=json"), "json"),
    "ceph.pool_ls_detail": (
        "ceph",
        ("osd", "pool", "ls", "detail", "--format=json"),
        "json",
    ),
    "ceph.crush_rule_dump": (
        "ceph",
        ("osd", "crush", "rule", "dump", "--format=json"),
        "json",
    ),
}

CONTROL_ACTIONS = frozenset({"health", "capabilities"})
ALLOWED_ACTIONS = frozenset(INVENTORY_COMMANDS) | CONTROL_ACTIONS | RBD_ACTIONS
ACTION_SCHEMAS: dict[str, dict[str, dict[str, str]]] = {
    **{
        action: {"required": {}, "optional": {}}
        for action in frozenset(INVENTORY_COMMANDS) | CONTROL_ACTIONS
    },
    **RBD_ACTION_SCHEMAS,
}

_SENSITIVE_FIELD = re.compile(
    r"^(?:key|secret|secret_key|access_key|password|token|credential|"
    r"private_key|keyring)$",
    re.IGNORECASE,
)
_TEXT_SECRET = re.compile(
    r"(?i)(\b(?:secret(?:_key)?|access_key|password|token|private_key|key)\b"
    r"\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_URL_PASSWORD = re.compile(r"(://[^:/\s]+:)[^@/\s]+(@)")


def redact_text(value: str) -> str:
    value = _TEXT_SECRET.sub(r"\1<redacted>", value)
    return _URL_PASSWORD.sub(r"\1<redacted>\2", value)


def redact_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if _SENSITIVE_FIELD.fullmatch(str(key)) else redact_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class CephInventoryRunner:
    """Execute a closed set of read-only Ceph inventory commands."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        }
        # Windows is supported only for the mocked/unit-test harness, but its
        # process loader requires these host values even with an absolute argv.
        if os.name == "nt":  # pragma: no cover - platform-specific
            for name in ("SYSTEMROOT", "WINDIR", "COMSPEC"):
                if name in os.environ:
                    self._environment[name] = os.environ[name]
        self._rbd_actions: RbdActionRunner | None = None

    @property
    def allowed_actions(self) -> frozenset[str]:
        return ALLOWED_ACTIONS

    @property
    def action_schemas(self) -> dict[str, dict[str, dict[str, str]]]:
        return ACTION_SCHEMAS

    def dispatch(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action not in ALLOWED_ACTIONS:
            raise AgentError("ACTION_NOT_ALLOWED", "The requested action is not allowed")
        validate_action_params(action, params, ACTION_SCHEMAS)

        observed_fsid = self._assert_expected_fsid()
        collected_at = datetime.now(timezone.utc).isoformat()

        if action in RBD_ACTIONS:
            if self._rbd_actions is None:
                self._rbd_actions = RbdActionRunner(self.config, self._invoke, self._argv)
            result = self._rbd_actions.dispatch(action, params)
            return {
                "fsid": observed_fsid,
                "action": action,
                "data": result,
                "collected_at": collected_at,
            }

        if action == "health":
            return {
                "status": "ok",
                "agent_version": AGENT_VERSION,
                "protocol_version": PROTOCOL_VERSION,
                "read_only": False,
                "fsid": observed_fsid,
                "collected_at": collected_at,
            }

        if action == "capabilities":
            return {
                "agent_version": AGENT_VERSION,
                "protocol_version": PROTOCOL_VERSION,
                "read_only": False,
                "fsid": observed_fsid,
                "actions": sorted(ALLOWED_ACTIONS),
                "action_schemas": ACTION_SCHEMAS,
                "rbd_scope": RbdActionRunner(
                    self.config, self._invoke, self._argv
                ).capability_scope(),
                "collected_at": collected_at,
            }

        command_kind, suffix, parser = INVENTORY_COMMANDS[action]
        if action == "ceph.fsid":
            data: Any = {"fsid": observed_fsid}
        else:
            stdout = self._invoke(self._argv(command_kind, suffix), action)
            data = self._parse_json(stdout, action) if parser == "json" else stdout.strip()

        return {
            "fsid": observed_fsid,
            "action": action,
            "data": data,
            "collected_at": collected_at,
        }

    def _assert_expected_fsid(self) -> str:
        stdout = self._invoke(self._argv("ceph", ("fsid",)), "ceph.fsid")
        try:
            observed = str(UUID(stdout.strip()))
        except ValueError as exc:
            raise AgentError(
                "INVALID_CEPH_OUTPUT",
                "ceph fsid returned an invalid UUID",
                details={"action": "ceph.fsid"},
            ) from exc
        if observed != self.config.expected_fsid:
            raise AgentError(
                "FSID_MISMATCH",
                "Connected Ceph cluster does not match CEPH_EXPECTED_FSID",
                details={
                    "expected_fsid": self.config.expected_fsid,
                    "observed_fsid": observed,
                },
            )
        return observed

    def _argv(self, command_kind: str, suffix: tuple[str, ...]) -> tuple[str, ...]:
        binary = self.config.ceph_binary if command_kind == "ceph" else self.config.rbd_binary
        return (
            str(binary),
            "--cluster",
            self.config.cluster_name,
            "--conf",
            str(self.config.conf_path),
            "--keyring",
            str(self.config.keyring_path),
            "--name",
            self.config.client_entity,
            *suffix,
        )

    def _invoke(self, argv: tuple[str, ...], action: str) -> str:
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                env=self._environment,
                close_fds=True,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise AgentError(
                "COMMAND_NOT_FOUND",
                "A required host-agent executable was not found",
                details={"action": action},
            ) from exc
        except OSError as exc:
            raise AgentError(
                "COMMAND_START_FAILED",
                "Could not start a host-agent command",
                retryable=True,
                details={"action": action},
            ) from exc

        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        total_bytes = 0
        total_lock = threading.Lock()
        output_limit_hit = threading.Event()
        reader_failed = threading.Event()

        def read_bounded(name: str, stream) -> None:
            nonlocal total_bytes
            try:
                while True:
                    chunk = stream.read(64 * 1024)
                    if not chunk:
                        return
                    with total_lock:
                        remaining = self.config.max_command_output_bytes - total_bytes
                        if remaining > 0:
                            buffers[name].extend(chunk[:remaining])
                            total_bytes += min(len(chunk), remaining)
                        if len(chunk) > remaining:
                            output_limit_hit.set()
                            try:
                                process.kill()
                            except OSError:
                                pass
                            return
            except Exception:
                reader_failed.set()
                try:
                    process.kill()
                except OSError:
                    pass
            finally:
                try:
                    stream.close()
                except OSError:
                    pass

        readers = [
            threading.Thread(target=read_bounded, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=read_bounded, args=("stderr", process.stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()
        try:
            returncode = process.wait(timeout=self.config.command_timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            try:
                process.kill()
            except OSError:
                pass
            process.wait()
            for reader in readers:
                reader.join(timeout=1)
            stderr = bytes(buffers["stderr"]).decode("utf-8", errors="replace")
            raise AgentError(
                "COMMAND_TIMEOUT",
                "Host-agent command timed out",
                retryable=True,
                details={"action": action, "stderr": self._safe_excerpt(stderr)},
            ) from exc
        for reader in readers:
            reader.join(timeout=1)

        if output_limit_hit.is_set():
            raise AgentError(
                "COMMAND_OUTPUT_LIMIT",
                "Host-agent command exceeded the configured output limit",
                details={
                    "action": action,
                    "output_bytes": self.config.max_command_output_bytes + 1,
                    "limit_bytes": self.config.max_command_output_bytes,
                },
            )
        if reader_failed.is_set() or any(reader.is_alive() for reader in readers):
            raise AgentError(
                "COMMAND_READ_FAILED",
                "Could not safely read host-agent command output",
                retryable=True,
                details={"action": action},
            )

        stdout_bytes = bytes(buffers["stdout"])
        stderr_bytes = bytes(buffers["stderr"])
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if returncode != 0:
            raise AgentError(
                "COMMAND_FAILED",
                "Host-agent command failed",
                retryable=True,
                details={
                    "action": action,
                    "exit_code": returncode,
                    "stderr": self._safe_excerpt(stderr),
                },
            )
        return stdout

    @staticmethod
    def _safe_excerpt(value: str, limit: int = 2048) -> str:
        return redact_text(value)[:limit]

    def _parse_json(self, stdout: str, action: str) -> Any:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AgentError(
                "INVALID_CEPH_OUTPUT",
                "Ceph inventory command did not return valid JSON",
                details={
                    "action": action,
                    "output": self._safe_excerpt(stdout),
                },
            ) from exc
        return redact_data(parsed)
