from __future__ import annotations

from typing import Any

from ...config import Settings
from ...platform.config import build_config_snapshot, resolve_settings
from .domain import CapabilityState, ClusterReadError
from .normalization import normalize_inventory
from .ports import ClusterObservationPort


class ClusterProfileService:
    def __init__(
        self,
        settings: Settings,
        observations: ClusterObservationPort | None = None,
    ) -> None:
        self.settings = resolve_settings(settings)
        self.observations = observations

    def profile(self) -> dict[str, Any]:
        snapshot = build_config_snapshot(self.settings)
        blockers = []
        if not self.settings.cluster_id:
            blockers.append("CLUSTER_ID_MISSING")
        if not self.settings.ceph_expected_fsid:
            blockers.append("CEPH_EXPECTED_FSID_MISSING")
        if not self.settings.effective_executor_token:
            blockers.append("CEPH_EXECUTOR_TOKEN_MISSING")
        if self.settings.upgrade_mutations_enabled:
            if not self.settings.upgrade_allowed_osd_set:
                blockers.append("UPGRADE_ALLOWED_OSDS_MISSING")
            if not self.settings.upgrade_allowed_host_set:
                blockers.append("UPGRADE_ALLOWED_HOSTS_MISSING")
            if not self.settings.upgrade_allowed_pool_set:
                blockers.append("UPGRADE_ALLOWED_POOLS_MISSING")
        return {
            "schema_version": 1,
            "cluster_id": self.settings.cluster_id or None,
            "expected_fsid": self.settings.ceph_expected_fsid,
            "profile_revision": self.settings.cluster_profile_revision,
            "policy_revision": self.settings.policy_revision,
            "execution_environment": self.settings.execution_environment,
            "config_hash": snapshot.config_hash,
            "status": "READY" if not blockers else "BLOCKED",
            "blockers": blockers,
            "feature_flags": snapshot.payload["feature_readiness"],
            "deployment_scope": {
                "osds": sorted(self.settings.upgrade_allowed_osd_set),
                "hosts": sorted(self.settings.upgrade_allowed_host_set),
                "pools": sorted(self.settings.upgrade_allowed_pool_set),
                "device_classes": sorted(self.settings.upgrade_allowed_device_class_set),
            },
        }

    def capabilities(self) -> dict[str, Any]:
        self._require_readiness()
        if self.observations is None:
            raise ClusterReadError("CAPABILITY_UNSUPPORTED", "cluster adapter is not configured")
        raw = self.observations.capabilities()
        actions = set(raw.get("actions") or [])

        def state(required_actions: set[str]) -> str:
            return (
                CapabilityState.SUPPORTED.value
                if required_actions.issubset(actions)
                else CapabilityState.UNSUPPORTED.value
            )

        matrix = {
            "query_cluster_identity": state({"ceph.fsid"}),
            "query_osd_inventory": state(
                {"ceph.status", "ceph.osd_df", "ceph.osd_tree", "ceph.pool_ls_detail"}
            ),
            "collect_osd_info": (
                state({"ceph.osd_info_collect"})
                if self.settings.upgrade_allowed_osd_set
                else CapabilityState.DISABLED.value
            ),
            "query_osd_image_digest": CapabilityState.UNSUPPORTED.value,
            "query_pg_up_acting_primary": CapabilityState.UNSUPPORTED.value,
            "deep_scrub_completion_marker": CapabilityState.UNSUPPORTED.value,
            "cephadm_redeploy_target_image": CapabilityState.UNSUPPORTED.value,
            "safe_to_destroy": CapabilityState.UNSUPPORTED.value,
            "prometheus_client_counters": (
                CapabilityState.UNSUPPORTED.value
                if self.settings.telemetry_provider == "prometheus"
                else CapabilityState.DISABLED.value
            ),
        }
        return {
            "schema_version": 1,
            "cluster_id": self.settings.cluster_id,
            "fsid": raw.get("fsid"),
            "observed_at": raw.get("collected_at"),
            "source": {
                "executor_version": raw.get("executor_version"),
                "protocol_version": raw.get("protocol_version"),
            },
            "capabilities": matrix,
        }

    def inventory(self) -> dict[str, Any]:
        self._require_readiness()
        if self.observations is None:
            raise ClusterReadError("CAPABILITY_UNSUPPORTED", "cluster adapter is not configured")
        raw = self.observations.inventory()
        return normalize_inventory(
            raw,
            cluster_id=self.settings.cluster_id,
            allowed_osds=self.settings.upgrade_allowed_osd_set,
            allowed_hosts=self.settings.upgrade_allowed_host_set,
            allowed_pools=self.settings.upgrade_allowed_pool_set,
            allowed_device_classes=self.settings.upgrade_allowed_device_class_set,
        )

    def _require_readiness(self) -> None:
        if not self.settings.cluster_id or not self.settings.ceph_expected_fsid:
            raise ClusterReadError(
                "CLUSTER_PROFILE_MISMATCH",
                "cluster ID and expected FSID are required for read-only cluster access",
            )
