from __future__ import annotations

from typing import Any, Protocol


class ClusterObservationPort(Protocol):
    def identity(self) -> dict[str, Any]: ...

    def capabilities(self) -> dict[str, Any]: ...

    def inventory(self) -> dict[str, Any]: ...
