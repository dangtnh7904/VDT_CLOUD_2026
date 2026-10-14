from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from uuid import UUID, NAMESPACE_URL, uuid5

from ...platform.config import resolve_settings
from ...platform.evidence import FilesystemArtifactStore
from ...services.executor_client import ExecutorClient, ExecutorClientError
from ..osd_info_collector.redaction import redact_collector_evidence
from .normalization import normalize, samples
from .repository import CollectionRepository


ACTIONS = {
    "cluster": ("ceph.status", "ceph.health_detail", "ceph.df", "ceph.versions"),
    "mon": ("ceph.mon_dump", "ceph.quorum_status"),
    "mgr": ("ceph.mgr_dump", "ceph.mgr_modules", "ceph.mgr_services"),
    "rgw": ("ceph.daemon_ls",),
    "mds": ("ceph.fs_dump", "ceph.daemon_ls"),
    "host": ("ceph.host_ls",),
    "osd": ("ceph.osd_df", "ceph.osd_tree"),
    "pool": ("ceph.pool_ls_detail", "ceph.df"),
}
COLLECTION_SLOTS = threading.BoundedSemaphore(2)


class CollectionError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class ClusterMetricsService:
    def __init__(self, settings, repository=None, client=None):
        self.settings = resolve_settings(settings)
        self.repository = repository or CollectionRepository()
        self.client = client

    def _identity(self):
        if not self.settings.cluster_id or not self.settings.ceph_expected_fsid:
            raise CollectionError("CLUSTER_NOT_CONFIGURED", "Configure CLUSTER_ID and CEPH_EXPECTED_FSID before collecting.")
        return {"cluster_id": self.settings.cluster_id, "fsid": self.settings.ceph_expected_fsid}

    def _store(self):
        return FilesystemArtifactStore(self.settings.evidence_root, max_artifact_bytes=min(self.settings.evidence_max_artifact_bytes, 16 * 1024 * 1024))

    def list(self, limit=50):
        if not self.settings.cluster_id or not self.settings.ceph_expected_fsid:
            return {"items": [], "quality": "UNSUPPORTED", "reasons": ["CLUSTER_NOT_CONFIGURED"]}
        return {"items": self.repository.list(**self._identity(), limit=limit), "quality": "VALID"}

    def get(self, collection_id: UUID):
        row = self.repository.get(collection_id, **self._identity())
        if row is None:
            raise CollectionError("COLLECTION_NOT_FOUND", "Collection was not found in this cluster.", 404)
        try:
            payload = self._store().read_json(row["uri"], expected_sha256=row["sha256"], expected_size_bytes=row["size_bytes"])
        except (OSError, ValueError):
            raise CollectionError("EVIDENCE_ARTIFACT_INVALID", "Collection failed integrity validation.") from None
        if not isinstance(payload, dict) or payload.get("id") != str(collection_id) or any(payload.get(key) != value for key, value in self._identity().items()):
            raise CollectionError("EVIDENCE_ARTIFACT_INVALID", "Collection identity does not match its registry.")
        allowed_osds = {value.removeprefix("osd.") for value in self.settings.upgrade_allowed_osd_set}
        allowed_pools = self.settings.upgrade_allowed_pool_set
        for resource in payload.get("resources", []):
            scope = resource.get("scope_type")
            if ((scope == "osd" and resource.get("id") not in allowed_osds)
                or (scope == "host" and resource.get("id") not in self.settings.upgrade_allowed_host_set)
                or (scope == "pool" and resource.get("name") not in allowed_pools)):
                raise CollectionError("COLLECTION_SCOPE_REJECTED", "Saved collection includes resources no longer allowed by the current profile.", 403)
        result = redact_collector_evidence(payload)
        result["artifact"] = {"id": str(collection_id), "sha256": row["sha256"], "size_bytes": row["size_bytes"], "verified": True}
        try:
            age = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(payload["observed_at"])).total_seconds())
        except (TypeError, ValueError):
            age = None
        result["freshness"] = {"age_seconds": age, "state": "VALID" if age is not None and age <= self.settings.telemetry_max_age_seconds else "STALE"}
        return result

    def resources(self):
        listing = self.list(limit=1)
        if not listing["items"]:
            return {"resources": [], "quality": "UNSUPPORTED", "reasons": listing.get("reasons", ["NO_SNAPSHOT_YET"])}
        return self.get(UUID(str(listing["items"][0]["id"])))

    def create(self, *, scopes: list[str], resource_ids: list[str], idempotency_key: str, actor="operator"):
        identity = self._identity()
        if not scopes or set(scopes) - ACTIONS.keys() or len(scopes) != len(set(scopes)):
            raise CollectionError("INVALID_SCOPE", "Choose unique supported resource scopes.", 422)
        if resource_ids and len(scopes) != 1:
            raise CollectionError("INVALID_SCOPE", "Resource IDs require exactly one selected scope.", 422)
        if len(resource_ids) > 128 or len(set(resource_ids)) != len(resource_ids):
            raise CollectionError("INVALID_SCOPE", "Select at most 128 unique resource IDs.", 422)
        encoded = json.dumps({"scopes": sorted(scopes), "resource_ids": sorted(resource_ids)}, sort_keys=True).encode()
        request_hash = hashlib.sha256(encoded).hexdigest()
        collection_id = uuid5(NAMESPACE_URL, f"cluster-observation:{identity['cluster_id']}:{identity['fsid']}:{idempotency_key}")
        previous = self.repository.get(collection_id, **identity)
        if previous:
            if previous.get("metadata", {}).get("request_hash") != request_hash:
                raise CollectionError("IDEMPOTENCY_CONFLICT", "This request key already names a different collection.")
            return self.get(collection_id)
        if not COLLECTION_SLOTS.acquire(blocking=False):
            raise CollectionError("COLLECTION_BUSY", "Two collections are already running; retry later.", 429)
        try:
            client = self.client or ExecutorClient.from_settings()
            capabilities = client.capabilities()
            if capabilities.get("fsid") != identity["fsid"]:
                raise CollectionError("FSID_MISMATCH", "Executor belongs to a different cluster.")
            available = set(capabilities.get("actions", []))
            observed_at = datetime.now(timezone.utc).isoformat()
            evidence = {}
            for action in dict.fromkeys(action for scope in scopes for action in ACTIONS[scope]):
                if action not in available:
                    evidence[action] = {"quality": "UNSUPPORTED", "reason": "EXECUTOR_ACTION_UNSUPPORTED"}
                    continue
                try:
                    response = client.request(action, timeout_seconds=min(self.settings.rbd_executor_timeout_seconds, 15))
                    if response.get("fsid") != identity["fsid"]:
                        raise CollectionError("FSID_MISMATCH", "Observation belongs to a different cluster.")
                    evidence[action] = {"quality": "VALID", "observed_at": response.get("collected_at"), "data": redact_collector_evidence(response.get("data"))}
                except ExecutorClientError as exc:
                    if exc.code == "FSID_MISMATCH":
                        raise CollectionError("FSID_MISMATCH", "Observed cluster identity changed.") from None
                    evidence[action] = {"quality": "UNSUPPORTED", "reason": exc.code}
            if client.ceph_fsid().get("fsid") != identity["fsid"]:
                raise CollectionError("FSID_MISMATCH", "Cluster identity changed during collection.")
            resources = []
            limitations = []
            for scope in scopes:
                normalized = normalize(scope, evidence)
                if scope == "osd":
                    allowed = {value.removeprefix("osd.") for value in self.settings.upgrade_allowed_osd_set}
                    normalized = [row for row in normalized if row["id"] in allowed]
                elif scope == "host":
                    normalized = [row for row in normalized if row["id"] in self.settings.upgrade_allowed_host_set]
                elif scope == "pool":
                    allowed = self.settings.upgrade_allowed_pool_set
                    normalized = [row for row in normalized if row["name"] in allowed]
                if resource_ids:
                    normalized = [row for row in normalized if row["id"] in resource_ids]
                resources.extend(normalized)
                if not normalized:
                    limitations.append(f"{scope.upper()}_EMPTY_UNAVAILABLE_OR_OUTSIDE_ALLOWLIST")
            resolved_ids = {row["id"] for row in resources}
            missing = sorted(set(resource_ids) - resolved_ids)
            failures = [action for action, result in evidence.items() if result["quality"] != "VALID"]
            # Global raw CLI output can contain out-of-scope resources. Only the
            # filtered canonical projection is persisted; command coverage is metadata.
            source_status = {key: {field: value for field, value in result.items() if field != "data"} for key, result in evidence.items()}
            quality = "PARTIAL" if failures or limitations or missing else "VALID"
            payload = {"schema_version": 1, "collector_version": "cluster-info-1", "id": str(collection_id), **identity,
                       "source": "ceph_cli_executor", "observed_at": observed_at, "collected_at": datetime.now(timezone.utc).isoformat(),
                       "requested_scopes": scopes, "requested_resource_ids": resource_ids, "missing_resource_ids": missing,
                       "resources": resources, "quality": quality, "sources": source_status, "limitations": limitations,
                       "raw_evidence": "Canonical scoped projection only; unfiltered command output is not exported."}
            payload["metrics"] = samples(payload)
            artifact = self._store().put_json(payload, cluster_id=identity["cluster_id"], session_id=collection_id, run_id=collection_id)
            self.repository.save(collection_id, artifact=artifact, payload=payload, request_hash=request_hash, actor=actor)
            winner = self.repository.get(collection_id, **identity)
            if winner.get("metadata", {}).get("request_hash") != request_hash:
                raise CollectionError("IDEMPOTENCY_CONFLICT", "A concurrent request used this key for another scope.")
            return self.get(collection_id)
        except ExecutorClientError as exc:
            raise CollectionError(exc.code, "Cluster read failed; check executor identity, connectivity and permission.", 503) from None
        except ValueError as exc:
            if isinstance(exc, CollectionError):
                raise
            raise CollectionError("COLLECTOR_CONFIGURATION_INVALID", "Collector configuration or artifact bounds are invalid.") from None
        finally:
            COLLECTION_SLOTS.release()
