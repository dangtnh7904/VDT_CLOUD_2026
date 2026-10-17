from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from ...config import Settings
from ...platform.config import build_config_snapshot, resolve_settings
from ...platform.evidence import FilesystemArtifactStore
from .comparison import compare_collections
from .domain import CollectionPhase, OsdInfoError, validate_collection
from .evidence_comparison import compare_config_evidence
from .redaction import redact_collector_evidence


class OsdInfoService:
    def __init__(self, settings: Settings, repository, collector) -> None:
        self.settings = resolve_settings(settings)
        self.repository = repository
        self.collector = collector

    def create(
        self,
        *,
        session_id: UUID,
        phase: CollectionPhase,
        requested_osd_ids: tuple[int, ...] | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_enabled()
        allowed = self._allowed_osd_ids()
        selected = tuple(sorted(allowed if requested_osd_ids is None else requested_osd_ids))
        if not selected:
            raise OsdInfoError("SCOPE_NOT_ALLOWED", "no OSDs are authorized for inventory collection")
        if len(selected) > 128:
            raise OsdInfoError("INVALID_REQUEST", "at most 128 OSDs may be collected at once")
        if len(set(selected)) != len(selected) or any(osd_id < 0 for osd_id in selected):
            raise OsdInfoError("INVALID_REQUEST", "OSD IDs must be unique non-negative integers")
        outside = sorted(set(selected) - allowed)
        if outside:
            raise OsdInfoError(
                "SCOPE_NOT_ALLOWED",
                "one or more requested OSDs are outside UPGRADE_ALLOWED_OSDS",
                observed_state={"outside_allowlist": outside},
            )
        snapshot = build_config_snapshot(self.settings)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "session_id": str(session_id),
                    "phase": phase.value,
                    "osd_ids": selected,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        collection_id, replay = self.repository.claim(
            session_id=session_id,
            phase=phase.value,
            requested_osd_ids=selected,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            expected_cluster_id=snapshot.cluster_id,
            expected_fsid=str(snapshot.expected_fsid),
            expected_config_hash=snapshot.config_hash,
        )
        if replay is not None:
            return replay
        assert collection_id is not None
        try:
            raw = self.collector.collect(selected)
            validated = validate_collection(
                raw,
                expected_fsid=str(snapshot.expected_fsid),
                requested_osd_ids=selected,
            )
            artifact = FilesystemArtifactStore(
                self.settings.evidence_root,
                max_artifact_bytes=min(
                    self.settings.evidence_max_artifact_bytes,
                    self.settings.osd_info_collector_max_output_bytes,
                ),
            ).put_json(
                validated.raw,
                cluster_id=self.settings.cluster_id,
                session_id=session_id,
                run_id=collection_id,
            )
            return self.repository.finish(collection_id, validated=validated, artifact=artifact)
        except OsdInfoError as exc:
            self.repository.fail(collection_id, code=exc.code, message=exc.message, retryable=exc.retryable)
            raise
        except ValueError as exc:
            self.repository.fail(collection_id, code="EVIDENCE_ARTIFACT_REJECTED", message=str(exc), retryable=False)
            raise OsdInfoError("EVIDENCE_ARTIFACT_REJECTED", str(exc)) from exc
        except Exception as exc:
            self.repository.fail(collection_id, code="OSD_INFO_COLLECTION_FAILED", message=str(exc), retryable=False)
            raise

    def get(self, collection_id: UUID) -> dict[str, Any]:
        return self.repository.get(collection_id)

    def list(self, *, session_id: UUID, limit: int) -> dict[str, Any]:
        return self.repository.list(session_id=session_id, limit=limit)

    def get_osd(self, collection_id: UUID, osd_id: int) -> dict[str, Any]:
        return redact_collector_evidence(self.repository.get_osd(collection_id, osd_id))

    def get_evidence(self, collection_id: UUID) -> dict[str, Any]:
        collection = self.repository.get(collection_id)
        raw = self._load_verified_artifact(collection_id, collection)
        cluster_evidence = raw["cluster_evidence"]
        return {
            "schema_version": 1,
            "collection": {
                "id": str(collection_id),
                "phase": collection["phase"],
                "quality": collection["quality"],
                "collected_at": collection["collected_at"],
                "collector_version": collection["collector_version"],
            },
            "artifact": {
                "uri": collection["evidence_uri"],
                "sha256": collection["artifact_sha256"],
                "size_bytes": collection["evidence_size_bytes"],
                "verified": True,
            },
            "collection_errors": redact_collector_evidence(raw.get("errors", [])),
            "cluster_evidence": redact_collector_evidence(cluster_evidence),
        }

    def compare_evidence(self, *, before_id: UUID, after_id: UUID) -> dict[str, Any]:
        if before_id == after_id:
            raise OsdInfoError("INVALID_REQUEST", "before and after collections must differ")
        before = self.repository.get(before_id)
        after = self.repository.get(after_id)
        before_raw = self._load_verified_artifact(before_id, before)
        after_raw = self._load_verified_artifact(after_id, after)
        return compare_config_evidence(before, after, before_raw, after_raw)

    def _load_verified_artifact(
        self,
        collection_id: UUID,
        collection: dict[str, Any],
    ) -> dict[str, Any]:
        if collection.get("state") != "COMPLETE":
            raise OsdInfoError("EVIDENCE_NOT_READY", "collection evidence is not complete")
        uri = collection.get("evidence_uri")
        sha256 = collection.get("artifact_sha256")
        size_bytes = collection.get("evidence_size_bytes")
        if not isinstance(uri, str) or not isinstance(sha256, str) or not isinstance(size_bytes, int):
            raise OsdInfoError("EVIDENCE_NOT_READY", "collection evidence registry fields are incomplete")
        store = FilesystemArtifactStore(
            self.settings.evidence_root,
            max_artifact_bytes=min(
                self.settings.evidence_max_artifact_bytes,
                self.settings.osd_info_collector_max_output_bytes,
            ),
        )
        try:
            raw = store.read_json(
                uri,
                expected_sha256=sha256,
                expected_size_bytes=size_bytes,
            )
            validated = validate_collection(
                raw,
                expected_fsid=str(collection["fsid"]),
                requested_osd_ids=tuple(collection["requested_osd_ids"]),
            )
            if (
                validated.collector_version != collection.get("collector_version")
                or validated.quality.value != collection.get("quality")
            ):
                raise ValueError("evidence artifact metadata does not match its collection row")
            cluster_evidence = raw.get("cluster_evidence")
            if not isinstance(cluster_evidence, dict):
                raise ValueError("evidence artifact cluster_evidence is not an object")
        except (KeyError, OSError, TypeError, ValueError, OsdInfoError) as exc:
            raise OsdInfoError(
                "EVIDENCE_ARTIFACT_INVALID",
                "stored collection evidence failed integrity or protocol validation",
                observed_state={"collection_id": str(collection_id), "artifact_sha256": sha256},
            ) from exc
        return raw

    def compare(self, *, before_id: UUID, after_id: UUID) -> dict[str, Any]:
        if before_id == after_id:
            raise OsdInfoError("INVALID_REQUEST", "before and after collections must differ")
        return compare_collections(
            self.repository.get(before_id),
            self.repository.get(after_id),
        )

    def _require_enabled(self) -> None:
        if not self.settings.feature_upgrade:
            raise OsdInfoError("CAPABILITY_UNSUPPORTED", "upgrade inventory collection is disabled")
        if not self.settings.cluster_id or not self.settings.ceph_expected_fsid:
            raise OsdInfoError("CLUSTER_PROFILE_MISMATCH", "CLUSTER_ID and CEPH_EXPECTED_FSID are required")

    def _allowed_osd_ids(self) -> set[int]:
        result: set[int] = set()
        for value in self.settings.upgrade_allowed_osd_set:
            normalized = value[4:] if value.startswith("osd.") else value
            if not normalized.isdigit():
                raise OsdInfoError("SCOPE_NOT_ALLOWED", "UPGRADE_ALLOWED_OSDS must contain numeric OSD IDs")
            result.add(int(normalized))
        return result
