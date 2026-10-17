from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from ...config import Settings
from ...platform.config import resolve_settings
from ...platform.evidence import FilesystemArtifactStore
from .models import ExportRequest, METRIC_UNITS
from .rendering import (
    ExportDownload, ExportError, MAX_BYTES, MAX_ROWS, REDACTION_VERSION,
    json_bytes, render_export, safe_projection,
)
from .repository import ExportSourceRepository


logger = logging.getLogger(__name__)


@dataclass
class SourceSnapshot:
    data: dict
    tables: dict[str, list[dict]]
    raw: dict[str, Any] = field(default_factory=dict)
    source_refs: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class EvidenceExportService:
    def __init__(
        self, settings: Settings, *, repository=None,
        source_loader: Callable[[ExportRequest, datetime], SourceSnapshot] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.settings = resolve_settings(settings)
        self.repository = repository or ExportSourceRepository()
        self.source_loader = source_loader or self._load_source
        self.now = now or (lambda: datetime.now(timezone.utc))

    def create(self, request: ExportRequest, *, actor: str | None = None) -> ExportDownload:
        exported_at = self.now()
        export_id = str(uuid4())
        try:
            snapshot = self.source_loader(request, exported_at)
            data = safe_projection(snapshot.data)
            tables = safe_projection(snapshot.tables)
            raw = safe_projection(snapshot.raw)
            # Formats may duplicate source information; bound the complete input
            # as well as each final representation, never trust a ZIP's size.
            if sum(len(json_bytes(value)) for value in (data, raw)) > MAX_BYTES:
                raise ExportError("EXPORT_LIMIT_EXCEEDED", "Evidence exceeds the 16 MiB synchronous export budget", 413)
            manifest = safe_projection({
                "schema_version": 1, "export_id": export_id,
                "app_version": os.environ.get("APP_VERSION", "3.0.0"),
                "redaction_version": REDACTION_VERSION,
                "source": request.source, "source_id": str(request.source_id) if request.source_id else None,
                "comparison_id": str(request.comparison_id) if request.comparison_id else None,
                "actor": actor or self.settings.console_auth_username or "local-operator",
                "exported_at": exported_at.isoformat(),
                "cluster_id": self.settings.cluster_id or None,
                "fsid": self.settings.ceph_expected_fsid,
                "requested_scope": request.filters.model_dump(mode="json", by_alias=True, exclude_none=True),
                "source_refs": snapshot.source_refs,
                "download_hash_location": "X-Export-Sha256 response header; checksum applies to exact downloaded bytes",
                "null_semantics": "Unavailable values remain JSON null; CSV lists null columns in _null_fields",
                "cluster_mutations_executed": False,
                "collection_triggered": False,
                "limits": {"bytes": MAX_BYTES, "rows": MAX_ROWS, "mode": "SYNCHRONOUS"},
                "limitations": [
                    "Only implemented, authorized sources are included; this copy is not live acceptance evidence",
                    "No asynchronous export cache or cross-cluster restore is implemented",
                ],
                **snapshot.metadata,
            })
            download = render_export(data=data, tables=tables, raw=raw, manifest=manifest, format=request.format)
        except Exception as exc:
            code = getattr(exc, "code", "EXPORT_SOURCE_UNAVAILABLE")
            logger.info("evidence_export %s", __import__("json").dumps({
                "export_id": export_id, "source": request.source, "source_id": str(request.source_id) if request.source_id else None,
                "cluster_id": self.settings.cluster_id, "outcome": "REJECTED", "code": re.sub(r"[^A-Z0-9_]", "", str(code))[:80],
            }, ensure_ascii=False))
            raise
        logger.info("evidence_export %s", __import__("json").dumps({
            "export_id": export_id, "source": request.source, "source_id": str(request.source_id) if request.source_id else None,
            "cluster_id": self.settings.cluster_id, "actor": manifest["actor"], "requested_scope": manifest["requested_scope"],
            "source_hashes": [ref.get("sha256") for ref in snapshot.source_refs],
            "outcome": "DOWNLOAD_RESPONSE_READY", "quality": manifest.get("quality"),
            "download_sha256": download.sha256, "size_bytes": len(download.content),
        }, ensure_ascii=False))
        return download

    def _assert_cluster(self, source: dict) -> None:
        if (
            not self.settings.cluster_id or not self.settings.ceph_expected_fsid
            or source.get("cluster_id") != self.settings.cluster_id
            or str(source.get("fsid")) != str(self.settings.ceph_expected_fsid)
        ):
            raise ExportError("EXPORT_SCOPE_REJECTED", "Saved evidence is outside the current cluster profile", 403)

    def _allowed_osds(self) -> set[int]:
        result = set()
        for value in self.settings.upgrade_allowed_osd_set:
            normalized = value.removeprefix("osd.")
            if not normalized.isdigit():
                raise ExportError("EXPORT_SCOPE_REJECTED", "OSD inventory allowlist is invalid", 403)
            result.add(int(normalized))
        return result

    def _assert_osds(self, osds: list[int]) -> None:
        if set(osds) - self._allowed_osds():
            raise ExportError("EXPORT_SCOPE_REJECTED", "Selected evidence includes OSDs outside the configured allowlist", 403)

    def _selected_osds(self, collection: dict, requested: list[int] | None) -> list[int]:
        available = list(collection.get("requested_osd_ids") or [])
        selected = requested or available
        if set(selected) - set(available):
            raise ExportError("EXPORT_SCOPE_REJECTED", "Selected OSDs are not part of this collection", 403)
        self._assert_osds(selected)
        return sorted(selected)

    @staticmethod
    def _filter_osd_collection(collection: dict, raw: dict, selected: list[int]) -> tuple[dict, dict]:
        collection = {
            **collection, "requested_osd_ids": selected,
            "osds": [row for row in collection.get("osds", []) if row.get("osd_id") in selected],
            "osd_count": len(selected),
        }
        raw = {
            **raw, "osds": [row for row in raw.get("osds", []) if (row.get("identity") or {}).get("osd_id") in selected],
            "osd_count": len(selected),
        }
        return collection, raw

    def _osd_source(self, collection_id: UUID, selected: list[int] | None) -> tuple[dict, dict, list[dict]]:
        from ..osd_info_collector.repository import PostgresOsdInfoRepository
        from ..osd_info_collector.service import OsdInfoService

        service = OsdInfoService(self.settings, PostgresOsdInfoRepository(), None)
        collection = service.get(collection_id)
        self._assert_cluster(collection)
        selected = self._selected_osds(collection, selected)
        if collection.get("state") != "COMPLETE":
            return self._filter_osd_collection(collection, {}, selected)[0], {}, []
        artifact = self.repository.artifact(UUID(str(collection["evidence_artifact_id"])))
        self._assert_cluster(artifact)
        if artifact["sha256"] != collection.get("artifact_sha256"):
            raise ExportError("EXPORT_SOURCE_INVALID", "Collection artifact registry hashes disagree")
        if artifact["size_bytes"] > MAX_BYTES:
            raise ExportError("EXPORT_LIMIT_EXCEEDED", "Collection artifact exceeds the synchronous export limit", 413)
        # Reuse the collector's containment, hash, schema and metadata verifier;
        # no filesystem path supplied by the client reaches the artifact store.
        raw = service._load_verified_artifact(collection_id, collection)
        collection, raw = self._filter_osd_collection(collection, raw, selected)
        return collection, raw, [self._artifact_ref(artifact)]

    @staticmethod
    def _artifact_ref(artifact: dict) -> dict:
        return {
            "artifact_id": str(artifact["id"]), "sha256": artifact["sha256"],
            "size_bytes": artifact["size_bytes"], "mime_type": artifact.get("mime_type"),
            "producer": artifact.get("producer"), "observed_at": artifact.get("observed_at"),
            "verified": True,
        }

    def _registered_raw(self, artifacts: list[dict]) -> tuple[dict, list[dict]]:
        raw = {}
        refs = []
        total_bytes = 0
        store = FilesystemArtifactStore(self.settings.evidence_root, max_artifact_bytes=min(MAX_BYTES, self.settings.evidence_max_artifact_bytes))
        for artifact in artifacts:
            self._assert_cluster(artifact)
            if artifact.get("access_policy") != "operator":
                raise ExportError("EXPORT_SCOPE_REJECTED", "Evidence is not available to the console operator", 403)
            total_bytes += artifact["size_bytes"]
            if total_bytes > MAX_BYTES:
                raise ExportError("EXPORT_LIMIT_EXCEEDED", "Registered artifacts exceed the synchronous export limit", 413)
            if artifact["mime_type"] != "application/json":
                raise ExportError("EXPORT_SOURCE_INVALID", "Only registered JSON evidence can be exported in this release")
            try:
                value = store.read_json(artifact["uri"], expected_sha256=artifact["sha256"], expected_size_bytes=artifact["size_bytes"])
            except (OSError, ValueError, TypeError) as exc:
                raise ExportError("EXPORT_SOURCE_INVALID", "Registered evidence failed containment or integrity verification") from exc
            raw[str(artifact["id"])] = value
            refs.append(self._artifact_ref(artifact))
        return raw, refs

    def _load_source(self, request: ExportRequest, now: datetime) -> SourceSnapshot:
        if request.source == "osd_collection":
            collection, raw, refs = self._osd_source(request.source_id, request.filters.osd_ids)
            return SourceSnapshot(
                {"collection": collection, "evidence": raw or None}, {"osds": collection.get("osds", [])},
                {"collection": raw} if raw else {}, refs,
                {"quality": collection.get("quality") or collection.get("state"),
                 "resolved_scope": {"osd_ids": collection["requested_osd_ids"]},
                 "observed_at": collection.get("collected_at"), "collector_version": collection.get("collector_version"),
                 "source_components": {"inventory": "AVAILABLE", "verified_raw": "AVAILABLE" if refs else "MISSING"}},
            )
        if request.source in {"osd_comparison", "osd_config_diff"}:
            from ..osd_info_collector.comparison import compare_collections
            from ..osd_info_collector.evidence_comparison import compare_config_evidence

            before, before_raw, before_refs = self._osd_source(request.source_id, request.filters.osd_ids)
            after, after_raw, after_refs = self._osd_source(request.comparison_id, request.filters.osd_ids)
            data = compare_config_evidence(before, after, before_raw, after_raw) if request.source == "osd_config_diff" else compare_collections(before, after)
            tables = {"config_changes": data.get("osds", [])} if request.source == "osd_config_diff" else {"changes": data.get("changes", [])}
            if not any(tables.values()):
                tables = {"comparison_summary": [{"comparison_status": data["comparison_status"], "reasons": data["reasons"]}]}
            return SourceSnapshot(data, tables, {"before": before_raw, "after": after_raw}, before_refs + after_refs, {
                "quality": data["comparison_status"], "reasons": data["reasons"],
                "resolved_scope": {"before_osd_ids": before["requested_osd_ids"], "after_osd_ids": after["requested_osd_ids"]},
                "observed_at": {"before": before.get("collected_at"), "after": after.get("collected_at")},
            })
        if request.source == "upgrade_run":
            return self._upgrade_run(request)
        if request.source == "cluster_collection":
            return self._cluster_collection(request)
        if request.source == "performance":
            return self._performance(request, now)
        if request.source == "capacity":
            from ...api.capacity import capacity_snapshot

            data = capacity_snapshot(scope_type=request.filters.scope_type, scope=request.filters.scope)
            if data.get("fsid") is not None:
                self._assert_cluster({"cluster_id": self.settings.cluster_id, "fsid": data["fsid"]})
            return SourceSnapshot(data, {"capacity": [data]}, metadata={
                "quality": "VALID" if data.get("fresh") else data.get("state", "MISSING"),
                "reasons": data.get("reasons", []), "freshness": data.get("telemetry"),
                "observed_at": data.get("captured_at"),
                "resolved_scope": {"scope_type": request.filters.scope_type or "cluster", "scope": request.filters.scope},
                "unit_schema": "capacity-bytes-ratio-v1",
            })
        raise ExportError("EXPORT_SOURCE_UNSUPPORTED", "Selected export source is unsupported")

    def _upgrade_run(self, request: ExportRequest) -> SourceSnapshot:
        from ...adapters.osd_inventory_query import PostgresOsdInventoryQueryAdapter
        from ..upgrade_common.repository import PostgresUpgradeRepository
        from ..upgrade_common.service import UpgradeApplicationService

        repository = PostgresUpgradeRepository()
        run = repository.get_run_context(request.source_id)
        self._assert_cluster(run)
        self._assert_osds(list(run.get("source_osds", [])) + list(run.get("destination_osds", [])))
        binding = repository.get_inventory_binding(run_id=request.source_id, plan_revision=run["plan_revision"])
        raw, refs = self._registered_raw(self.repository.run_artifacts(request.source_id))
        readiness = {"result": "UNAVAILABLE", "reasons": ["CURRENT_READINESS_NOT_REQUESTED_FOR_HISTORICAL_RUN"]}
        if self.settings.feature_upgrade:
            try:
                readiness = UpgradeApplicationService(self.settings, repository, inventory_query=PostgresOsdInventoryQueryAdapter()).inventory_readiness(request.source_id)
            except Exception as exc:
                # A changed current config must not rewrite historical evidence
                # or prevent downloading the persisted plan. Never include an
                # exception's raw text, URI or server credentials in the report.
                readiness = {"result": "UNAVAILABLE", "reasons": ["CURRENT_READINESS_REQUIRES_MATCHING_PROFILE"], "error_code": re.sub(r"[^A-Z0-9_]", "", str(getattr(exc, "code", "READINESS_QUERY_FAILED")))[:80]}
        plan = run.get("dry_run_plan")
        data = {"run": run, "saved_inventory_binding": binding, "current_readiness": readiness}
        return SourceSnapshot(data, {
            "run": [run], "plan_steps": plan.get("steps", []) if isinstance(plan, dict) else [],
            "inventory_binding": [binding] if binding else [], "readiness": [readiness],
        }, raw, refs, {
            "quality": "AVAILABLE" if plan else "INCOMPLETE", "plan_revision": run["plan_revision"],
            "plan_hash": run.get("plan_hash"), "config_hash": run.get("config_hash"),
            "resolved_scope": {"source_osds": run.get("source_osds", []), "destination_osds": run.get("destination_osds", [])},
            "source_components": {"saved_plan": "AVAILABLE" if plan else "MISSING", "inventory_binding": "AVAILABLE" if binding else "MISSING", "run_artifacts": "AVAILABLE" if refs else "MISSING", "live_execution_evidence": "NOT_REQUESTED"},
        })

    def _cluster_collection(self, request: ExportRequest) -> SourceSnapshot:
        from ..cluster_metrics.api import _service

        data = _service().get(request.source_id)
        self._assert_cluster(data)
        resources = data.get("resources", [])
        metrics = data.get("metrics", [])
        if request.filters.resource_ids:
            if set(request.filters.resource_ids) - {str(row["id"]) for row in resources}:
                raise ExportError("EXPORT_SCOPE_REJECTED", "Selected resource IDs are not part of this collection", 403)
            resources = [row for row in resources if str(row["id"]) in request.filters.resource_ids]
        if request.filters.scope_type:
            resources = [row for row in resources if row.get("scope_type") == request.filters.scope_type]
        selected_ids = {str(row["id"]) for row in resources}
        selected_resources = {(row.get("scope_type"), str(row["id"])) for row in resources}
        if request.filters.metric_ids and set(request.filters.metric_ids) - {str(row["metric_id"]) for row in metrics}:
            raise ExportError("EXPORT_SCOPE_REJECTED", "Selected metric IDs are not part of this collection", 403)
        metrics = [row for row in metrics if (row.get("scope_type"), str(row.get("resource_id"))) in selected_resources]
        if request.filters.metric_ids:
            metrics = [row for row in metrics if row["metric_id"] in request.filters.metric_ids]
        data = {**data, "resources": resources, "metrics": metrics}
        artifact = data.get("artifact") or {}
        refs = [{"artifact_id": str(artifact["id"]), "sha256": artifact.get("sha256"), "size_bytes": artifact.get("size_bytes"), "verified": True}] if artifact.get("verified") else []
        return SourceSnapshot(data, {"metrics": metrics} if request.filters.metric_ids else {"resources": resources}, source_refs=refs, metadata={
            "quality": data.get("quality", "UNKNOWN"), "freshness": data.get("freshness"),
            "observed_at": data.get("observed_at"), "collector_version": data.get("collector_version"),
            "resolved_scope": {"resource_ids": sorted(selected_ids), "metric_ids": sorted({str(row["metric_id"]) for row in metrics})},
            "reasons": ["NO_MATCHING_RESOURCES"] if not resources else [],
        })

    def _performance(self, request: ExportRequest, now: datetime) -> SourceSnapshot:
        from ...services.performance import history_samples, latest_sample, scope_supported, unavailable_payload

        filters = request.filters
        source = filters.source or "application"
        scope_type = filters.scope_type or "cluster"
        scope = filters.scope or ("console" if source == "application" and scope_type == "cluster" else self.settings.ceph_expected_fsid if source == "ceph" and scope_type == "cluster" else "all")
        scope = scope or "unconfigured"
        if scope_type == "osd":
            if not scope.isdigit():
                raise ExportError("EXPORT_SCOPE_REJECTED", "OSD metric scope must be numeric", 403)
            self._assert_osds([int(scope)])
        if scope_type == "pool" and scope not in self.settings.rbd_allowed_pool_set | self.settings.rgw_affected_pool_set:
            raise ExportError("EXPORT_SCOPE_REJECTED", "Pool metric scope is outside the configured allowlists", 403)
        if scope_type == "cluster" and source in {"application", "ceph"} and scope != ("console" if source == "application" else self.settings.ceph_expected_fsid):
            if not (source == "ceph" and not self.settings.ceph_expected_fsid and scope == "unconfigured"):
                raise ExportError("EXPORT_SCOPE_REJECTED", "Cluster metric scope does not match the current profile", 403)
        reason = "PERFORMANCE_DISABLED" if not self.settings.performance_enabled else "UNSUPPORTED_SCOPE" if not scope_supported(source, scope_type) else "NOT_CONFIGURED" if source == "ceph" and not self.settings.ceph_expected_fsid else None
        history = filters.from_time is not None or filters.to_time is not None
        metadata = {"query_revision": "performance-export-v1", "unit_schema": METRIC_UNITS, "resolved_scope": {"source": source, "scope_type": scope_type, "scope": scope}}
        if history:
            try:
                started_at, ended_at = filters.window(now)
            except ValueError as exc:
                raise ExportError("EXPORT_INVALID_REQUEST", str(exc), 422) from exc
            step = filters.step or 15
            sample_kind = "rollup_1m" if step >= 60 or ended_at - started_at > timedelta(hours=self.settings.performance_raw_retention_hours) else "raw"
            if reason:
                items = []
            else:
                self.repository.assert_performance_query_bounded(fsid=self.settings.ceph_expected_fsid or "application", source=source, scope_type=scope_type, scope=scope, sample_kind=sample_kind, started_at=started_at, ended_at=ended_at)
                sample_kind, items = history_samples(source, scope_type, scope, started_at=started_at, ended_at=ended_at, step_seconds=step)
            data = {"source": source, "scope_type": scope_type, "scope": scope, "from": started_at.isoformat(), "to": ended_at.isoformat(), "step_seconds": step, "sample_kind": sample_kind, "state": "UNAVAILABLE" if reason else "OK" if items else "MISSING", "reasons": [reason] if reason else [] if items else ["NO_SAMPLES_IN_WINDOW"], "items": items}
            metadata.update(window={"from": data["from"], "to": data["to"], "step_seconds": step, "timezone": "UTC"}, aggregation_semantics="latest persisted sample in each requested time bucket; no interpolation", freshness={"mode": "HISTORICAL_WINDOW", "current_freshness_enforced": False})
        else:
            data = unavailable_payload(source, scope_type, scope, reason) if reason else latest_sample(source, scope_type, scope)
            items = [data] if data.get("captured_at") is not None else []
            metadata.update(observed_at=data.get("captured_at"), freshness={"fresh": data.get("fresh"), "age_seconds": data.get("age_seconds")})
        if filters.metric_ids:
            selected = set(filters.metric_ids)
            items = [{key: {metric: value for metric, value in child.items() if f"{key}.{metric}" in selected} if key in {"iops", "throughput_bps", "latency_ms", "counts"} else child for key, child in item.items()} for item in items]
            if history:
                data = {**data, "items": items}
            elif items:
                data = items[0]
            else:
                data = {key: {metric: value for metric, value in child.items() if f"{key}.{metric}" in selected} if key in {"iops", "throughput_bps", "latency_ms", "counts"} else child for key, child in data.items()}
            metadata["unit_schema"] = {key: METRIC_UNITS[key] for key in filters.metric_ids}
        metadata.update(quality="PARTIAL" if any(item.get("partial") for item in items) else data.get("state", "UNKNOWN"), reasons=data.get("reasons", []))
        return SourceSnapshot(data, {"samples": items}, metadata=metadata)
