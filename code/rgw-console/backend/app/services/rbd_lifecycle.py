from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from ..config import get_settings
from ..db import connection, record_operation
from .capacity_guard import (
    CapacityRejected,
    finish_reservation,
    require_admission,
    reservation_lease,
)
from .rbd_agent_client import RbdAgentClient, RbdAgentClientError


MUTATION_TO_OPERATION = {
    "rbd.image.create": "RBD_CREATE",
    "rbd.image.map": "RBD_MAP",
    "rbd.device.format_ext4": "RBD_FORMAT",
    "rbd.device.mount": "RBD_MOUNT",
    "rbd.device.unmount": "RBD_UNMOUNT",
    "rbd.device.unmap": "RBD_UNMAP",
    "rbd.image.remove": "RBD_DELETE",
}
AMBIGUOUS_AGENT_CODES = {
    "AGENT_TIMEOUT",
    "AGENT_UNAVAILABLE",
    "AGENT_PROTOCOL_ERROR",
    "AGENT_RESPONSE_TOO_LARGE",
    "FSID_MISMATCH",
    "FENCE_REJECTED",
    "STALE_FENCE",
    "STATE_CONFLICT",
}
BUSY_CODES = {
    "BUSY",
    "VOLUME_BUSY",
    "DEVICE_BUSY",
    "MOUNT_BUSY",
    "IMAGE_IN_USE",
    "IMAGE_ALREADY_MAPPED",
}
DEPENDENCY_CODES = {
    "DEPENDENCY_EXISTS",
    "SNAPSHOT_EXISTS",
    "CLONE_EXISTS",
    "DELETE_BLOCKED_DEPENDENCY",
}
FINAL_AGENT_CODES = {
    "INVALID_PARAMS",
    "ACTION_NOT_ALLOWED",
    "INVALID_SIZE",
    "SCOPE_NOT_ALLOWED",
    "IMAGE_ALREADY_EXISTS",
    "VOLUME_ID_CONFLICT",
    "FEATURE_MISMATCH",
    "FORMAT_NOT_ALLOWED",
    "CREATION_IDENTITY_MISMATCH",
    "FILESYSTEM_SIGNATURE_PRESENT",
    "UNMANAGED_VOLUME",
    "IMAGE_IDENTITY_MISMATCH",
    "DEVICE_IDENTITY_MISMATCH",
    "FILESYSTEM_IDENTITY_MISMATCH",
    "MOUNTPOINT_NOT_EMPTY",
    "MOUNT_IDENTITY_CONFLICT",
}


class RbdActionFenceLost(RuntimeError):
    pass


class RbdActionStateError(RuntimeError):
    pass


@dataclass
class ClaimedAction:
    action: dict[str, Any]
    volume: dict[str, Any]
    request_id: str


def granular_action_id(action_id: UUID | str, step: str) -> str:
    """Stable agent idempotency identity for one step of a lifecycle action."""

    return str(uuid5(UUID(str(action_id)), step))


def _items(result: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = result.get(key, result.get("items", []))
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


class RbdLifecycleWorker:
    """Fenced RBD lifecycle orchestrator.

    A timeout or transport loss is never interpreted as "not executed". Such an
    action is moved to RECONCILING and only read-only image/device observations
    may make it runnable again.
    """

    def __init__(
        self,
        client: RbdAgentClient | Any | None = None,
        *,
        worker_id: str | None = None,
    ) -> None:
        self.client = client or RbdAgentClient.from_settings()
        self.worker_id = worker_id or f"rbd-worker-{uuid.uuid4()}"
        self.lease_seconds = int(get_settings().rbd_action_lease_seconds)

    def quarantine_expired(self) -> int:
        """Fence expired workers; no automatic mutation takeover is permitted."""

        with connection() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    SELECT action.id,action.volume_id,volume.observed_state
                      FROM rbd_actions action
                      JOIN rbd_volumes volume ON volume.id=action.volume_id
                     WHERE action.state='RUNNING'
                       AND action.lease_expires_at IS NOT NULL
                       AND action.lease_expires_at < now()
                     FOR UPDATE OF action,volume SKIP LOCKED
                    """
                ).fetchall()
                for row in rows:
                    conn.execute(
                        """
                        UPDATE rbd_actions
                           SET state='RECONCILING',observed_state=%s,
                               lease_owner=NULL,heartbeat_at=NULL,lease_expires_at=NULL,
                               error_code='ACTION_LEASE_EXPIRED',
                               error='Worker lease expired; read-only reconciliation is required'
                         WHERE id=%s AND state='RUNNING'
                        """,
                        (row["observed_state"], row["id"]),
                    )
                    conn.execute(
                        """
                        UPDATE rbd_volumes
                           SET observed_state='RECONCILING',
                               last_error='Worker lease expired; reconciliation required',
                               updated_at=now()
                         WHERE id=%s
                        """,
                        (row["volume_id"],),
                    )
        return len(rows)

    def _claim(self, state: str) -> ClaimedAction | None:
        with connection() as conn:
            with conn.transaction():
                candidate = conn.execute(
                    """
                    SELECT id
                      FROM rbd_actions
                     WHERE state=%s
                       AND (lease_expires_at IS NULL OR lease_expires_at < now())
                     ORDER BY created_at,id
                     FOR UPDATE SKIP LOCKED
                     LIMIT 1
                    """,
                    (state,),
                ).fetchone()
                if candidate is None:
                    return None
                row = conn.execute(
                    """
                    UPDATE rbd_actions
                       SET state=CASE WHEN %s='PENDING' THEN 'RUNNING' ELSE state END,
                           lease_owner=%s,lease_generation=lease_generation+1,
                           heartbeat_at=now(),
                           lease_expires_at=now() + (%s * interval '1 second'),
                           started_at=coalesce(started_at,now()),attempt_count=attempt_count+1
                     WHERE id=%s AND state=%s
                    RETURNING id
                    """,
                    (state, self.worker_id, self.lease_seconds, candidate["id"], state),
                ).fetchone()
                if row is None:
                    return None
                loaded = conn.execute(
                    """
                    SELECT row_to_json(action) AS action,
                           row_to_json(volume) AS volume,
                           idem.request_id
                      FROM rbd_actions action
                      JOIN rbd_volumes volume ON volume.id=action.volume_id
                      JOIN idempotency_requests idem ON idem.id=action.idempotency_request_id
                     WHERE action.id=%s
                    """,
                    (candidate["id"],),
                ).fetchone()
        return ClaimedAction(
            action=dict(loaded["action"]),
            volume=dict(loaded["volume"]),
            request_id=str(loaded["request_id"]),
        )

    def claim_pending(self) -> ClaimedAction | None:
        return self._claim("PENDING")

    def claim_reconciling(self) -> ClaimedAction | None:
        return self._claim("RECONCILING")

    @contextmanager
    def _heartbeat(self, claimed: ClaimedAction):
        stop = threading.Event()
        lost = threading.Event()
        action = claimed.action
        generation = int(action["lease_generation"])

        def renew() -> None:
            interval = max(1.0, self.lease_seconds / 3)
            while not stop.wait(interval):
                try:
                    with connection() as conn:
                        row = conn.execute(
                            """
                            UPDATE rbd_actions
                               SET heartbeat_at=now(),
                                   lease_expires_at=now() + (%s * interval '1 second')
                             WHERE id=%s AND lease_owner=%s AND lease_generation=%s
                               AND state IN ('RUNNING','RECONCILING')
                            RETURNING id
                            """,
                            (
                                self.lease_seconds,
                                action["id"],
                                self.worker_id,
                                generation,
                            ),
                        ).fetchone()
                        conn.commit()
                    if row is None:
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return

        thread = threading.Thread(
            target=renew,
            name=f"rbd-action-heartbeat-{action['id']}",
            daemon=True,
        )
        thread.start()
        try:
            yield lost
            if lost.is_set():
                raise RbdActionFenceLost("RBD action lease heartbeat was lost")
        finally:
            stop.set()
            thread.join(timeout=2)

    @staticmethod
    def _common_params(
        action: dict[str, Any],
        volume: dict[str, Any],
        step: str,
        fence_token: int,
    ) -> dict[str, Any]:
        return {
            "volume_id": str(volume["id"]),
            "action_id": granular_action_id(action["id"], step),
            "fence_token": fence_token,
            "pool": volume["pool"],
            "namespace": volume.get("namespace") or "",
            "image_name": volume["image_name"],
        }

    @staticmethod
    def _validate_identity(result: dict[str, Any], volume: dict[str, Any]) -> None:
        expected = {
            "pool": volume["pool"],
            "namespace": volume.get("namespace") or "",
            "image_name": volume["image_name"],
        }
        for field, value in expected.items():
            if field not in result or result[field] != value:
                raise RbdAgentClientError(
                    "AGENT_PROTOCOL_ERROR",
                    f"Host-agent result did not confirm the expected {field}",
                    retryable=False,
                )
        if volume.get("image_id") and result.get("image_id") != volume["image_id"]:
            raise RbdAgentClientError(
                "STATE_CONFLICT",
                "Host-agent result image identity differs from the database",
                retryable=False,
            )

    def _set_current_step(self, claimed: ClaimedAction, step: str) -> int:
        action = claimed.action
        with connection() as conn:
            with conn.transaction():
                owned = conn.execute(
                    """
                    SELECT action.current_step,action.current_fence_token
                      FROM rbd_actions action
                      JOIN rbd_volumes volume ON volume.id=action.volume_id
                     WHERE action.id=%s AND action.state='RUNNING'
                       AND action.lease_owner=%s AND action.lease_generation=%s
                       AND action.volume_generation=%s
                       AND volume.transition_generation=action.volume_generation
                     FOR UPDATE OF action,volume
                    """,
                    (
                        action["id"],
                        self.worker_id,
                        action["lease_generation"],
                        action["volume_generation"],
                    ),
                ).fetchone()
                if owned is None:
                    raise RbdActionFenceLost("RBD action lost its fence before an agent call")
                fence_token = owned["current_fence_token"]
                if owned["current_step"] != step or fence_token is None:
                    fenced = conn.execute(
                        """
                        UPDATE rbd_volumes
                           SET agent_fence_token=agent_fence_token+1,updated_at=now()
                         WHERE id=%s AND transition_generation=%s
                        RETURNING agent_fence_token
                        """,
                        (claimed.volume["id"], action["volume_generation"]),
                    ).fetchone()
                    if fenced is None:
                        raise RbdActionFenceLost("RBD volume fence could not be advanced")
                    fence_token = int(fenced["agent_fence_token"])
                row = conn.execute(
                    """
                    UPDATE rbd_actions
                       SET current_step=%s,current_fence_token=%s,heartbeat_at=now(),
                           lease_expires_at=now() + (%s * interval '1 second')
                     WHERE id=%s AND state='RUNNING' AND lease_owner=%s
                       AND lease_generation=%s AND volume_generation=%s
                    RETURNING id
                    """,
                    (
                        step,
                        fence_token,
                        self.lease_seconds,
                        action["id"],
                        self.worker_id,
                        action["lease_generation"],
                        action["volume_generation"],
                    ),
                ).fetchone()
        if row is None:
            raise RbdActionFenceLost("RBD action lost its fence before an agent call")
        action["current_step"] = step
        action["current_fence_token"] = fence_token
        return int(fence_token)

    def _audit(
        self,
        claimed: ClaimedAction,
        step: str,
        *,
        success: bool,
        latency_ms: float,
        error: str | None = None,
        error_code: str | None = None,
    ) -> None:
        try:
            volume = claimed.volume
            bytes_count = int(volume["logical_size_bytes"]) if step == "rbd.image.create" else 0
            record_operation(
                kind=MUTATION_TO_OPERATION[step],
                success=success,
                bytes_count=bytes_count,
                latency_ms=latency_ms,
                volume_id=volume["id"],
                request_id=claimed.request_id,
                source="rbd-lifecycle-worker",
                error=error[:1000] if error else None,
                error_code=error_code,
                bytes_delta_logical=(bytes_count if step == "rbd.image.create" else 0),
                capacity_decision_id=claimed.action.get("capacity_decision_id"),
            )
        except Exception:
            # Audit failure after a privileged command must not turn a known result
            # into an invented command failure. The action row remains authoritative.
            pass

    def _invoke(
        self,
        claimed: ClaimedAction,
        step: str,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        fence_token = self._set_current_step(claimed, step)
        params = self._common_params(claimed.action, claimed.volume, step, fence_token)
        params.update(extra)
        started = time.monotonic()
        try:
            result = self.client.mutate(step, params)
            self._validate_identity(result, claimed.volume)
        except RbdAgentClientError as exc:
            self._audit(
                claimed,
                step,
                success=False,
                latency_ms=(time.monotonic() - started) * 1000,
                error=exc.message,
                error_code=exc.code,
            )
            raise
        self._audit(
            claimed,
            step,
            success=True,
            latency_ms=(time.monotonic() - started) * 1000,
        )
        return result

    def _checkpoint(
        self,
        claimed: ClaimedAction,
        state: str,
        **changes: Any,
    ) -> None:
        action = claimed.action
        volume = claimed.volume
        updated = dict(volume)
        updated.update(changes)
        updated["observed_state"] = state
        with connection() as conn:
            with conn.transaction():
                owned = conn.execute(
                    """
                    SELECT action.id
                      FROM rbd_actions action
                      JOIN rbd_volumes volume ON volume.id=action.volume_id
                     WHERE action.id=%s AND action.state='RUNNING'
                       AND action.lease_owner=%s AND action.lease_generation=%s
                       AND action.volume_generation=%s
                       AND volume.transition_generation=action.volume_generation
                     FOR UPDATE OF action,volume
                    """,
                    (
                        action["id"],
                        self.worker_id,
                        action["lease_generation"],
                        action["volume_generation"],
                    ),
                ).fetchone()
                if owned is None:
                    raise RbdActionFenceLost("RBD lifecycle checkpoint was fenced")
                conn.execute(
                    """
                    UPDATE rbd_volumes
                       SET observed_state=%s,image_id=%s,feature_set=%s,
                           device=%s,device_major=%s,device_minor=%s,
                           fs_uuid=%s,mountpoint=%s,last_error=NULL,updated_at=now(),
                           deleted_at=CASE WHEN %s='DELETED' THEN now() ELSE deleted_at END
                     WHERE id=%s AND transition_generation=%s
                    """,
                    (
                        state,
                        updated.get("image_id"),
                        updated.get("feature_set") or [],
                        updated.get("device"),
                        updated.get("device_major"),
                        updated.get("device_minor"),
                        updated.get("fs_uuid"),
                        updated.get("mountpoint"),
                        state,
                        volume["id"],
                        action["volume_generation"],
                    ),
                )
                conn.execute(
                    "UPDATE rbd_actions SET observed_state=%s WHERE id=%s",
                    (state, action["id"]),
                )
        claimed.volume = updated

    def _verify_image(self, claimed: ClaimedAction) -> dict[str, Any]:
        volume = claimed.volume
        result = self.client.rbd_image_info(
            pool=volume["pool"],
            namespace=volume.get("namespace") or "",
            image_name=volume["image_name"],
        )
        self._validate_identity(result, volume)
        if result.get("image_id") != volume.get("image_id"):
            raise RbdAgentClientError(
                "STATE_CONFLICT",
                "Read-back image identity differs from the create result",
            )
        return result

    def _create_image(self, claimed: ClaimedAction) -> None:
        volume = claimed.volume
        result = self._invoke(
            claimed,
            "rbd.image.create",
            {"size_bytes": int(volume["logical_size_bytes"])},
        )
        image_id = result.get("image_id")
        features = result.get("features")
        if not isinstance(image_id, str) or not image_id:
            raise RbdAgentClientError("AGENT_PROTOCOL_ERROR", "Create result has no image_id")
        if int(result.get("size_bytes", -1)) != int(volume["logical_size_bytes"]):
            raise RbdAgentClientError("STATE_CONFLICT", "Created image size differs from the request")
        if not isinstance(features, list) or "exclusive-lock" not in features:
            raise RbdAgentClientError(
                "STATE_CONFLICT",
                "Created image did not confirm the exclusive-lock feature",
            )
        claimed.volume["image_id"] = image_id
        self._verify_image(claimed)
        self._checkpoint(claimed, "CREATED", image_id=image_id, feature_set=features)

    def _map(self, claimed: ClaimedAction) -> None:
        volume = claimed.volume
        if not volume.get("image_id"):
            raise RbdActionStateError("Cannot map a volume without an immutable image_id")
        result = self._invoke(
            claimed,
            "rbd.image.map",
            {"image_id": volume["image_id"]},
        )
        device = result.get("device")
        major = result.get("device_major")
        minor = result.get("device_minor")
        if (
            not isinstance(device, str)
            or not device.startswith("/dev/")
            or isinstance(major, bool)
            or not isinstance(major, int)
            or major < 0
            or isinstance(minor, bool)
            or not isinstance(minor, int)
            or minor < 0
        ):
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR", "Map result has no valid device identity"
            )
        self._checkpoint(
            claimed,
            "MAPPED",
            device=device,
            device_major=major,
            device_minor=minor,
        )

    def _format(self, claimed: ClaimedAction) -> None:
        volume = claimed.volume
        required = ("image_id", "device_major", "device_minor", "creation_action_id")
        if any(volume.get(field) is None for field in required):
            raise RbdActionStateError("Volume identity is incomplete before format")
        require_admission(
            "RBD_FORMAT",
            0,
            request_id=claimed.request_id,
            affected_pools=[volume["pool"]],
        )
        result = self._invoke(
            claimed,
            "rbd.device.format_ext4",
            {
                "image_id": volume["image_id"],
                "creation_action_id": str(volume["creation_action_id"]),
                "device_major": int(volume["device_major"]),
                "device_minor": int(volume["device_minor"]),
            },
        )
        fs_uuid = result.get("fs_uuid")
        if not isinstance(fs_uuid, str) or not fs_uuid or result.get("filesystem") != "ext4":
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR", "Format result did not confirm an ext4 filesystem UUID"
            )
        self._checkpoint(claimed, "FORMATTED", fs_uuid=fs_uuid)

    def _mount(self, claimed: ClaimedAction) -> None:
        volume = claimed.volume
        required = ("image_id", "device_major", "device_minor", "fs_uuid")
        if any(volume.get(field) is None for field in required):
            raise RbdActionStateError("Volume identity is incomplete before mount")
        result = self._invoke(
            claimed,
            "rbd.device.mount",
            {
                "image_id": volume["image_id"],
                "device_major": int(volume["device_major"]),
                "device_minor": int(volume["device_minor"]),
                "fs_uuid": volume["fs_uuid"],
            },
        )
        mountpoint = result.get("mountpoint")
        if not isinstance(mountpoint, str) or result.get("state") not in {"mounted", "MOUNTED", "READY"}:
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR", "Mount result did not confirm a mounted path"
            )
        self._checkpoint(claimed, "READY", mountpoint=mountpoint)

    def _unmount(self, claimed: ClaimedAction) -> None:
        volume = claimed.volume
        required = ("image_id", "device_major", "device_minor", "fs_uuid")
        if any(volume.get(field) is None for field in required):
            raise RbdActionStateError("Volume identity is incomplete before unmount")
        result = self._invoke(
            claimed,
            "rbd.device.unmount",
            {
                "image_id": volume["image_id"],
                "device_major": int(volume["device_major"]),
                "device_minor": int(volume["device_minor"]),
                "fs_uuid": volume["fs_uuid"],
            },
        )
        if result.get("state") not in {"unmounted", "UNMOUNTED"}:
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR", "Unmount result did not confirm the unmounted state"
            )
        self._checkpoint(claimed, "UNMOUNTED", mountpoint=result.get("mountpoint"))

    def _unmap(self, claimed: ClaimedAction) -> None:
        volume = claimed.volume
        required = ("image_id", "device_major", "device_minor")
        if any(volume.get(field) is None for field in required):
            raise RbdActionStateError("Volume identity is incomplete before unmap")
        result = self._invoke(
            claimed,
            "rbd.device.unmap",
            {
                "image_id": volume["image_id"],
                "device_major": int(volume["device_major"]),
                "device_minor": int(volume["device_minor"]),
            },
        )
        if result.get("state") not in {"unmapped", "UNMAPPED"}:
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR", "Unmap result did not confirm the unmapped state"
            )
        self._checkpoint(
            claimed,
            "UNMAPPED",
            device=None,
            device_major=None,
            device_minor=None,
            mountpoint=None,
        )

    def _remove(self, claimed: ClaimedAction) -> None:
        volume = claimed.volume
        if not volume.get("image_id"):
            raise RbdActionStateError("Cannot remove a volume without an immutable image_id")
        decision = require_admission(
            "RBD_DELETE_CLEANUP",
            1,
            request_id=claimed.request_id,
            affected_pools=[volume["pool"]],
        )
        try:
            with reservation_lease(decision):
                result = self._invoke(
                    claimed,
                    "rbd.image.remove",
                    {"image_id": volume["image_id"]},
                )
        except Exception:
            finish_reservation(decision, "ambiguous")
            raise
        finish_reservation(decision, "success")
        if result.get("state") not in {"deleted", "DELETED", "removed", "REMOVED"}:
            raise RbdAgentClientError(
                "AGENT_PROTOCOL_ERROR", "Remove result did not confirm image deletion"
            )
        self._checkpoint(
            claimed,
            "DELETED",
            device=None,
            device_major=None,
            device_minor=None,
            mountpoint=None,
        )

    def _complete(self, claimed: ClaimedAction) -> None:
        action = claimed.action
        volume = claimed.volume
        with connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    UPDATE rbd_actions
                       SET state='SUCCEEDED',observed_state=%s,finished_at=now(),
                           redacted_result=%s::jsonb,error_code=NULL,error=NULL,
                           lease_owner=NULL,heartbeat_at=NULL,lease_expires_at=NULL
                     WHERE id=%s AND state='RUNNING' AND lease_owner=%s
                       AND lease_generation=%s AND volume_generation=%s
                    RETURNING id
                    """,
                    (
                        volume["observed_state"],
                        json.dumps(
                            {
                                "volume_id": str(volume["id"]),
                                "observed_state": volume["observed_state"],
                            }
                        ),
                        action["id"],
                        self.worker_id,
                        action["lease_generation"],
                        action["volume_generation"],
                    ),
                ).fetchone()
                if row is None:
                    raise RbdActionFenceLost("RBD action completion was fenced")
                if volume["observed_state"] == "DELETED" and volume.get("capacity_reservation_id"):
                    conn.execute(
                        """
                        UPDATE capacity_reservations
                           SET state='SETTLING',remaining_commitment_bytes=0,
                               settled_at=now(),updated_at=now()
                         WHERE id=%s AND state='PERSISTENT_COMMITMENT'
                        """,
                        (volume["capacity_reservation_id"],),
                    )

    def _mark_reconciling(
        self,
        claimed: ClaimedAction,
        code: str,
        message: str,
    ) -> None:
        action = claimed.action
        with connection() as conn:
            with conn.transaction():
                current = conn.execute(
                    "SELECT observed_state FROM rbd_volumes WHERE id=%s FOR UPDATE",
                    (claimed.volume["id"],),
                ).fetchone()
                row = conn.execute(
                    """
                    UPDATE rbd_actions
                       SET state='RECONCILING',observed_state=%s,error_code=%s,error=%s,
                           lease_owner=NULL,heartbeat_at=NULL,lease_expires_at=NULL
                     WHERE id=%s AND state='RUNNING' AND lease_owner=%s
                       AND lease_generation=%s AND volume_generation=%s
                    RETURNING id
                    """,
                    (
                        current["observed_state"] if current else claimed.volume["observed_state"],
                        code,
                        message[:2000],
                        action["id"],
                        self.worker_id,
                        action["lease_generation"],
                        action["volume_generation"],
                    ),
                ).fetchone()
                if row is None:
                    return
                conn.execute(
                    """
                    UPDATE rbd_volumes
                       SET observed_state='RECONCILING',last_error=%s,updated_at=now()
                     WHERE id=%s AND transition_generation=%s
                    """,
                    (message[:2000], claimed.volume["id"], action["volume_generation"]),
                )

    def _fail_final(
        self,
        claimed: ClaimedAction,
        code: str,
        message: str,
        volume_state: str | None = None,
    ) -> None:
        action = claimed.action
        volume_state = volume_state or claimed.action.get("observed_state") or claimed.volume["observed_state"]
        with connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    UPDATE rbd_actions
                       SET state='FAILED_FINAL',observed_state=%s,error_code=%s,error=%s,
                           finished_at=now(),lease_owner=NULL,heartbeat_at=NULL,lease_expires_at=NULL
                     WHERE id=%s AND state='RUNNING' AND lease_owner=%s
                       AND lease_generation=%s AND volume_generation=%s
                    RETURNING id
                    """,
                    (
                        volume_state,
                        code,
                        message[:2000],
                        action["id"],
                        self.worker_id,
                        action["lease_generation"],
                        action["volume_generation"],
                    ),
                ).fetchone()
                if row:
                    conn.execute(
                        """
                        UPDATE rbd_volumes
                           SET observed_state=%s,last_error=%s,updated_at=now()
                         WHERE id=%s AND transition_generation=%s
                        """,
                        (
                            volume_state,
                            message[:2000],
                            claimed.volume["id"],
                            action["volume_generation"],
                        ),
                    )
                    if (
                        action.get("action_type") == "CREATE"
                        and not claimed.volume.get("image_id")
                        and claimed.volume.get("capacity_reservation_id")
                    ):
                        conn.execute(
                            """
                            UPDATE capacity_reservations
                               SET state='SETTLING',remaining_commitment_bytes=0,
                                   settled_at=now(),updated_at=now()
                             WHERE id=%s AND state='PERSISTENT_COMMITMENT'
                            """,
                            (claimed.volume["capacity_reservation_id"],),
                        )

    def _fail_retryable(self, claimed: ClaimedAction, code: str, message: str) -> None:
        action = claimed.action
        observed = claimed.volume["observed_state"]
        with connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    UPDATE rbd_actions
                       SET state='FAILED_RETRYABLE',observed_state=%s,error_code=%s,error=%s,
                           finished_at=now(),lease_owner=NULL,heartbeat_at=NULL,lease_expires_at=NULL
                     WHERE id=%s AND state='RUNNING' AND lease_owner=%s
                       AND lease_generation=%s AND volume_generation=%s
                    RETURNING id
                    """,
                    (
                        observed,
                        code,
                        message[:2000],
                        action["id"],
                        self.worker_id,
                        action["lease_generation"],
                        action["volume_generation"],
                    ),
                ).fetchone()
                if row:
                    conn.execute(
                        """
                        UPDATE rbd_volumes
                           SET last_error=%s,updated_at=now()
                         WHERE id=%s AND transition_generation=%s
                        """,
                        (message[:2000], claimed.volume["id"], action["volume_generation"]),
                    )

    def process(self, claimed: ClaimedAction) -> None:
        action_type = claimed.action["action_type"]
        try:
            with self._heartbeat(claimed):
                state = claimed.volume["observed_state"]
                if action_type == "CREATE":
                    if state in {"REQUESTED", "CAPACITY_RESERVED"}:
                        self._create_image(claimed)
                        state = claimed.volume["observed_state"]
                    if not bool(claimed.volume.get("auto_mount")):
                        if state != "CREATED":
                            raise RbdActionStateError(f"Unexpected create state {state}")
                    else:
                        if state in {"CREATED", "UNMAPPED"}:
                            self._map(claimed)
                            state = claimed.volume["observed_state"]
                        if state == "MAPPED" and not claimed.volume.get("fs_uuid"):
                            self._format(claimed)
                            state = claimed.volume["observed_state"]
                        if state in {"MAPPED", "FORMATTED", "UNMOUNTED"}:
                            self._mount(claimed)
                            state = claimed.volume["observed_state"]
                        if state != "READY":
                            raise RbdActionStateError(f"Unexpected create state {state}")
                elif action_type == "MOUNT":
                    if state in {"CREATED", "UNMAPPED"}:
                        self._map(claimed)
                        state = claimed.volume["observed_state"]
                    if state == "MAPPED" and not claimed.volume.get("fs_uuid"):
                        self._format(claimed)
                        state = claimed.volume["observed_state"]
                    if state in {"MAPPED", "FORMATTED", "UNMOUNTED"}:
                        self._mount(claimed)
                        state = claimed.volume["observed_state"]
                    if state != "READY":
                        raise RbdActionStateError(f"Unexpected mount state {state}")
                elif action_type == "UNMOUNT":
                    if state in {"READY", "MOUNTED"}:
                        self._unmount(claimed)
                        state = claimed.volume["observed_state"]
                    if state != "UNMOUNTED":
                        raise RbdActionStateError(f"Unexpected unmount state {state}")
                elif action_type == "DELETE":
                    if state in {"REQUESTED", "CAPACITY_RESERVED"} and not claimed.volume.get("image_id"):
                        self._checkpoint(claimed, "DELETED")
                        state = claimed.volume["observed_state"]
                    if state in {"READY", "MOUNTED"}:
                        self._unmount(claimed)
                        state = claimed.volume["observed_state"]
                    if state in {"MAPPED", "FORMATTED", "UNMOUNTED"}:
                        self._unmap(claimed)
                        state = claimed.volume["observed_state"]
                    if state in {
                        "CREATED",
                        "UNMAPPED",
                        "MAP_FAILED",
                        "FORMAT_FAILED",
                        "MOUNT_FAILED",
                        "BUSY",
                        "DELETE_BLOCKED_DEPENDENCY",
                    }:
                        self._remove(claimed)
                        state = claimed.volume["observed_state"]
                    if state != "DELETED":
                        raise RbdActionStateError(f"Unexpected delete state {state}")
                else:
                    raise RbdActionStateError(f"Unsupported lifecycle action {action_type}")
                self._complete(claimed)
        except RbdActionFenceLost:
            # The newer owner is responsible for reconciliation.
            return
        except RbdAgentClientError as exc:
            if exc.code in BUSY_CODES:
                self._fail_final(claimed, "VOLUME_BUSY", exc.message, "BUSY")
            elif exc.code in DEPENDENCY_CODES:
                self._fail_final(
                    claimed,
                    "DEPENDENCY_EXISTS",
                    exc.message,
                    "DELETE_BLOCKED_DEPENDENCY",
                )
            elif exc.code in FINAL_AGENT_CODES:
                self._fail_final(claimed, exc.code, exc.message)
            else:
                # Includes every timeout/transport/protocol ambiguity and unknown
                # command failure: observe before deciding whether to retry.
                self._mark_reconciling(claimed, exc.code, exc.message)
        except RbdActionStateError as exc:
            self._fail_final(claimed, "STATE_CONFLICT", str(exc))
        except CapacityRejected as exc:
            self._fail_retryable(claimed, exc.code, str(exc))
        except Exception as exc:
            self._mark_reconciling(claimed, "RBD_ACTION_AMBIGUOUS", str(exc))

    def _finish_reconcile_claim(
        self,
        claimed: ClaimedAction,
        confirmed_state: str,
        *,
        complete: bool,
        changes: dict[str, Any] | None = None,
    ) -> None:
        action = claimed.action
        volume = dict(claimed.volume)
        volume.update(changes or {})
        volume["observed_state"] = confirmed_state
        with connection() as conn:
            with conn.transaction():
                owned = conn.execute(
                    """
                    SELECT id FROM rbd_actions
                     WHERE id=%s AND state='RECONCILING' AND lease_owner=%s
                       AND lease_generation=%s AND volume_generation=%s
                     FOR UPDATE
                    """,
                    (
                        action["id"],
                        self.worker_id,
                        action["lease_generation"],
                        action["volume_generation"],
                    ),
                ).fetchone()
                if owned is None:
                    raise RbdActionFenceLost("Reconciliation claim was fenced")
                conn.execute(
                    """
                    UPDATE rbd_volumes
                       SET observed_state=%s,image_id=%s,feature_set=%s,
                           device=%s,device_major=%s,device_minor=%s,fs_uuid=%s,
                           mountpoint=%s,last_error=NULL,updated_at=now(),
                           deleted_at=CASE WHEN %s='DELETED' THEN now() ELSE deleted_at END
                     WHERE id=%s AND transition_generation=%s
                    """,
                    (
                        confirmed_state,
                        volume.get("image_id"),
                        volume.get("feature_set") or [],
                        volume.get("device"),
                        volume.get("device_major"),
                        volume.get("device_minor"),
                        volume.get("fs_uuid"),
                        volume.get("mountpoint"),
                        confirmed_state,
                        volume["id"],
                        action["volume_generation"],
                    ),
                )
                if complete:
                    conn.execute(
                        """
                        UPDATE rbd_actions
                           SET state='SUCCEEDED',observed_state=%s,finished_at=now(),
                               redacted_result=%s::jsonb,error_code=NULL,error=NULL,
                               lease_owner=NULL,heartbeat_at=NULL,lease_expires_at=NULL
                         WHERE id=%s
                        """,
                        (
                            confirmed_state,
                            json.dumps(
                                {
                                    "volume_id": str(volume["id"]),
                                    "observed_state": confirmed_state,
                                    "reconciled": True,
                                }
                            ),
                            action["id"],
                        ),
                    )
                    if confirmed_state == "DELETED" and volume.get("capacity_reservation_id"):
                        conn.execute(
                            """
                            UPDATE capacity_reservations
                               SET state='SETTLING',remaining_commitment_bytes=0,
                                   settled_at=now(),updated_at=now()
                             WHERE id=%s AND state='PERSISTENT_COMMITMENT'
                            """,
                            (volume["capacity_reservation_id"],),
                        )
                else:
                    conn.execute(
                        """
                        UPDATE rbd_actions
                           SET state='PENDING',observed_state=%s,error_code=NULL,error=NULL,
                               lease_owner=NULL,heartbeat_at=NULL,lease_expires_at=NULL
                         WHERE id=%s
                        """,
                        (confirmed_state, action["id"]),
                    )

    def _release_reconcile_claim(self, claimed: ClaimedAction, code: str, message: str) -> None:
        action = claimed.action
        with connection() as conn:
            conn.execute(
                """
                UPDATE rbd_actions
                   SET error_code=%s,error=%s,lease_owner=NULL,
                       heartbeat_at=NULL,lease_expires_at=NULL
                 WHERE id=%s AND state='RECONCILING' AND lease_owner=%s
                   AND lease_generation=%s
                """,
                (
                    code,
                    message[:2000],
                    action["id"],
                    self.worker_id,
                    action["lease_generation"],
                ),
            )
            conn.commit()

    def reconcile(self, claimed: ClaimedAction) -> None:
        volume = claimed.volume
        action = claimed.action
        image: dict[str, Any] | None = None
        try:
            image = self.client.rbd_image_info(
                pool=volume["pool"],
                namespace=volume.get("namespace") or "",
                image_name=volume["image_name"],
            )
            self._validate_identity(image, volume)
        except RbdAgentClientError as exc:
            if exc.code not in {"IMAGE_NOT_FOUND", "NOT_FOUND", "ENOENT"}:
                self._release_reconcile_claim(claimed, exc.code, exc.message)
                return

        if image is None:
            if action["action_type"] == "DELETE":
                self._finish_reconcile_claim(claimed, "DELETED", complete=True)
                return
            if action["action_type"] == "CREATE" and action.get("current_step") == "rbd.image.create":
                prior = action.get("observed_state") or "REQUESTED"
                if prior == "RECONCILING":
                    prior = "REQUESTED"
                self._finish_reconcile_claim(claimed, prior, complete=False)
                return
            self._release_reconcile_claim(
                claimed,
                "STATE_CONFLICT",
                "The managed image is absent but the requested transition does not permit absence",
            )
            return

        image_id = image.get("image_id")
        if not isinstance(image_id, str) or not image_id:
            self._release_reconcile_claim(
                claimed, "AGENT_PROTOCOL_ERROR", "Image observation has no immutable image_id"
            )
            return
        if volume.get("image_id") and volume["image_id"] != image_id:
            self._release_reconcile_claim(
                claimed, "STATE_CONFLICT", "Observed image_id differs from the managed volume"
            )
            return

        if action["action_type"] == "CREATE" and action.get("current_step") == "rbd.image.create":
            # The image may exist while the host-agent's durable registry still
            # contains an IN_PROGRESS create record. Re-enter the same create
            # step so the agent can observe and finalize that exact action ID;
            # skipping directly to map would leave the identity registry
            # permanently incomplete.
            prior = action.get("observed_state") or (
                "CAPACITY_RESERVED" if volume.get("capacity_reservation_id") else "REQUESTED"
            )
            if prior == "RECONCILING":
                prior = (
                    "CAPACITY_RESERVED"
                    if volume.get("capacity_reservation_id")
                    else "REQUESTED"
                )
            self._finish_reconcile_claim(
                claimed,
                prior,
                complete=False,
                changes={
                    "image_id": image_id,
                    "feature_set": image.get("features") or [],
                },
            )
            return

        try:
            devices_result = self.client.rbd_device_list()
        except RbdAgentClientError as exc:
            self._release_reconcile_claim(claimed, exc.code, exc.message)
            return
        device = next(
            (
                item
                for item in _items(devices_result, "devices")
                if item.get("pool") == volume["pool"]
                and (item.get("namespace") or "") == (volume.get("namespace") or "")
                and item.get("image_name") == volume["image_name"]
                and item.get("image_id") == image_id
            ),
            None,
        )
        changes: dict[str, Any] = {
            "image_id": image_id,
            "feature_set": image.get("features") or volume.get("feature_set") or [],
        }
        if device is None:
            changes.update(
                {"device": None, "device_major": None, "device_minor": None, "mountpoint": None}
            )
            confirmed = "UNMAPPED" if volume.get("fs_uuid") else "CREATED"
        else:
            changes.update(
                {
                    "device": device.get("device"),
                    "device_major": device.get("device_major"),
                    "device_minor": device.get("device_minor"),
                    "fs_uuid": device.get("fs_uuid") or volume.get("fs_uuid"),
                    "mountpoint": device.get("mountpoint"),
                }
            )
            mounted = bool(device.get("mounted")) or bool(device.get("mountpoint"))
            if mounted:
                confirmed = "READY"
            elif changes.get("fs_uuid"):
                confirmed = "UNMOUNTED"
            else:
                confirmed = "MAPPED"
        complete = confirmed == action["intended_state"]
        self._finish_reconcile_claim(
            claimed,
            confirmed,
            complete=complete,
            changes=changes,
        )

    def run_once(self) -> bool:
        self.quarantine_expired()
        reconciling = self.claim_reconciling()
        if reconciling is not None:
            self.reconcile(reconciling)
            return True
        pending = self.claim_pending()
        if pending is None:
            return False
        self.process(pending)
        return True
