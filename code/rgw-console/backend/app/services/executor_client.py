from __future__ import annotations

import math
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import UUID, uuid4

import httpx


PROTOCOL_VERSION = 1
READ_ONLY_ACTIONS = frozenset(
    {
        "health", "capabilities", "ceph.status", "ceph.fsid", "ceph.versions",
        "ceph.osd_df", "ceph.osd_tree", "ceph.pool_ls_detail", "ceph.capacity_inventory",
        "ceph.crush_rule_dump", "rbd.pool.list", "rbd.image.list",
        "rbd.image.info", "rbd.device.list",
    }
)
MUTATION_ACTIONS = frozenset(
    {
        "rbd.image.create", "rbd.image.map", "rbd.device.format_ext4",
        "rbd.device.mount", "rbd.device.unmount", "rbd.device.unmap",
        "rbd.image.remove",
    }
)
FILE_ACTIONS = frozenset(
    {
        "rbd.files.list", "rbd.files.stat", "rbd.files.mkdir",
        "rbd.files.delete", "rbd.files.manifest",
    }
)
SESSION_ACTIONS = frozenset({"rbd.terminal.ticket.create"})
ALLOWED_ACTIONS = READ_ONLY_ACTIONS | MUTATION_ACTIONS | FILE_ACTIONS | SESSION_ACTIONS


class ExecutorClientError(RuntimeError):
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


class ExecutorClient:
    """Bounded, authenticated HTTP client for the internal Node SSH executor."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str,
        expected_fsid: str,
        timeout_seconds: float = 35,
        max_response_bytes: int = 5 * 1024 * 1024,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("RBD_EXECUTOR_URL must be an HTTP(S) URL without embedded credentials")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("RBD_EXECUTOR_URL must not include a path, query, or fragment")
        if len(token) < 32:
            raise ValueError("RBD_EXECUTOR_TOKEN must contain at least 32 characters")
        try:
            self.expected_fsid = str(UUID(expected_fsid))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("CEPH_EXPECTED_FSID must be a UUID") from exc
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("executor timeout must be greater than zero")
        if max_response_bytes <= 0:
            raise ValueError("executor response limit must be greater than zero")
        self.endpoint = urljoin(base_url.rstrip("/") + "/", "internal/v1/execute")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.transport = transport

    @classmethod
    def from_settings(cls) -> "ExecutorClient":
        from ..config import get_settings

        settings = get_settings()
        if not settings.ceph_expected_fsid:
            raise ValueError("CEPH_EXPECTED_FSID is required for executor calls")
        token = settings.rbd_executor_token.get_secret_value() if settings.rbd_executor_token else ""
        return cls(
            settings.rbd_executor_url,
            token=token,
            expected_fsid=settings.ceph_expected_fsid,
            timeout_seconds=settings.rbd_executor_timeout_seconds,
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

    def ceph_capacity_inventory(self) -> dict[str, Any]:
        return self.request("ceph.capacity_inventory")

    def rbd_pool_list(self) -> dict[str, Any]:
        return self._rbd_data(self.request("rbd.pool.list"), "rbd.pool.list")

    def rbd_image_list(self, *, pool: str, namespace: str = "") -> dict[str, Any]:
        return self._rbd_data(
            self.request("rbd.image.list", {"pool": pool, "namespace": namespace}),
            "rbd.image.list",
        )

    def rbd_image_info(self, *, pool: str, image_name: str, namespace: str = "") -> dict[str, Any]:
        return self._rbd_data(
            self.request(
                "rbd.image.info",
                {"pool": pool, "namespace": namespace, "image_name": image_name},
            ),
            "rbd.image.info",
        )

    def rbd_device_list(self) -> dict[str, Any]:
        return self._rbd_data(self.request("rbd.device.list"), "rbd.device.list")

    def rbd_file_action(
        self,
        action: str,
        params: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if action not in FILE_ACTIONS:
            raise ExecutorClientError("ACTION_NOT_ALLOWED", "The requested file action is not allowlisted")
        return self._rbd_data(
            self.request(action, params, timeout_seconds=timeout_seconds),
            action,
        )

    def terminal_ticket(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._rbd_data(
            self.request("rbd.terminal.ticket.create", params),
            "rbd.terminal.ticket.create",
        )

    def mutate(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action not in MUTATION_ACTIONS:
            raise ExecutorClientError("ACTION_NOT_ALLOWED", "The requested executor mutation is not allowlisted")
        try:
            UUID(str(params.get("volume_id")))
            UUID(str(params.get("action_id")))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("mutation volume_id and action_id must be UUIDs") from exc
        fence_token = params.get("fence_token")
        if isinstance(fence_token, bool) or not isinstance(fence_token, int) or fence_token < 1:
            raise ValueError("mutation fence_token must be a positive integer")
        return self._rbd_data(self.request(action, params), action)

    @staticmethod
    def _rbd_data(result: dict[str, Any], action: str) -> dict[str, Any]:
        if result.get("action") != action or not isinstance(result.get("data"), dict):
            raise ExecutorClientError(
                "EXECUTOR_PROTOCOL_ERROR",
                "Executor result did not contain the expected action payload",
            )
        payload = dict(result["data"])
        payload.setdefault("fsid", result.get("fsid"))
        if "collected_at" in result:
            payload.setdefault("collected_at", result["collected_at"])
        return payload

    def request(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if action not in ALLOWED_ACTIONS:
            raise ExecutorClientError("ACTION_NOT_ALLOWED", "The requested executor action is not allowlisted")
        params = {} if params is None else params
        if not isinstance(params, dict):
            raise TypeError("executor params must be a JSON object")
        try:
            normalized_request_id = str(UUID(request_id)) if request_id else str(uuid4())
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        payload = {
            "version": PROTOCOL_VERSION,
            "request_id": normalized_request_id,
            "action": action,
            "params": params,
        }
        request_timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        if not math.isfinite(request_timeout) or request_timeout <= 0:
            raise ValueError("executor request timeout must be greater than zero")
        try:
            with httpx.Client(
                timeout=request_timeout,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    self.endpoint,
                    json=payload,
                    headers={"X-Executor-Token": self.token},
                )
        except httpx.TimeoutException as exc:
            raise ExecutorClientError(
                "EXECUTOR_TIMEOUT", "Timed out while waiting for the SSH executor", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ExecutorClientError(
                "EXECUTOR_UNAVAILABLE", "Could not connect to the SSH executor", retryable=True
            ) from exc
        if len(response.content) > self.max_response_bytes:
            raise ExecutorClientError("EXECUTOR_RESPONSE_TOO_LARGE", "Executor response exceeded the configured size limit")
        try:
            decoded = response.json()
        except ValueError as exc:
            raise ExecutorClientError("EXECUTOR_PROTOCOL_ERROR", "Executor returned invalid JSON") from exc
        envelope = self._decode_response(decoded, normalized_request_id)
        if not envelope["ok"]:
            error = envelope["error"]
            raise ExecutorClientError(
                error["code"], error["message"],
                retryable=bool(error.get("retryable")), details=error.get("details"),
            )
        result = envelope["result"]
        self._assert_fsid(result)
        return result

    @staticmethod
    def _decode_response(response: Any, request_id: str) -> dict[str, Any]:
        if not isinstance(response, dict) or response.get("version") != PROTOCOL_VERSION:
            raise ExecutorClientError("EXECUTOR_PROTOCOL_ERROR", "Executor returned an unsupported response")
        if response.get("request_id") not in {None, request_id} or not isinstance(response.get("ok"), bool):
            raise ExecutorClientError("EXECUTOR_PROTOCOL_ERROR", "Executor response binding is invalid")
        if response["ok"]:
            if response.get("request_id") != request_id or not isinstance(response.get("result"), dict):
                raise ExecutorClientError("EXECUTOR_PROTOCOL_ERROR", "Successful executor response is incomplete")
        else:
            error = response.get("error")
            if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
                raise ExecutorClientError("EXECUTOR_PROTOCOL_ERROR", "Executor error response is incomplete")
        return response

    def _assert_fsid(self, result: dict[str, Any]) -> None:
        try:
            observed = str(UUID(result.get("fsid")))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ExecutorClientError("EXECUTOR_PROTOCOL_ERROR", "Executor result is missing a valid FSID") from exc
        if observed != self.expected_fsid:
            raise ExecutorClientError(
                "FSID_MISMATCH", "Executor result came from an unexpected Ceph cluster",
                details={"expected_fsid": self.expected_fsid, "observed_fsid": observed},
            )
