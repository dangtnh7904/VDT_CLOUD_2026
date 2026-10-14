from __future__ import annotations

from typing import Any

from ...services.executor_client import ExecutorClient, ExecutorClientError
from .domain import ClusterReadError


class ExecutorClusterObservationAdapter:
    """Read-only adapter over the existing authenticated closed executor protocol."""

    def __init__(self, client: ExecutorClient | None = None) -> None:
        self.client = client or ExecutorClient.from_settings()

    def identity(self) -> dict[str, Any]:
        try:
            result = self.client.ceph_fsid()
        except ExecutorClientError as exc:
            raise self._translate(exc) from exc
        return {
            "fsid": result.get("fsid"),
            "observed_at": result.get("collected_at"),
            "source": "ceph_cli_executor",
        }

    def capabilities(self) -> dict[str, Any]:
        try:
            return self.client.capabilities()
        except ExecutorClientError as exc:
            raise self._translate(exc) from exc

    def inventory(self) -> dict[str, Any]:
        try:
            capacity = self.client.ceph_capacity_inventory()
            versions = self.client.ceph_versions()
        except ExecutorClientError as exc:
            raise self._translate(exc) from exc
        return {
            "fsid": capacity.get("fsid"),
            "observed_at": capacity.get("collected_at"),
            "capacity": capacity.get("data"),
            "versions": versions.get("data"),
        }

    @staticmethod
    def _translate(exc: ExecutorClientError) -> ClusterReadError:
        code = exc.code
        if code == "FSID_MISMATCH":
            return ClusterReadError(
                "FSID_MISMATCH",
                "connected Ceph cluster does not match the configured FSID",
                observed_state=exc.details,
            )
        return ClusterReadError(
            code,
            exc.message,
            retryable=exc.retryable,
            observed_state=exc.details,
        )
