from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class OsdInventoryQueryPort(Protocol):
    """Read-only query boundary for immutable OSD Info collections."""

    def get_collection(self, collection_id: UUID) -> dict[str, Any]: ...
