from __future__ import annotations

from typing import Any
from uuid import UUID

from ..modules.osd_info_collector.repository import PostgresOsdInfoRepository


class PostgresOsdInventoryQueryAdapter:
    """Composition adapter; upgrade_common never reads collector-owned tables."""

    def __init__(self, repository: PostgresOsdInfoRepository | None = None) -> None:
        self.repository = repository or PostgresOsdInfoRepository()

    def get_collection(self, collection_id: UUID) -> dict[str, Any]:
        return self.repository.get(collection_id)
