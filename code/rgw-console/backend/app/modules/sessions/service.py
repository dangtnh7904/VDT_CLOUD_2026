from __future__ import annotations

from uuid import UUID, uuid4

from ...config import Settings
from ...platform.config import build_config_snapshot, resolve_settings
from ..cluster_profiles.domain import ClusterReadError
from ..cluster_profiles.ports import ClusterObservationPort
from ..cluster_profiles.service import ClusterProfileService
from .domain import CreateSessionCommand, SessionError, SessionRepository, WORKFLOW_TYPES


class SessionService:
    def __init__(
        self,
        settings: Settings,
        observations: ClusterObservationPort | None,
        repository: SessionRepository,
    ) -> None:
        self.settings = resolve_settings(settings)
        self.observations = observations
        self.repository = repository

    def create(self, command: CreateSessionCommand) -> dict:
        self._validate_command(command)
        command = CreateSessionCommand(command.name.strip(), command.workflow_types)
        if not self.settings.cluster_id or not self.settings.ceph_expected_fsid:
            raise SessionError(
                "CLUSTER_PROFILE_MISMATCH",
                "CLUSTER_ID and CEPH_EXPECTED_FSID are required to create a session",
            )
        if self.observations is None:
            raise SessionError(
                "CAPABILITY_UNSUPPORTED",
                "cluster identity adapter is required to create a session",
            )
        try:
            identity = self.observations.identity()
        except ClusterReadError as exc:
            raise SessionError(
                exc.code,
                exc.message,
                retryable=exc.retryable,
                observed_state=exc.observed_state,
            ) from exc
        actual_fsid = identity.get("fsid")
        if actual_fsid != self.settings.ceph_expected_fsid:
            raise SessionError(
                "FSID_MISMATCH",
                "actual cluster FSID does not match the configured FSID",
                observed_state={
                    "expected_fsid": self.settings.ceph_expected_fsid,
                    "actual_fsid": actual_fsid,
                },
            )
        try:
            capabilities = ClusterProfileService(
                self.settings,
                self.observations,
            ).capabilities()
        except ClusterReadError as exc:
            raise SessionError(
                exc.code,
                exc.message,
                retryable=exc.retryable,
                observed_state=exc.observed_state,
            ) from exc
        if capabilities.get("fsid") != actual_fsid:
            raise SessionError(
                "FSID_MISMATCH",
                "identity and capability probes returned different cluster FSIDs",
            )
        if not capabilities.get("observed_at"):
            raise SessionError(
                "SCRUB_EVIDENCE_INCOMPLETE",
                "capability probe did not provide an observation timestamp",
            )
        snapshot = build_config_snapshot(self.settings)
        return self.repository.create(
            session_id=uuid4(),
            command=command,
            snapshot=snapshot,
            actual_fsid=actual_fsid,
            execution_environment=self.settings.execution_environment,
            capabilities=capabilities,
        )

    def get(self, session_id: UUID) -> dict:
        session = self.repository.get(session_id)
        if session is None:
            raise SessionError("SESSION_NOT_FOUND", "session does not exist")
        return session

    def _validate_command(self, command: CreateSessionCommand) -> None:
        name = command.name.strip()
        if not name or len(name) > 255:
            raise SessionError("INVALID_REQUEST", "session name must contain 1 to 255 characters")
        if not command.workflow_types:
            raise SessionError("INVALID_REQUEST", "at least one workflow must be requested")
        unknown = sorted(set(command.workflow_types) - WORKFLOW_TYPES)
        if unknown:
            raise SessionError("INVALID_REQUEST", f"unknown workflow types: {', '.join(unknown)}")
        if len(set(command.workflow_types)) != len(command.workflow_types):
            raise SessionError("INVALID_REQUEST", "workflow types must be unique")
        requirements = {
            "UPGRADE_PRODUCTION": self.settings.feature_upgrade,
            "QOS_OBSERVER": False,  # Historical records remain readable; no new runs.
            "LAB_TEST": self.settings.feature_lab and self.settings.lab_validation_enabled,
            "LEGACY": self.settings.feature_legacy_rgw or self.settings.feature_legacy_rbd,
            "ROLLBACK": self.settings.feature_upgrade,
        }
        disabled = sorted(item for item in command.workflow_types if not requirements[item])
        if disabled:
            raise SessionError(
                "CAPABILITY_UNSUPPORTED",
                f"requested workflows are disabled: {', '.join(disabled)}",
            )
