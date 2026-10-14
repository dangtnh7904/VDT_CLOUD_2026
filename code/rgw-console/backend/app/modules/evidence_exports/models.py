from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExportSource = Literal[
    "osd_collection", "osd_comparison", "osd_config_diff", "upgrade_run",
    "performance", "capacity", "cluster_collection",
]
ExportFormat = Literal["json", "csv", "zip", "md"]
ScopeType = Literal["cluster", "mon", "mgr", "host", "osd", "pool", "image", "job", "operation"]
OsdId = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
METRIC_UNITS = {
    **{f"iops.{key}": "operations/second" for key in ("read", "write", "total")},
    **{f"throughput_bps.{key}": "bytes/second" for key in ("read", "write", "total")},
    **{f"latency_ms.{key}": "milliseconds" for key in ("read_avg", "write_avg", "average", "p50", "p95", "p99")},
    **{f"counts.{key}": "operations/window" for key in ("success", "error")},
}


class ExportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    osd_ids: list[OsdId] | None = Field(default=None, min_length=1, max_length=128)
    resource_ids: list[Annotated[str, Field(min_length=1, max_length=255, pattern=r"^[^\x00-\x1f\x7f]+$")]] | None = Field(default=None, min_length=1, max_length=128)
    source: Literal["application", "ceph", "device"] | None = None
    scope_type: ScopeType | None = None
    scope: str | None = Field(default=None, min_length=1, max_length=255, pattern=r"^[^\x00-\x1f\x7f]+$")
    from_time: datetime | None = Field(default=None, alias="from")
    to_time: datetime | None = Field(default=None, alias="to")
    step: int | None = Field(default=None, strict=True, ge=10, le=3600)
    metric_ids: list[Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]] | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_selection(self):
        if self.osd_ids and len(set(self.osd_ids)) != len(self.osd_ids):
            raise ValueError("osd_ids must be unique")
        if self.resource_ids and len(set(self.resource_ids)) != len(self.resource_ids):
            raise ValueError("resource_ids must be unique")
        if self.metric_ids and len(set(self.metric_ids)) != len(self.metric_ids):
            raise ValueError("metric_ids must be unique")
        for value in (self.from_time, self.to_time):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("export timestamps must include a timezone")
        if self.from_time and self.to_time:
            if self.from_time >= self.to_time:
                raise ValueError("from must be earlier than to")
            if self.to_time - self.from_time > timedelta(hours=24):
                raise ValueError("synchronous metric export is limited to 24 hours")
        return self

    def window(self, now: datetime) -> tuple[datetime, datetime]:
        ended_at = self.to_time or now
        started_at = self.from_time or ended_at - timedelta(minutes=5)
        if started_at >= ended_at or ended_at - started_at > timedelta(hours=24):
            raise ValueError("metric export requires an increasing window of at most 24 hours")
        return started_at.astimezone(timezone.utc), ended_at.astimezone(timezone.utc)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: ExportSource
    source_id: UUID | None = None
    comparison_id: UUID | None = None
    format: ExportFormat = "json"
    filters: ExportFilters = Field(default_factory=ExportFilters)

    @model_validator(mode="after")
    def validate_source_contract(self):
        if self.source not in {"performance", "capacity"} and self.source_id is None:
            raise ValueError("this source requires a registered source_id")
        if self.source in {"performance", "capacity"} and self.source_id is not None:
            raise ValueError("metric queries do not accept source_id")
        comparison = self.source in {"osd_comparison", "osd_config_diff"}
        if comparison != (self.comparison_id is not None):
            raise ValueError("comparison_id is required only for OSD comparisons")
        if comparison and self.source_id == self.comparison_id:
            raise ValueError("before and after collection IDs must differ")
        present = self.filters.model_fields_set
        if self.source == "performance":
            allowed = {"source", "scope_type", "scope", "from_time", "to_time", "step", "metric_ids"}
            if self.filters.scope_type in {"mon", "mgr", "host"}:
                raise ValueError("this scope is not supported by performance history")
            if self.filters.metric_ids and any(metric not in METRIC_UNITS for metric in self.filters.metric_ids):
                raise ValueError("metric_ids must name registered performance metrics")
        elif self.source == "capacity":
            allowed = {"scope_type", "scope"}
            if bool(self.filters.scope_type) != bool(self.filters.scope):
                raise ValueError("capacity scope_type and scope must be supplied together")
            if self.filters.scope_type not in {None, "pool"}:
                raise ValueError("capacity exports support cluster or pool scope")
        elif self.source in {"osd_collection", "osd_comparison", "osd_config_diff"}:
            allowed = {"osd_ids"}
        elif self.source == "cluster_collection":
            allowed = {"resource_ids", "scope_type", "metric_ids"}
            if self.filters.resource_ids and not self.filters.scope_type:
                raise ValueError("resource_ids require a scope_type because IDs can overlap across resource types")
            if self.filters.scope_type in {"image", "job", "operation"}:
                raise ValueError("this scope is not supported by cluster collections")
        else:
            allowed = set()
        if present - allowed:
            raise ValueError("one or more filters are not supported by the selected source")
        return self
