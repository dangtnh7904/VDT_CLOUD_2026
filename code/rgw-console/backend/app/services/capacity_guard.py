from __future__ import annotations

import math
import threading
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from ..db import connection


INCREASING_OPERATIONS = {"PUT", "UPDATE", "RBD_CREATE", "RBD_FILE_WRITE"}
CLEANUP_OPERATIONS = {"DELETE_CLEANUP", "RBD_DELETE_CLEANUP"}
CAPACITY_CHARGED_OPERATIONS = INCREASING_OPERATIONS | CLEANUP_OPERATIONS
HEALTH_GATED_OPERATIONS = CAPACITY_CHARGED_OPERATIONS | {"RBD_FORMAT"}


@dataclass(frozen=True)
class CapacityDecision:
    id: str
    decision: str
    state: str
    reason: str
    retryable: bool
    snapshot_id: int | None
    osdmap_epoch: int | None
    participating_osds: list[int]
    most_full_osd: int | None
    most_full_ratio: float | None
    projected_ratios: dict[str, float]
    observe_only: bool
    reservation_id: str | None = None
    reservation_generation: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapacityRejected(RuntimeError):
    def __init__(self, decision: CapacityDecision, code: str, status_code: int):
        super().__init__(decision.reason)
        self.decision = decision
        self.code = code
        self.status_code = status_code


def _setting(name: str, default: Any) -> Any:
    return getattr(get_settings(), name, default)


def _load_control_and_snapshot(db_conn=None) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    manager = connection() if db_conn is None else nullcontext(db_conn)
    with manager as conn:
        control = conn.execute(
            "SELECT desired_state, reason FROM control_state WHERE id=true"
        ).fetchone()
        snapshot = conn.execute(
            """
            SELECT id, fsid, osdmap_epoch, captured_at, fresh, cluster_health_summary,
                   (SELECT max(success.captured_at)
                      FROM capacity_snapshots success
                     WHERE success.fresh=true) AS last_success_at
              FROM capacity_snapshots
             ORDER BY captured_at DESC, id DESC
             LIMIT 1
            """
        ).fetchone()
        osds: list[dict[str, Any]] = []
        if snapshot:
            osds = conn.execute(
                """
                SELECT osd_id, total_bytes, used_bytes, available_bytes, used_ratio,
                       is_up, is_in, host, device_class, scope_metadata
                  FROM capacity_osds
                 WHERE snapshot_id=%s
                 ORDER BY osd_id
                """,
                (snapshot["id"],),
            ).fetchall()
    return dict(control or {"desired_state": "NORMAL", "reason": None}), dict(snapshot) if snapshot else None, [dict(row) for row in osds]


def _physical_state(ratio: float | None) -> str:
    if ratio is None:
        return "BLOCKED_TELEMETRY"
    if ratio >= float(_setting("capacity_hard_ceiling_ratio", 0.70)):
        return "EMERGENCY_CAPACITY"
    if ratio >= float(_setting("capacity_admission_stop_ratio", 0.68)):
        return "PAUSED_CAPACITY"
    if ratio >= float(_setting("capacity_throttle_start_ratio", 0.67)):
        return "THROTTLED"
    return "NORMAL"


def _persist_decision(
    decision: CapacityDecision,
    *,
    request_id: str | None,
    job_id: str | None,
    operation: str,
    expected_bytes: int,
    object_count: int,
    affected_pools: list[str] | None = None,
    db_conn=None,
) -> None:
    manager = connection() if db_conn is None else nullcontext(db_conn)
    with manager as conn:
        conn.execute(
            """
            INSERT INTO capacity_decisions (
              id, request_id, job_id, policy_version, snapshot_id, osdmap_epoch,
              state, reason, participating_osds, projected_ratios, decision, inputs
            ) VALUES (
              %s, %s, %s, 'default-70-v1', %s, %s, %s, %s, %s, %s::jsonb,
              %s, %s::jsonb
            )
            """,
            (
                decision.id,
                request_id,
                job_id,
                decision.snapshot_id,
                decision.osdmap_epoch,
                decision.state,
                decision.reason,
                decision.participating_osds,
                __import__("json").dumps(decision.projected_ratios),
                decision.decision,
                __import__("json").dumps(
                    {
                        "operation": operation,
                        "expected_bytes": expected_bytes,
                        "object_count": object_count,
                        "observe_only": decision.observe_only,
                        "affected_pools": sorted(
                            affected_pools
                            if affected_pools is not None
                            else (get_settings().rgw_affected_pool_set if not operation.startswith("RBD_") else [])
                        ),
                    }
                ),
            ),
        )
        if db_conn is None:
            conn.commit()


def decide(
    operation: str,
    expected_bytes: int = 0,
    *,
    request_id: str | None = None,
    job_id: str | None = None,
    persist: bool = True,
    affected_pools: list[str] | None = None,
    object_count: int = 1,
    _db_conn=None,
    _pending_by_osd: dict[int, int] | None = None,
) -> CapacityDecision:
    """Make a conservative per-OSD admission decision.

    Until the collector has produced a complete pool/CRUSH scope, enforcement mode
    fails closed. Observe-only mode records the same blocked state but allows the
    existing workload so that P2 can be calibrated safely.
    """

    operation = operation.upper()
    expected_bytes = max(0, int(expected_bytes))
    object_count = max(1, int(object_count))
    observe_only = bool(_setting("capacity_observe_only", True))
    strict_health = operation == "RBD_FORMAT" and bool(
        _setting("capacity_require_clean_for_rbd_format", True)
    )
    control, snapshot, osds = _load_control_and_snapshot(_db_conn)
    decision_id = str(uuid.uuid4())

    if control.get("desired_state") == "READ_CLEANUP_ONLY" and operation in INCREASING_OPERATIONS:
        result = CapacityDecision(
            decision_id,
            "BLOCK",
            "READ_CLEANUP_ONLY",
            control.get("reason") or "Emergency stop is active",
            False,
            snapshot.get("id") if snapshot else None,
            snapshot.get("osdmap_epoch") if snapshot else None,
            [int(row["osd_id"]) for row in osds],
            None,
            None,
            {},
            observe_only,
        )
        if persist:
            _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
        return result

    now = datetime.now(timezone.utc)
    max_age = float(_setting("capacity_metrics_max_age_seconds", 5))
    snapshot_fresh = False
    if snapshot:
        captured = snapshot["captured_at"]
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        age_seconds = (now - captured).total_seconds()
        snapshot_fresh = bool(snapshot.get("fresh")) and 0 <= age_seconds <= max_age

    expected_fsid = get_settings().ceph_expected_fsid
    if operation in HEALTH_GATED_OPERATIONS and (
        not expected_fsid or (snapshot and snapshot.get("fsid") != expected_fsid)
    ):
        allow = observe_only and not strict_health
        result = CapacityDecision(
            decision_id,
            "ADMIT" if allow else "BLOCK",
            "BLOCKED_UNKNOWN_CAPACITY",
            (
                "CEPH_EXPECTED_FSID is not configured"
                if not expected_fsid
                else "Capacity telemetry FSID does not match CEPH_EXPECTED_FSID"
            ) + ("; observe-only override" if allow else ""),
            not allow,
            snapshot.get("id") if snapshot else None,
            snapshot.get("osdmap_epoch") if snapshot else None,
            [int(row["osd_id"]) for row in osds],
            None,
            None,
            {},
            observe_only,
        )
        if persist:
            _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
        return result

    if not snapshot_fresh or not osds:
        allow = (observe_only and not strict_health) or operation not in HEALTH_GATED_OPERATIONS
        result = CapacityDecision(
            decision_id,
            "ADMIT" if allow else "BLOCK",
            "BLOCKED_TELEMETRY",
            "No fresh per-OSD capacity snapshot is available" + ("; observe-only override" if observe_only and allow else ""),
            not allow,
            snapshot.get("id") if snapshot else None,
            snapshot.get("osdmap_epoch") if snapshot else None,
            [int(row["osd_id"]) for row in osds],
            None,
            None,
            {},
            observe_only,
        )
        if persist:
            _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
        return result

    requested_pools = {pool for pool in (affected_pools or []) if pool}
    if operation in HEALTH_GATED_OPERATIONS:
        scoped_osds: list[dict[str, Any]] = []
        covered_pools: set[str] = set()
        scope_complete = bool(requested_pools)
        for row in osds:
            metadata = row.get("scope_metadata") or {}
            eligible_pools = {str(pool) for pool in metadata.get("eligible_pools", [])}
            if requested_pools & eligible_pools:
                scoped_osds.append(row)
                covered_pools.update(requested_pools & eligible_pools)
                pool_ids = metadata.get("pool_ids") or {}
                scope_complete = (
                    scope_complete
                    and bool(metadata.get("capacity_scope_complete"))
                    and all(str(pool) in pool_ids for pool in requested_pools & eligible_pools)
                )
        scope_complete = scope_complete and covered_pools == requested_pools and bool(scoped_osds)
        if not scope_complete:
            allow = observe_only and not strict_health
            result = CapacityDecision(
                decision_id,
                "ADMIT" if allow else "BLOCK",
                "BLOCKED_UNKNOWN_CAPACITY",
                "Affected pool to participating-OSD scope is incomplete" + ("; observe-only override" if allow else ""),
                not allow,
                int(snapshot["id"]),
                int(snapshot["osdmap_epoch"]),
                [int(row["osd_id"]) for row in scoped_osds],
                None,
                None,
                {},
                observe_only,
            )
            if persist:
                _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
            return result
        osds = scoped_osds

        summary = snapshot.get("cluster_health_summary") or {}
        health_pause = any(
            bool(summary.get(name))
            for name in (
                "degraded",
                "remapped",
                "recovering",
                "backfilling",
                "has_degraded_or_remapped_pgs",
                "has_recovery_or_backfill",
            )
        ) or any(not row.get("is_up") or not row.get("is_in") for row in osds)
        full_flag = any(
            bool((row.get("scope_metadata") or {}).get(name))
            for row in osds
            for name in ("full", "backfillfull")
        )
        manager = connection() if _db_conn is None else nullcontext(_db_conn)
        with manager as epoch_conn:
            epoch_rows = epoch_conn.execute(
                "SELECT osdmap_epoch FROM capacity_snapshots "
                "WHERE fsid=%s ORDER BY captured_at DESC,id DESC LIMIT 2",
                (snapshot["fsid"],),
            ).fetchall()
        epoch_changed = len(epoch_rows) > 1 and len({row["osdmap_epoch"] for row in epoch_rows}) > 1
        forced_state = None
        forced_reason = None
        if full_flag:
            forced_state = "EMERGENCY_CAPACITY"
            forced_reason = "A participating OSD is marked full or backfillfull"
        elif health_pause and bool(_setting("capacity_pause_on_degraded_or_remapped", True)):
            forced_state = "PAUSED_REMAP"
            forced_reason = "Relevant OSD/PG recovery, backfill, degraded, or remapped state is active"
        elif epoch_changed and bool(_setting("capacity_fail_closed_on_osdmap_change", True)):
            forced_state = "RECONCILING"
            forced_reason = "OSDMap epoch changed between the two newest capacity samples"
        if forced_state:
            allow = observe_only and not strict_health
            result = CapacityDecision(
                decision_id,
                "ADMIT" if allow else "BLOCK",
                forced_state,
                forced_reason + ("; observe-only override" if allow else ""),
                not allow,
                int(snapshot["id"]),
                int(snapshot["osdmap_epoch"]),
                [int(row["osd_id"]) for row in osds],
                None,
                None,
                {},
                observe_only,
            )
            if persist:
                _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
            return result

    overhead = float(_setting("capacity_raw_overhead_factor", 1.10))
    fixed_metadata_setting = _setting("capacity_fixed_metadata_bytes_per_object", None)
    margin_ratio = float(_setting("capacity_safety_margin_ratio_per_osd", 0.01))
    margin_min_setting = _setting("capacity_safety_margin_min_bytes_per_osd", None)
    maintenance_budget = _setting("capacity_emergency_maintenance_bytes", None)
    if operation in CLEANUP_OPERATIONS and maintenance_budget is None:
        allow = observe_only
        result = CapacityDecision(
            decision_id,
            "ADMIT" if allow else "BLOCK",
            "BLOCKED_UNKNOWN_CAPACITY",
            "Emergency maintenance metadata budget is not calibrated" + ("; observe-only override" if allow else ""),
            not allow,
            int(snapshot["id"]),
            int(snapshot["osdmap_epoch"]),
            [int(row["osd_id"]) for row in osds],
            None,
            None,
            {},
            observe_only,
        )
        if persist:
            _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
        return result
    if operation in CAPACITY_CHARGED_OPERATIONS and (fixed_metadata_setting is None or margin_min_setting is None):
        allow = observe_only
        missing = []
        if fixed_metadata_setting is None:
            missing.append("fixed metadata bytes per object")
        if margin_min_setting is None:
            missing.append("minimum safety margin bytes per OSD")
        result = CapacityDecision(
            decision_id,
            "ADMIT" if allow else "BLOCK",
            "BLOCKED_UNKNOWN_CAPACITY",
            "Required capacity calibration is unknown: " + ", ".join(missing) + ("; observe-only override" if allow else ""),
            not allow,
            int(snapshot["id"]),
            int(snapshot["osdmap_epoch"]),
            [int(row["osd_id"]) for row in osds],
            None,
            None,
            {},
            observe_only,
        )
        if persist:
            _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
        return result

    fixed_metadata = int(fixed_metadata_setting or 0)
    margin_min = int(margin_min_setting or 0)
    base_pool_charge = math.ceil(expected_bytes * overhead) + (fixed_metadata * object_count) if operation in CAPACITY_CHARGED_OPERATIONS else 0
    per_osd_charge = base_pool_charge * max(1, len(requested_pools))
    projected: dict[str, float] = {}
    for row in osds:
        total = int(row["total_bytes"] or 0)
        if total <= 0:
            continue
        margin = max(math.ceil(total * margin_ratio), margin_min)
        pending = int((_pending_by_osd or {}).get(int(row["osd_id"]), 0))
        projected[str(row["osd_id"])] = (int(row["used_bytes"] or 0) + pending + per_osd_charge + margin) / total

    ratios = [(int(row["osd_id"]), float(row["used_ratio"])) for row in osds if row.get("used_ratio") is not None]
    if operation in CAPACITY_CHARGED_OPERATIONS and (len(projected) != len(osds) or len(ratios) != len(osds)):
        allow = observe_only
        result = CapacityDecision(
            decision_id,
            "ADMIT" if allow else "BLOCK",
            "BLOCKED_UNKNOWN_CAPACITY",
            "One or more participating OSD telemetry rows are incomplete or invalid" + ("; observe-only override" if allow else ""),
            not allow,
            int(snapshot["id"]),
            int(snapshot["osdmap_epoch"]),
            [int(row["osd_id"]) for row in osds],
            None,
            None,
            projected,
            observe_only,
        )
        if persist:
            _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
        return result
    most_full_osd, most_full_ratio = max(ratios, key=lambda item: item[1]) if ratios else (None, None)
    worst_projected = max(projected.values(), default=most_full_ratio or 0.0)
    state = _physical_state(max(most_full_ratio or 0.0, worst_projected))
    threshold = float(
        _setting("capacity_hard_ceiling_ratio", 0.70)
        if operation in CLEANUP_OPERATIONS
        else _setting("capacity_admission_stop_ratio", 0.68)
    )
    over_budget = operation in CLEANUP_OPERATIONS and per_osd_charge > int(maintenance_budget or 0)
    blocked = operation in CAPACITY_CHARGED_OPERATIONS and (worst_projected >= threshold or over_budget)
    allow = not blocked or observe_only
    reason = (
        f"Projected most-full participating OSD ratio {worst_projected:.4f} "
        f"is {'above' if worst_projected >= threshold else 'below'} threshold {threshold:.4f}"
    )
    if over_budget:
        reason += "; cleanup metadata charge exceeds maintenance budget"
    if blocked and observe_only:
        reason += "; observe-only override"
    result = CapacityDecision(
        decision_id,
        "ADMIT" if allow else "BLOCK",
        state,
        reason,
        blocked and not observe_only,
        int(snapshot["id"]),
        int(snapshot["osdmap_epoch"]),
        [int(row["osd_id"]) for row in osds],
        most_full_osd,
        most_full_ratio,
        projected,
        observe_only,
    )
    if persist:
        _persist_decision(result, request_id=request_id, job_id=job_id, operation=operation, expected_bytes=expected_bytes, object_count=object_count, affected_pools=affected_pools, db_conn=_db_conn)
    return result


def require_admission(
    operation: str,
    expected_bytes: int = 0,
    *,
    request_id: str | None = None,
    job_id: str | None = None,
    affected_pools: list[str] | None = None,
    object_count: int = 1,
) -> CapacityDecision:
    operation = operation.upper()
    if affected_pools is None and not operation.startswith("RBD_"):
        affected_pools = sorted(get_settings().rgw_affected_pool_set)
    affected_pools = sorted({pool for pool in (affected_pools or []) if pool})
    observe_only = bool(_setting("capacity_observe_only", True))

    if operation not in CAPACITY_CHARGED_OPERATIONS or observe_only:
        result = decide(
            operation,
            expected_bytes,
            request_id=request_id,
            job_id=job_id,
            affected_pools=affected_pools,
            object_count=object_count,
        )
    else:
        with connection() as conn:
            with conn.transaction():
                latest = conn.execute(
                    "SELECT fsid,osdmap_epoch FROM capacity_snapshots ORDER BY captured_at DESC,id DESC LIMIT 1"
                ).fetchone()
                lock_scope = latest["fsid"] if latest else "capacity:no-snapshot"
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (lock_scope,))
                conn.execute(
                    """
                    UPDATE capacity_reservations
                       SET state='LEASE_EXPIRED_UNRECONCILED',updated_at=now()
                     WHERE state IN ('PENDING','IN_FLIGHT')
                       AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
                    """
                )
                pending_rows = conn.execute(
                    """
                    SELECT allocation.osd_id,coalesce(sum(allocation.estimated_bytes),0) AS pending_bytes
                      FROM capacity_reservation_allocations allocation
                      JOIN capacity_reservations reservation ON reservation.id=allocation.reservation_id
                     WHERE reservation.state IN (
                       'PENDING','IN_FLIGHT','SETTLING','PERSISTENT_COMMITMENT',
                       'LEASE_EXPIRED_UNRECONCILED'
                     )
                       AND (%s::text IS NULL OR reservation.fsid=%s)
                     GROUP BY allocation.osd_id
                    """,
                    (latest["fsid"] if latest else None, latest["fsid"] if latest else None),
                ).fetchall()
                pending_by_osd = {int(row["osd_id"]): int(row["pending_bytes"]) for row in pending_rows}
                result = decide(
                    operation,
                    expected_bytes,
                    request_id=request_id,
                    job_id=job_id,
                    persist=False,
                    affected_pools=affected_pools,
                    object_count=object_count,
                    _db_conn=conn,
                    _pending_by_osd=pending_by_osd,
                )
                _persist_decision(
                    result,
                    request_id=request_id,
                    job_id=job_id,
                    operation=operation,
                    expected_bytes=expected_bytes,
                    object_count=object_count,
                    affected_pools=affected_pools,
                    db_conn=conn,
                )
                if result.decision == "ADMIT" and latest:
                    reservation_id = str(uuid.uuid4())
                    fixed_metadata = int(_setting("capacity_fixed_metadata_bytes_per_object", 0) or 0)
                    overhead = float(_setting("capacity_raw_overhead_factor", 1.10))
                    base_pool_charge = math.ceil(max(0, int(expected_bytes)) * overhead) + (fixed_metadata * max(1, int(object_count)))
                    snapshot_osds = conn.execute(
                        "SELECT osd_id,scope_metadata FROM capacity_osds WHERE snapshot_id=%s AND osd_id=ANY(%s)",
                        (result.snapshot_id, result.participating_osds),
                    ).fetchall()
                    allocations: list[tuple[int, str, int, int]] = []
                    for row in snapshot_osds:
                        metadata = row["scope_metadata"] or {}
                        eligible = {str(pool) for pool in metadata.get("eligible_pools", [])}
                        pool_ids = metadata.get("pool_ids") or {}
                        for pool_name in affected_pools:
                            if pool_name in eligible:
                                allocations.append((int(pool_ids[pool_name]), pool_name, int(row["osd_id"]), base_pool_charge))
                    if not allocations:
                        raise RuntimeError("capacity scope produced no reservation allocations")
                    raw_total = sum(item[3] for item in allocations)
                    owner_type = "JOB" if job_id else "REQUEST"
                    owner_id = job_id or request_id or result.id
                    conn.execute(
                        """
                        INSERT INTO capacity_reservations (
                          id,decision_id,owner_type,owner_id,fsid,osdmap_epoch,
                          affected_pools,logical_bytes,estimated_raw_bytes,
                          remaining_commitment_bytes,reservation_class,state,
                          lease_owner,lease_generation,heartbeat_at,lease_expires_at
                        ) VALUES (
                          %s,%s,%s,%s,%s,%s,%s,%s,%s,0,'TRANSIENT_OPERATION','PENDING',
                          %s,1,now(),now() + (%s * interval '1 second')
                        )
                        """,
                        (
                            reservation_id,result.id,owner_type,owner_id,latest["fsid"],
                            latest["osdmap_epoch"],affected_pools,max(0,int(expected_bytes)),
                            raw_total,owner_id,int(_setting("capacity_operation_lease_seconds",30)),
                        ),
                    )
                    for pool_id,pool_name,osd_id,estimated in allocations:
                        conn.execute(
                            """
                            INSERT INTO capacity_reservation_allocations (
                              reservation_id,pool_id,pool_name,osd_id,estimated_bytes
                            ) VALUES (%s,%s,%s,%s,%s)
                            """,
                            (reservation_id,pool_id,pool_name,osd_id,estimated),
                        )
                    result = replace(result, reservation_id=reservation_id, reservation_generation=1)
    if result.decision == "BLOCK":
        code = "TELEMETRY_STALE" if result.state == "BLOCKED_TELEMETRY" else "CAPACITY_LIMIT"
        status = 503 if code == "TELEMETRY_STALE" else 409
        raise CapacityRejected(result, code, status)
    return result


def require_cleanup_admission(
    *,
    request_id: str | None = None,
    job_id: str | None = None,
    object_count: int = 1,
) -> CapacityDecision:
    return require_admission("DELETE_CLEANUP", object_count, request_id=request_id, job_id=job_id, object_count=object_count)


@contextmanager
def reservation_lease(decision: CapacityDecision):
    """Fence and heartbeat a transient reservation while a mutation is in flight."""

    if not decision.reservation_id:
        yield
        return

    generation = int(decision.reservation_generation or 1)
    lease_seconds = int(_setting("capacity_operation_lease_seconds", 30))
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE capacity_reservations
               SET state='IN_FLIGHT',heartbeat_at=now(),
                   lease_expires_at=now() + (%s * interval '1 second'),updated_at=now()
             WHERE id=%s AND lease_generation=%s AND state='PENDING'
            RETURNING id
            """,
            (lease_seconds, decision.reservation_id, generation),
        ).fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("capacity reservation could not enter its fenced in-flight state")

    stop = threading.Event()
    lost = threading.Event()

    def heartbeat() -> None:
        interval = max(0.25, lease_seconds / 3)
        while not stop.wait(interval):
            try:
                with connection() as conn:
                    renewed = conn.execute(
                        """
                        UPDATE capacity_reservations
                           SET heartbeat_at=now(),
                               lease_expires_at=now() + (%s * interval '1 second'),
                               updated_at=now()
                         WHERE id=%s AND lease_generation=%s AND state='IN_FLIGHT'
                        RETURNING id
                        """,
                        (lease_seconds, decision.reservation_id, generation),
                    ).fetchone()
                    conn.commit()
                if not renewed:
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    thread = threading.Thread(
        target=heartbeat,
        name=f"capacity-reservation-{decision.reservation_id}",
        daemon=True,
    )
    thread.start()
    try:
        yield
        if lost.is_set():
            raise RuntimeError("capacity reservation heartbeat/fencing was lost")
    finally:
        stop.set()
        thread.join(timeout=2)


def finish_reservation(decision: CapacityDecision, outcome: str) -> None:
    """Transition a reservation without ever crediting delete/write bytes early."""
    if not decision.reservation_id:
        return
    states = {
        "success": "SETTLING",
        "not_started": "RELEASED",
        "ambiguous": "LEASE_EXPIRED_UNRECONCILED",
    }
    if outcome not in states:
        raise ValueError("unknown reservation outcome")
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE capacity_reservations
               SET state=%s,updated_at=now(),
                   settled_at=CASE WHEN %s='SETTLING' THEN now() ELSE settled_at END,
                   released_at=CASE WHEN %s='RELEASED' THEN now() ELSE released_at END
             WHERE id=%s AND lease_generation=%s AND state IN ('PENDING','IN_FLIGHT')
             RETURNING id
            """,
            (
                states[outcome],states[outcome],states[outcome],decision.reservation_id,
                int(decision.reservation_generation or 1),
            ),
        ).fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("capacity reservation outcome lost its fencing state")


def snapshot_response(*, scope_type: str | None = None, scope: str | None = None) -> dict[str, Any]:
    control, snapshot, osds = _load_control_and_snapshot()
    if scope_type == "pool" and scope:
        osds = [
            row
            for row in osds
            if scope in {str(pool) for pool in (row.get("scope_metadata") or {}).get("eligible_pools", [])}
        ]
    if not snapshot:
        configured = bool(
            _setting("ceph_expected_fsid", None)
            and _setting("rbd_executor_url", None)
            and _setting("rbd_executor_token", None)
        )
        telemetry_status = "NO_SNAPSHOT" if configured else "NOT_CONFIGURED"
        return {
            "fsid": None,
            "osdmap_epoch": None,
            "captured_at": None,
            "fresh": False,
            "policy": {
                "hard_ceiling_ratio": float(_setting("capacity_hard_ceiling_ratio", 0.70)),
                "admission_stop_ratio": float(_setting("capacity_admission_stop_ratio", 0.68)),
                "resume_ratio": float(_setting("capacity_resume_ratio", 0.67)),
            },
            "state": "READ_CLEANUP_ONLY" if control.get("desired_state") == "READ_CLEANUP_ONLY" else "BLOCKED_TELEMETRY",
            "most_full_osd": None,
            "most_full_ratio": None,
            "participating_osds": [],
            "pending_unobserved_raw_bytes": 0,
            "remaining_persistent_commitment_raw_bytes": 0,
            "contract": "OBSERVE_ONLY" if _setting("capacity_observe_only", True) else "NO_FRESH_EVIDENCE",
            "reasons": [control.get("reason") or "No capacity snapshot has been collected"],
            "telemetry": {
                "status": telemetry_status,
                "source": "node-ssh",
                "age_seconds": None,
                "last_success_at": None,
                "error_code": None if configured else "EXECUTOR_NOT_CONFIGURED",
                "osd_scope": [],
                "pool_scope": sorted(
                    _setting("rgw_affected_pool_set", frozenset())
                    | _setting("rbd_allowed_pool_set", frozenset())
                ),
            },
            "scope_type": scope_type,
            "scope": scope,
        }

    now = datetime.now(timezone.utc)
    captured = snapshot["captured_at"]
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    age_seconds = (now - captured).total_seconds()
    fresh = bool(snapshot.get("fresh")) and 0 <= age_seconds <= float(_setting("capacity_metrics_max_age_seconds", 5))
    summary = snapshot.get("cluster_health_summary") or {}
    error_code = summary.get("collector_error_code")
    if fresh:
        telemetry_status = "FRESH"
    elif error_code and str(error_code).startswith("EXECUTOR_"):
        telemetry_status = "EXECUTOR_UNAVAILABLE"
    elif error_code:
        telemetry_status = "COLLECTOR_ERROR"
    else:
        telemetry_status = "STALE"
    last_success_at = snapshot.get("last_success_at")
    if last_success_at is not None and last_success_at.tzinfo is None:
        last_success_at = last_success_at.replace(tzinfo=timezone.utc)
    telemetry_age = (
        max(0.0, (now - last_success_at).total_seconds())
        if last_success_at is not None
        else age_seconds
    )
    ratios = [(int(row["osd_id"]), float(row["used_ratio"])) for row in osds if row.get("used_ratio") is not None]
    most_full_osd, most_full_ratio = max(ratios, key=lambda item: item[1]) if ratios else (None, None)
    state = _physical_state(most_full_ratio) if fresh else "BLOCKED_TELEMETRY"
    if fresh and scope_type == "pool" and scope and not osds:
        state = "BLOCKED_UNKNOWN_CAPACITY"
    if control.get("desired_state") == "READ_CLEANUP_ONLY":
        state = "READ_CLEANUP_ONLY"
    with connection() as conn:
        conn.execute(
            """
            UPDATE capacity_reservations
               SET state='LEASE_EXPIRED_UNRECONCILED',updated_at=now()
             WHERE state IN ('PENDING','IN_FLIGHT')
               AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
            """
        )
        if scope_type == "pool" and scope:
            reservation = conn.execute(
                """
                SELECT
                  coalesce(sum(allocation.estimated_bytes) FILTER (
                    WHERE reservation.state IN ('PENDING','IN_FLIGHT','SETTLING','LEASE_EXPIRED_UNRECONCILED')
                  ),0) AS pending,
                  coalesce(sum(allocation.estimated_bytes) FILTER (
                    WHERE reservation.state IN ('PERSISTENT_COMMITMENT','LEASE_EXPIRED_UNRECONCILED')
                  ),0) AS commitment
                  FROM capacity_reservation_allocations allocation
                  JOIN capacity_reservations reservation ON reservation.id=allocation.reservation_id
                 WHERE reservation.fsid=%s AND allocation.pool_name=%s
                """,
                (snapshot["fsid"], scope),
            ).fetchone()
        else:
            reservation = conn.execute(
                """
                SELECT
                  coalesce(sum(estimated_raw_bytes) FILTER (
                    WHERE state IN ('PENDING','IN_FLIGHT','SETTLING','LEASE_EXPIRED_UNRECONCILED')
                  ),0) AS pending,
                  coalesce(sum(remaining_commitment_bytes) FILTER (
                    WHERE state IN ('PERSISTENT_COMMITMENT','LEASE_EXPIRED_UNRECONCILED')
                  ),0) AS commitment
                  FROM capacity_reservations
                 WHERE fsid=%s
                """,
                (snapshot["fsid"],),
            ).fetchone()
        conn.commit()
    return {
        "fsid": snapshot.get("fsid"),
        "osdmap_epoch": snapshot.get("osdmap_epoch"),
        "captured_at": snapshot["captured_at"].isoformat(),
        "fresh": fresh,
        "policy": {
            "hard_ceiling_ratio": float(_setting("capacity_hard_ceiling_ratio", 0.70)),
            "admission_stop_ratio": float(_setting("capacity_admission_stop_ratio", 0.68)),
            "resume_ratio": float(_setting("capacity_resume_ratio", 0.67)),
        },
        "state": state,
        "most_full_osd": most_full_osd,
        "most_full_ratio": most_full_ratio,
        "participating_osds": [int(row["osd_id"]) for row in osds],
        "pending_unobserved_raw_bytes": int(reservation["pending"]),
        "remaining_persistent_commitment_raw_bytes": int(reservation["commitment"]),
        "contract": "OBSERVE_ONLY" if _setting("capacity_observe_only", True) else "STABLE_EPOCH_CONTROLLED_WRITERS",
        "reasons": (
            [control.get("reason")]
            if control.get("reason")
            else (
                [f"No participating OSD scope is known for pool {scope}"]
                if fresh and scope_type == "pool" and scope and not osds
                else ([] if fresh else ["Capacity telemetry is stale"])
            )
        ),
        "telemetry": {
            "status": telemetry_status,
            "source": "node-ssh",
            "age_seconds": telemetry_age,
            "last_success_at": last_success_at.isoformat() if last_success_at else None,
            "error_code": error_code,
            "osd_scope": [int(row["osd_id"]) for row in osds],
            "pool_scope": sorted(
                {
                    str(pool)
                    for row in osds
                    for pool in (row.get("scope_metadata") or {}).get("eligible_pools", [])
                }
            ),
        },
        "scope_type": scope_type,
        "scope": scope,
    }
