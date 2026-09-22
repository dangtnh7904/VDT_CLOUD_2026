from __future__ import annotations

import logging
import os
import signal
import socket
import stat
import struct
import threading
from pathlib import Path
from types import FrameType
from typing import BinaryIO

try:
    import grp
except ImportError:  # pragma: no cover - exercised by import tests on Windows
    grp = None  # type: ignore[assignment]

from .ceph_cli import CephInventoryRunner
from .config import AgentConfig, AgentConfigError
from .errors import AgentError
from .protocol import decode_request, encode_error, encode_success


LOGGER = logging.getLogger("rgw-console-agent")


class UnixAgentServer:
    def __init__(self, config: AgentConfig, runner: CephInventoryRunner) -> None:
        self.config = config
        self.runner = runner
        self._listener: socket.socket | None = None
        self._socket_inode: int | None = None
        self._stopping = threading.Event()
        self._slots = threading.BoundedSemaphore(config.max_connections)
        self._threads: set[threading.Thread] = set()
        self._threads_lock = threading.Lock()

    def serve_forever(self) -> None:
        listener = self._prepare_listener()
        self._listener = listener
        LOGGER.info("read-only agent listening on %s", self.config.socket_path)
        try:
            while not self._stopping.is_set():
                try:
                    connection, _ = listener.accept()
                except OSError:
                    if self._stopping.is_set():
                        break
                    raise

                if not self._slots.acquire(blocking=False):
                    self._send_best_effort_error(
                        connection,
                        AgentError(
                            "SERVER_BUSY",
                            "The agent has reached its connection limit",
                            retryable=True,
                        ),
                    )
                    connection.close()
                    continue

                thread = threading.Thread(
                    target=self._serve_connection,
                    args=(connection,),
                    name="ceph-agent-client",
                    daemon=True,
                )
                with self._threads_lock:
                    self._threads.add(thread)
                thread.start()
        finally:
            self.stop()
            self._wait_for_connections()
            self._remove_owned_socket()

    def stop(self) -> None:
        self._stopping.set()
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass

    def _prepare_listener(self) -> socket.socket:
        unix_family = getattr(socket, "AF_UNIX", None)
        if unix_family is None:
            raise RuntimeError("ceph-host-agent requires Unix domain socket support")

        socket_path = self.config.socket_path
        parent = socket_path.parent
        parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        parent_stat = parent.lstat()
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise RuntimeError("agent socket parent must be a real directory")
        if parent_stat.st_mode & stat.S_IWOTH:
            raise RuntimeError("agent socket parent must not be world-writable")

        try:
            existing = socket_path.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if not stat.S_ISSOCK(existing.st_mode):
                raise RuntimeError("refusing to replace a non-socket agent path")
            if hasattr(os, "geteuid") and existing.st_uid != os.geteuid():
                raise RuntimeError("refusing to replace an agent socket owned by another UID")
            socket_path.unlink()

        listener = socket.socket(unix_family, socket.SOCK_STREAM)
        previous_umask = os.umask(0o077)
        try:
            listener.bind(str(socket_path))
        finally:
            os.umask(previous_umask)

        try:
            os.chmod(socket_path, self.config.socket_mode)
            if self.config.socket_group:
                if grp is None:
                    raise RuntimeError("socket group lookup is unavailable on this platform")
                group = grp.getgrnam(self.config.socket_group)
                os.chown(socket_path, -1, group.gr_gid)
            self._socket_inode = socket_path.lstat().st_ino
            listener.listen(self.config.max_connections)
        except Exception:
            listener.close()
            self._remove_owned_socket(unchecked=True)
            raise
        return listener

    def _serve_connection(self, connection: socket.socket) -> None:
        try:
            connection.settimeout(self.config.client_timeout_seconds)
            self._authorize_peer(connection)
            with connection, connection.makefile("rb") as stream:
                self._serve_lines(connection, stream)
        except AgentError as exc:
            self._send_best_effort_error(connection, exc)
        except (BrokenPipeError, ConnectionError, TimeoutError, socket.timeout, OSError):
            pass
        finally:
            try:
                connection.close()
            except OSError:
                pass
            with self._threads_lock:
                self._threads.discard(threading.current_thread())
            self._slots.release()

    def _serve_lines(self, connection: socket.socket, stream: BinaryIO) -> None:
        while not self._stopping.is_set():
            raw = stream.readline(self.config.max_request_bytes + 1)
            if not raw:
                return
            if len(raw) > self.config.max_request_bytes:
                self._send(
                    connection,
                    encode_error(
                        None,
                        AgentError(
                            "REQUEST_TOO_LARGE",
                            "Request exceeded the configured size limit",
                        ),
                    ),
                )
                return
            if not raw.endswith(b"\n"):
                self._send(
                    connection,
                    encode_error(
                        None,
                        AgentError("INVALID_REQUEST", "Request must end with a newline"),
                    ),
                )
                return

            request_id: str | None = None
            try:
                request = decode_request(raw[:-1], self.runner.allowed_actions)
                request_id = request.request_id
                LOGGER.info("request_id=%s action=%s", request_id, request.action)
                result = self.runner.dispatch(request.action, request.params)
                response = encode_success(request_id, result)
                if len(response) > self.config.max_response_bytes:
                    raise AgentError(
                        "RESPONSE_TOO_LARGE",
                        "Response exceeded the configured size limit",
                    )
            except AgentError as exc:
                response = encode_error(request_id, exc)
            except Exception:
                LOGGER.exception("unexpected agent failure request_id=%s", request_id)
                response = encode_error(
                    request_id,
                    AgentError(
                        "INTERNAL_ERROR",
                        "The agent could not complete the request",
                        retryable=True,
                    ),
                )
            self._send(connection, response)

    def _authorize_peer(self, connection: socket.socket) -> None:
        peer_option = getattr(socket, "SO_PEERCRED", None)
        if peer_option is None:
            raise AgentError(
                "PEER_AUTH_UNAVAILABLE",
                "The platform cannot authenticate Unix socket peers",
            )
        try:
            raw = connection.getsockopt(
                socket.SOL_SOCKET,
                peer_option,
                struct.calcsize("3i"),
            )
            pid, uid, gid = struct.unpack("3i", raw)
        except (OSError, struct.error) as exc:
            raise AgentError(
                "PEER_AUTH_FAILED",
                "Could not authenticate the Unix socket peer",
            ) from exc
        if uid not in self.config.allowed_uids:
            LOGGER.warning("rejected peer pid=%s uid=%s gid=%s", pid, uid, gid)
            raise AgentError("PERMISSION_DENIED", "Unix socket peer is not allowed")

    @staticmethod
    def _send(connection: socket.socket, payload: bytes) -> None:
        connection.sendall(payload)

    @staticmethod
    def _send_best_effort_error(connection: socket.socket, error: AgentError) -> None:
        try:
            connection.sendall(encode_error(None, error))
        except OSError:
            pass

    def _wait_for_connections(self) -> None:
        deadline = self.config.command_timeout_seconds + 1
        with self._threads_lock:
            threads = tuple(self._threads)
        for thread in threads:
            thread.join(timeout=deadline)

    def _remove_owned_socket(self, unchecked: bool = False) -> None:
        path = self.config.socket_path
        try:
            current = path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(current.st_mode):
            return
        if unchecked or self._socket_inode is None or current.st_ino == self._socket_inode:
            path.unlink(missing_ok=True)


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("CEPH_AGENT_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> int:
    _configure_logging()
    try:
        config = AgentConfig.from_env()
    except AgentConfigError as exc:
        LOGGER.error("invalid configuration: %s", exc)
        return 2

    runner = CephInventoryRunner(config)
    server = UnixAgentServer(config, runner)

    def stop_handler(_signum: int, _frame: FrameType | None) -> None:
        server.stop()

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    try:
        server.serve_forever()
    except Exception:
        LOGGER.exception("agent terminated unexpectedly")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
