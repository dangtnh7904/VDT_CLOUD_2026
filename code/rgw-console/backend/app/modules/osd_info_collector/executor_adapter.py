from __future__ import annotations

from typing import Any

from ...services.executor_client import ExecutorClient, ExecutorClientError
from .domain import OsdInfoError


class ExecutorOsdInfoAdapter:
    """Runs only the closed, read-only collector action exposed by the executor."""

    def __init__(self, client: ExecutorClient | None = None) -> None:
        self.client = client or ExecutorClient.from_settings()

    def collect(self, osd_ids: tuple[int, ...]) -> dict[str, Any]:
        try:
            return self.client.ceph_osd_info_collect(list(osd_ids))
        except ExecutorClientError as exc:
            raise OsdInfoError(
                exc.code,
                exc.message,
                retryable=exc.retryable,
                observed_state=exc.details,
            ) from exc
