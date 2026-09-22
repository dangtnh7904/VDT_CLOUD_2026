from __future__ import annotations

import json
import math
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Collection, Mapping, Sequence
from uuid import UUID

from ..config import get_settings
from ..db import connection
from .rbd_agent_client import RbdAgentClient, RbdAgentClientError


COLLECTOR_VERSION = "pacific-v1"
_KIB = 1024


class CapacityTelemetryError(ValueError):
    """Ceph returned telemetry that is unsafe to use for admission."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True)
class CapacityOsdSample:
    osd_id: int
    total_bytes: int
    used_bytes: int
    available_bytes: int
    used_ratio: float
    is_up: bool
    is_in: bool
    host: str | None
    device_class: str | None
    scope_metadata: dict[str, Any]


@dataclass(frozen=True)
class CapacityInventory:
    fsid: str
    osdmap_epoch: int
    captured_at: datetime
    fresh: bool
    cluster_health_summary: dict[str, Any]
    osds: tuple[CapacityOsdSample, ...]


def _error(code: str, message: str, **details: Any) -> CapacityTelemetryError:
    return CapacityTelemetryError(code, message, details=details)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("INVALID_CEPH_OUTPUT", f"{path} must be a JSON object", path=path)
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error("INVALID_CEPH_OUTPUT", f"{path} must be a JSON array", path=path)
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _error(
            "INVALID_CEPH_OUTPUT",
            f"{path} must be an integer greater than or equal to {minimum}",
            path=path,
        )
    return value


def _number(value: Any, path: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error("INVALID_CEPH_OUTPUT", f"{path} must be numeric", path=path)
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise _error("INVALID_CEPH_OUTPUT", f"{path} is outside its valid range", path=path)
    return result


def _text(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise _error("INVALID_CEPH_OUTPUT", f"{path} must be a non-empty string", path=path)
    return value.strip()


def _normalize_fsid(value: Any, path: str = "fsid") -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise _error("INVALID_CEPH_OUTPUT", f"{path} must be a UUID", path=path) from exc


def _aware_datetime(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        raise _error("INVALID_CEPH_OUTPUT", f"{path} must be an ISO-8601 timestamp", path=path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error("INVALID_CEPH_OUTPUT", f"{path} must be an ISO-8601 timestamp", path=path) from exc
    if parsed.tzinfo is None:
        raise _error("INVALID_CEPH_OUTPUT", f"{path} must include a timezone", path=path)
    return parsed.astimezone(timezone.utc)


def _status_osdmap(status: Mapping[str, Any]) -> Mapping[str, Any]:
    osdmap = _mapping(status.get("osdmap"), "status.osdmap")
    # Some Pacific point releases wrap the actual map summary one level deeper.
    if "epoch" not in osdmap and isinstance(osdmap.get("osdmap"), Mapping):
        osdmap = _mapping(osdmap["osdmap"], "status.osdmap.osdmap")
    return osdmap


def _status_epoch(status: Mapping[str, Any]) -> int:
    return _integer(_status_osdmap(status).get("epoch"), "status.osdmap.epoch")


def _bool_or_positive_count(osdmap: Mapping[str, Any], names: Sequence[str]) -> bool:
    for name in names:
        value = osdmap.get(name)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return True
    return False


def _health_summary(status: Mapping[str, Any]) -> dict[str, Any]:
    health = _mapping(status.get("health"), "status.health")
    health_status = _text(health.get("status"), "status.health.status")
    checks_value = health.get("checks", {})
    checks = _mapping(checks_value, "status.health.checks")
    check_names = sorted(str(name) for name in checks)

    pgmap = _mapping(status.get("pgmap"), "status.pgmap")
    states = _list(pgmap.get("pgs_by_state"), "status.pgmap.pgs_by_state")
    pg_states: dict[str, int] = {}
    for index, raw_state in enumerate(states):
        state = _mapping(raw_state, f"status.pgmap.pgs_by_state[{index}]")
        name = _text(state.get("state_name"), f"status.pgmap.pgs_by_state[{index}].state_name")
        count = _integer(state.get("count"), f"status.pgmap.pgs_by_state[{index}].count")
        if name in pg_states:
            raise _error("INVALID_CEPH_OUTPUT", "duplicate PG state in status output", state=name)
        pg_states[name] = count

    state_tokens = {
        token
        for state_name, count in pg_states.items()
        if count > 0
        for token in state_name.lower().split("+")
    }
    degraded_tokens = {"degraded", "undersized", "incomplete", "stale", "peering"}
    degraded = bool(state_tokens & degraded_tokens)
    remapped = "remapped" in state_tokens
    recovering = any("recover" in token for token in state_tokens)
    backfilling = any("backfill" in token for token in state_tokens)

    osdmap = _status_osdmap(status)
    check_upper = {name.upper() for name in check_names}
    full = _bool_or_positive_count(osdmap, ("full", "num_full_osds")) or any(
        name == "OSD_FULL" or name.endswith("_FULL") for name in check_upper
    )
    backfillfull = _bool_or_positive_count(
        osdmap, ("backfillfull", "num_backfillfull_osds")
    ) or any("BACKFILLFULL" in name for name in check_upper)
    nearfull = _bool_or_positive_count(osdmap, ("nearfull", "num_nearfull_osds")) or any(
        "NEARFULL" in name for name in check_upper
    )

    return {
        "status": health_status,
        "checks": check_names,
        "pg_states": pg_states,
        "degraded": degraded,
        "remapped": remapped,
        "recovering": recovering,
        "backfilling": backfilling,
        "has_degraded_or_remapped_pgs": degraded or remapped,
        "has_recovery_or_backfill": recovering or backfilling,
        "full": full,
        "backfillfull": backfillfull,
        "nearfull": nearfull,
    }


@dataclass(frozen=True)
class _TreeIndex:
    nodes: dict[int, Mapping[str, Any]]
    names: dict[str, int]
    parents: dict[int, set[int]]

    def descendants(self, node_id: int) -> set[int]:
        if node_id not in self.nodes:
            raise _error("UNKNOWN_CRUSH_ITEM", "CRUSH rule references an unknown tree item", item=node_id)
        found: set[int] = set()
        visiting: set[int] = set()

        def visit(current: int) -> None:
            if current in visiting:
                raise _error("INVALID_CEPH_OUTPUT", "OSD tree contains a cycle", item=current)
            node = self.nodes[current]
            if node.get("type") == "osd" or current >= 0:
                found.add(current)
                return
            visiting.add(current)
            children = _list(node.get("children", []), f"osd_tree.node[{current}].children")
            for child in children:
                visit(_integer(child, f"osd_tree.node[{current}].children[]", minimum=-2**31))
            visiting.remove(current)

        visit(node_id)
        return found

    def host_for(self, osd_id: int) -> str | None:
        queue = list(self.parents.get(osd_id, set()))
        visited: set[int] = set()
        hosts: set[str] = set()
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            node = self.nodes[current]
            if node.get("type") == "host":
                hosts.add(_text(node.get("name"), f"osd_tree.node[{current}].name"))
            queue.extend(self.parents.get(current, set()))
        if len(hosts) > 1:
            raise _error("INVALID_CEPH_OUTPUT", "OSD belongs to multiple hosts", osd_id=osd_id)
        return next(iter(hosts), None)


def _parse_tree(osd_tree: Mapping[str, Any]) -> _TreeIndex:
    raw_nodes = _list(osd_tree.get("nodes"), "osd_tree.nodes")
    nodes: dict[int, Mapping[str, Any]] = {}
    names: dict[str, int] = {}
    for index, raw_node in enumerate(raw_nodes):
        node = _mapping(raw_node, f"osd_tree.nodes[{index}]")
        node_id = _integer(node.get("id"), f"osd_tree.nodes[{index}].id", minimum=-2**31)
        name = _text(node.get("name"), f"osd_tree.nodes[{index}].name")
        node_type = _text(node.get("type"), f"osd_tree.nodes[{index}].type")
        if node_id in nodes or name in names:
            raise _error("INVALID_CEPH_OUTPUT", "OSD tree contains duplicate IDs or names", item=name)
        if node_id >= 0 and node_type != "osd":
            raise _error("INVALID_CEPH_OUTPUT", "non-negative OSD tree item is not an OSD", item=node_id)
        nodes[node_id] = node
        names[name] = node_id

    parents: dict[int, set[int]] = {}
    for parent_id, node in nodes.items():
        for raw_child in _list(node.get("children", []), f"osd_tree.node[{parent_id}].children"):
            child = _integer(raw_child, f"osd_tree.node[{parent_id}].children[]", minimum=-2**31)
            if child not in nodes:
                raise _error("INVALID_CEPH_OUTPUT", "OSD tree references an unknown child", item=child)
            parents.setdefault(child, set()).add(parent_id)
    return _TreeIndex(nodes=nodes, names=names, parents=parents)


def _parse_osds(
    status: Mapping[str, Any],
    osd_df: Mapping[str, Any],
    tree: _TreeIndex,
) -> list[dict[str, Any]]:
    raw_nodes = _list(osd_df.get("nodes"), "osd_df.nodes")
    parsed: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, raw_node in enumerate(raw_nodes):
        node = _mapping(raw_node, f"osd_df.nodes[{index}]")
        if node.get("type") not in (None, "osd"):
            raise _error("INVALID_CEPH_OUTPUT", "osd_df.nodes contains a non-OSD row", index=index)
        osd_id = _integer(node.get("id"), f"osd_df.nodes[{index}].id")
        if osd_id in seen:
            raise _error("INVALID_CEPH_OUTPUT", "osd_df contains a duplicate OSD", osd_id=osd_id)
        seen.add(osd_id)
        tree_node = tree.nodes.get(osd_id)
        if tree_node is None or tree_node.get("type") != "osd":
            raise _error("INVALID_CEPH_OUTPUT", "OSD is missing from the OSD tree", osd_id=osd_id)

        total_kib = _integer(node.get("kb"), f"osd_df.nodes[{index}].kb", minimum=1)
        used_kib = _integer(node.get("kb_used"), f"osd_df.nodes[{index}].kb_used")
        available_kib = _integer(node.get("kb_avail"), f"osd_df.nodes[{index}].kb_avail")
        if used_kib > total_kib or available_kib > total_kib or used_kib + available_kib > total_kib:
            raise _error("INVALID_CEPH_OUTPUT", "OSD byte counters are inconsistent", osd_id=osd_id)

        status_value = node.get("status", tree_node.get("status"))
        status_text = _text(status_value, f"osd_df.nodes[{index}].status").lower()
        if status_text not in {"up", "down"}:
            raise _error("INVALID_CEPH_OUTPUT", "OSD status must be up or down", osd_id=osd_id)
        tree_status = tree_node.get("status")
        if tree_status is not None and _text(tree_status, f"osd_tree.osd[{osd_id}].status").lower() != status_text:
            raise _error("INCONSISTENT_CEPH_OUTPUT", "OSD status differs between commands", osd_id=osd_id)

        reweight = _number(
            node.get("reweight", tree_node.get("reweight")),
            f"osd_df.nodes[{index}].reweight",
        )
        if reweight > 1.0:
            raise _error("INVALID_CEPH_OUTPUT", "OSD reweight is greater than one", osd_id=osd_id)

        df_class = node.get("device_class")
        tree_class = tree_node.get("device_class")
        if df_class is not None:
            df_class = _text(df_class, f"osd_df.nodes[{index}].device_class")
        if tree_class is not None:
            tree_class = _text(tree_class, f"osd_tree.osd[{osd_id}].device_class")
        if df_class and tree_class and df_class != tree_class:
            raise _error("INCONSISTENT_CEPH_OUTPUT", "OSD device class differs between commands", osd_id=osd_id)

        total_bytes = total_kib * _KIB
        used_bytes = used_kib * _KIB
        available_bytes = available_kib * _KIB
        ratio = used_bytes / total_bytes
        reported_utilization = node.get("utilization")
        if reported_utilization is not None:
            utilization = _number(reported_utilization, f"osd_df.nodes[{index}].utilization")
            if utilization > 100.0001 or abs(utilization / 100.0 - ratio) > 0.002:
                raise _error(
                    "INCONSISTENT_CEPH_OUTPUT",
                    "OSD utilization does not match its byte counters",
                    osd_id=osd_id,
                )

        parsed.append(
            {
                "osd_id": osd_id,
                "total_bytes": total_bytes,
                "used_bytes": used_bytes,
                "available_bytes": available_bytes,
                "used_ratio": ratio,
                "is_up": status_text == "up",
                "is_in": reweight > 0,
                "host": tree.host_for(osd_id),
                "device_class": df_class or tree_class,
            }
        )

    osdmap = _status_osdmap(status)
    expected_total = _integer(osdmap.get("num_osds"), "status.osdmap.num_osds")
    expected_up = _integer(osdmap.get("num_up_osds"), "status.osdmap.num_up_osds")
    expected_in = _integer(osdmap.get("num_in_osds"), "status.osdmap.num_in_osds")
    actual_up = sum(1 for row in parsed if row["is_up"])
    actual_in = sum(1 for row in parsed if row["is_in"])
    if (len(parsed), actual_up, actual_in) != (expected_total, expected_up, expected_in):
        raise _error(
            "INCONSISTENT_CEPH_OUTPUT",
            "OSD counts differ between ceph status and ceph osd df",
            expected=[expected_total, expected_up, expected_in],
            observed=[len(parsed), actual_up, actual_in],
        )
    if not parsed:
        raise _error("INVALID_CEPH_OUTPUT", "capacity telemetry contains no OSDs")
    return parsed


_KNOWN_RULE_OPS = frozenset(
    {
        "take",
        "emit",
        "choose_firstn",
        "choose_indep",
        "chooseleaf_firstn",
        "chooseleaf_indep",
        "set_choose_tries",
        "set_chooseleaf_tries",
        "set_choose_local_tries",
        "set_choose_local_fallback_tries",
        "set_chooseleaf_vary_r",
        "set_chooseleaf_stable",
        "set_msr_descents",
        "set_msr_collision_tries",
    }
)


def _rule_osds(rule: Mapping[str, Any], tree: _TreeIndex, osd_rows: Sequence[Mapping[str, Any]]) -> set[int]:
    steps = _list(rule.get("steps"), "crush_rule.steps")
    takes: list[tuple[int, str | None]] = []
    emitted = False
    for index, raw_step in enumerate(steps):
        step = _mapping(raw_step, f"crush_rule.steps[{index}]")
        op = _text(step.get("op"), f"crush_rule.steps[{index}].op")
        if op not in _KNOWN_RULE_OPS:
            raise _error("UNSUPPORTED_CRUSH_RULE", "CRUSH rule contains an unsupported operation", op=op)
        if op == "emit":
            emitted = True
        if op != "take":
            continue
        item_value = step.get("item")
        item_name_value = step.get("item_name")
        item_class = step.get("item_class", step.get("class"))
        item_name = item_name_value if isinstance(item_name_value, str) else None
        if item_class is not None:
            item_class = _text(item_class, f"crush_rule.steps[{index}].item_class")
        if item_name and "~" in item_name:
            base, shadow_class = item_name.rsplit("~", 1)
            item_name = base
            item_class = item_class or shadow_class
        item_id: int | None = None
        if isinstance(item_value, int) and not isinstance(item_value, bool) and item_value in tree.nodes:
            item_id = item_value
        elif item_name and item_name in tree.names:
            item_id = tree.names[item_name]
        if item_id is None:
            raise _error("UNKNOWN_CRUSH_ITEM", "CRUSH take step cannot be resolved", item=item_name_value)
        takes.append((item_id, item_class))

    if not takes or not emitted:
        raise _error("UNSUPPORTED_CRUSH_RULE", "CRUSH rule must contain take and emit steps")
    class_by_osd = {int(row["osd_id"]): row.get("device_class") for row in osd_rows}
    eligible: set[int] = set()
    for item_id, device_class in takes:
        candidates = tree.descendants(item_id)
        if device_class:
            if any(class_by_osd.get(osd_id) is None for osd_id in candidates):
                raise _error(
                    "UNKNOWN_DEVICE_CLASS",
                    "device-class CRUSH rule cannot be evaluated for every candidate OSD",
                    device_class=device_class,
                )
            candidates = {
                osd_id for osd_id in candidates if class_by_osd.get(osd_id) == device_class
            }
        eligible.update(candidates)
    if not eligible:
        raise _error("EMPTY_CRUSH_SCOPE", "CRUSH rule has no eligible OSDs")
    return eligible


def _pool_scopes(
    pool_details: Sequence[Any],
    crush_rules: Sequence[Any],
    tree: _TreeIndex,
    osd_rows: Sequence[Mapping[str, Any]],
    affected_pools: Collection[str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    pools_by_name: dict[str, Mapping[str, Any]] = {}
    for index, raw_pool in enumerate(pool_details):
        pool = _mapping(raw_pool, f"pool_details[{index}]")
        name = _text(pool.get("pool_name"), f"pool_details[{index}].pool_name")
        if name in pools_by_name:
            raise _error("INVALID_CEPH_OUTPUT", "duplicate pool name in pool inventory", pool=name)
        pools_by_name[name] = pool

    rules_by_id: dict[int, Mapping[str, Any]] = {}
    for index, raw_rule in enumerate(crush_rules):
        rule = _mapping(raw_rule, f"crush_rules[{index}]")
        rule_id = _integer(rule.get("rule_id"), f"crush_rules[{index}].rule_id")
        if rule_id in rules_by_id:
            raise _error("INVALID_CEPH_OUTPUT", "duplicate CRUSH rule ID", rule_id=rule_id)
        rules_by_id[rule_id] = rule

    scopes: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for pool_name in sorted(set(affected_pools)):
        pool = pools_by_name.get(pool_name)
        try:
            if pool is None:
                raise _error("UNKNOWN_POOL", "configured affected pool is absent", pool=pool_name)
            pool_id = _integer(pool.get("pool"), f"pool[{pool_name}].pool")
            pool_type = pool.get("type")
            type_name = pool.get("type_name")
            replicated = pool_type == 1 or type_name == "replicated" or pool_type == "replicated"
            if not replicated:
                raise _error(
                    "UNSUPPORTED_POOL_TYPE",
                    "erasure-coded or unknown affected pools are outside the MVP contract",
                    pool=pool_name,
                )
            size = _integer(pool.get("size"), f"pool[{pool_name}].size", minimum=1)
            rule_id = _integer(pool.get("crush_rule"), f"pool[{pool_name}].crush_rule")
            rule = rules_by_id.get(rule_id)
            if rule is None:
                raise _error("UNKNOWN_CRUSH_RULE", "pool references an unknown CRUSH rule", pool=pool_name)
            eligible = _rule_osds(rule, tree, osd_rows)
            if len(eligible) < size:
                raise _error(
                    "INSUFFICIENT_CRUSH_SCOPE",
                    "CRUSH scope has fewer OSDs than the replicated pool size",
                    pool=pool_name,
                )
            scopes[pool_name] = {
                "pool_id": pool_id,
                "size": size,
                "crush_rule_id": rule_id,
                "crush_rule_name": str(rule.get("rule_name") or rule_id),
                "eligible_osds": eligible,
            }
        except CapacityTelemetryError as exc:
            errors.append({"pool": pool_name, "code": exc.code})
    return scopes, errors


def parse_ceph_inventory(
    *,
    fsid: str,
    status_before: Mapping[str, Any],
    status_after: Mapping[str, Any],
    osd_df: Mapping[str, Any],
    osd_tree: Mapping[str, Any],
    pool_details: Sequence[Any],
    crush_rules: Sequence[Any],
    affected_pools: Collection[str],
    captured_at: datetime | None = None,
) -> CapacityInventory:
    """Parse a Pacific-compatible, read-only inventory into admission evidence.

    Invalid physical telemetry raises instead of substituting zero. Unknown pool
    or CRUSH scope remains visible in the snapshot but is marked incomplete so
    the capacity guard blocks that affected pool in enforcement mode.
    """

    normalized_fsid = _normalize_fsid(fsid)
    status_before = _mapping(status_before, "status_before")
    status_after = _mapping(status_after, "status_after")
    before_epoch = _status_epoch(status_before)
    after_epoch = _status_epoch(status_after)
    if before_epoch != after_epoch:
        raise _error(
            "OSDMAP_CHANGED_DURING_COLLECTION",
            "OSDMap epoch changed while capacity telemetry was collected",
            before=before_epoch,
            after=after_epoch,
        )

    for label, status in (("status_before", status_before), ("status_after", status_after)):
        status_fsid = status.get("fsid")
        if status_fsid is not None and _normalize_fsid(status_fsid, f"{label}.fsid") != normalized_fsid:
            raise _error("FSID_MISMATCH", "status output came from an unexpected cluster")

    tree = _parse_tree(_mapping(osd_tree, "osd_tree"))
    osd_rows = _parse_osds(status_after, _mapping(osd_df, "osd_df"), tree)
    summary = _health_summary(status_after)
    scopes, scope_errors = _pool_scopes(
        _list(list(pool_details), "pool_details"),
        _list(list(crush_rules), "crush_rules"),
        tree,
        osd_rows,
        affected_pools,
    )
    summary["affected_pools"] = sorted(set(affected_pools))
    summary["resolved_affected_pools"] = sorted(scopes)
    summary["capacity_scope_complete"] = set(scopes) == set(affected_pools) and bool(affected_pools)
    summary["scope_errors"] = scope_errors

    samples: list[CapacityOsdSample] = []
    for row in sorted(osd_rows, key=lambda item: int(item["osd_id"])):
        osd_id = int(row["osd_id"])
        eligible = sorted(name for name, scope in scopes.items() if osd_id in scope["eligible_osds"])
        pool_ids = {name: int(scopes[name]["pool_id"]) for name in eligible}
        metadata = {
            "eligible_pools": eligible,
            "pool_ids": pool_ids,
            "pool_replication_sizes": {name: int(scopes[name]["size"]) for name in eligible},
            "pool_crush_rules": {name: int(scopes[name]["crush_rule_id"]) for name in eligible},
            "capacity_scope_complete": bool(eligible),
            # A cluster-level full/backfillfull indication is conservatively
            # attached to every OSD because Pacific status does not identify a
            # reliable per-OSD set in this command bundle.
            "full": bool(summary["full"]),
            "backfillfull": bool(summary["backfillfull"]),
            "nearfull": bool(summary["nearfull"]),
        }
        samples.append(CapacityOsdSample(scope_metadata=metadata, **row))

    timestamp = captured_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("captured_at must include a timezone")
    return CapacityInventory(
        fsid=normalized_fsid,
        osdmap_epoch=after_epoch,
        captured_at=timestamp.astimezone(timezone.utc),
        fresh=True,
        cluster_health_summary=summary,
        osds=tuple(samples),
    )


def _unwrap_agent_result(
    result: Any,
    action: str,
    expected_fsid: str,
) -> tuple[Any, datetime]:
    envelope = _mapping(result, f"agent.{action}")
    observed_fsid = _normalize_fsid(envelope.get("fsid"), f"agent.{action}.fsid")
    if observed_fsid != expected_fsid:
        raise _error("FSID_MISMATCH", "host-agent responses came from different clusters")
    if envelope.get("action") != action:
        raise _error("AGENT_PROTOCOL_ERROR", "host-agent action does not match the request", action=action)
    if "data" not in envelope:
        raise _error("AGENT_PROTOCOL_ERROR", "host-agent inventory result has no data", action=action)
    collected_at = _aware_datetime(envelope.get("collected_at"), f"agent.{action}.collected_at")
    return envelope["data"], collected_at


def _safe_health_for_settlement(summary: Mapping[str, Any]) -> bool:
    unsafe = (
        "degraded",
        "remapped",
        "recovering",
        "backfilling",
        "has_degraded_or_remapped_pgs",
        "has_recovery_or_backfill",
        "full",
        "backfillfull",
    )
    return not any(bool(summary.get(name)) for name in unsafe)


def evaluate_settlement_evidence(
    reservation: Mapping[str, Any],
    samples: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    required_samples: int,
    minimum_seconds: float,
    maximum_age_seconds: float,
) -> tuple[bool, str]:
    """Evaluate conservative evidence for releasing one SETTLING charge."""

    settled_at = reservation.get("settled_at")
    if not isinstance(settled_at, datetime):
        return False, "reservation has no settlement timestamp"
    if settled_at.tzinfo is None:
        settled_at = settled_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    if now < settled_at or (now - settled_at).total_seconds() < minimum_seconds:
        return False, "minimum settlement window has not elapsed"
    if required_samples < 1 or len(samples) < required_samples:
        return False, "not enough post-operation samples"

    ordered = sorted(samples, key=lambda row: row["captured_at"], reverse=True)[:required_samples]
    expected_fsid = reservation.get("fsid")
    expected_epoch = reservation.get("osdmap_epoch")
    previous_time: datetime | None = None
    for sample in ordered:
        captured = sample.get("captured_at")
        if not isinstance(captured, datetime):
            return False, "sample has no valid timestamp"
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        if captured <= settled_at or captured > now:
            return False, "sample is not strictly post-operation"
        if not sample.get("fresh"):
            return False, "a consecutive sample is invalid"
        if sample.get("fsid") != expected_fsid or sample.get("osdmap_epoch") != expected_epoch:
            return False, "FSID or OSDMap epoch changed"
        if not sample.get("scope_complete"):
            return False, "reservation scope is incomplete in a sample"
        if not sample.get("health_safe"):
            return False, "cluster health is unsafe for settlement"
        if previous_time is None:
            age = (now - captured).total_seconds()
            if age < 0 or age > maximum_age_seconds:
                return False, "newest sample is stale"
        elif (previous_time - captured).total_seconds() > maximum_age_seconds:
            return False, "consecutive samples contain a telemetry gap"
        previous_time = captured
    return True, "fresh stable-epoch telemetry covers the full reservation scope"


def _scope_complete_for_reservation(conn: Any, reservation_id: str, snapshot_id: int) -> bool:
    rows = conn.execute(
        """
        SELECT allocation.osd_id, allocation.pool_id, allocation.pool_name,
               osd.is_up, osd.is_in, osd.scope_metadata
          FROM capacity_reservation_allocations allocation
          LEFT JOIN capacity_osds osd
            ON osd.snapshot_id=%s AND osd.osd_id=allocation.osd_id
         WHERE allocation.reservation_id=%s
         ORDER BY allocation.pool_id,allocation.osd_id
        """,
        (snapshot_id, reservation_id),
    ).fetchall()
    if not rows:
        return False
    for row in rows:
        if row["is_up"] is not True or row["is_in"] is not True:
            return False
        metadata = row.get("scope_metadata") or {}
        if not metadata.get("capacity_scope_complete"):
            return False
        pool_name = str(row["pool_name"])
        if pool_name not in {str(item) for item in metadata.get("eligible_pools", [])}:
            return False
        pool_ids = metadata.get("pool_ids") or {}
        try:
            if int(pool_ids.get(pool_name)) != int(row["pool_id"]):
                return False
        except (TypeError, ValueError):
            return False
    return True


def reconcile_settling_reservations(
    conn: Any,
    fsid: str,
    *,
    now: datetime | None = None,
    required_samples: int | None = None,
    minimum_seconds: float | None = None,
    maximum_age_seconds: float | None = None,
) -> list[str]:
    """Release only SETTLING transient reservations with complete evidence.

    Ambiguous/expired and persistent reservations are deliberately untouched.
    The caller must hold the FSID advisory transaction lock used by admission.
    """

    settings = get_settings()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    required = required_samples or settings.capacity_settlement_consecutive_samples
    minimum = (
        settings.capacity_settlement_min_seconds if minimum_seconds is None else minimum_seconds
    )
    maximum_age = (
        settings.capacity_metrics_max_age_seconds
        if maximum_age_seconds is None
        else maximum_age_seconds
    )
    reservations = conn.execute(
        """
        SELECT id,fsid,osdmap_epoch,settled_at
          FROM capacity_reservations
         WHERE fsid=%s AND state='SETTLING'
           AND reservation_class='TRANSIENT_OPERATION'
         ORDER BY settled_at,id
         FOR UPDATE
        """,
        (fsid,),
    ).fetchall()
    released: list[str] = []
    for reservation_row in reservations:
        reservation = dict(reservation_row)
        snapshots = conn.execute(
            """
            SELECT id,fsid,osdmap_epoch,captured_at,fresh,cluster_health_summary
              FROM capacity_snapshots
             WHERE captured_at > %s
             ORDER BY captured_at DESC,id DESC
             LIMIT %s
            """,
            (reservation["settled_at"], required),
        ).fetchall()
        evidence: list[dict[str, Any]] = []
        for snapshot_row in snapshots:
            snapshot = dict(snapshot_row)
            evidence.append(
                {
                    **snapshot,
                    "scope_complete": _scope_complete_for_reservation(
                        conn, str(reservation["id"]), int(snapshot["id"])
                    ),
                    "health_safe": _safe_health_for_settlement(
                        snapshot.get("cluster_health_summary") or {}
                    ),
                }
            )
        sufficient, _ = evaluate_settlement_evidence(
            reservation,
            evidence,
            now=now,
            required_samples=required,
            minimum_seconds=minimum,
            maximum_age_seconds=maximum_age,
        )
        if not sufficient:
            continue
        updated = conn.execute(
            """
            UPDATE capacity_reservations
               SET state='RELEASED',released_at=%s,updated_at=%s
             WHERE id=%s AND state='SETTLING'
            RETURNING id
            """,
            (now, now, reservation["id"]),
        ).fetchone()
        if updated:
            released.append(str(updated["id"]))
    return released


def store_capacity_inventory(inventory: CapacityInventory, *, db_conn: Any | None = None) -> dict[str, Any]:
    manager = connection() if db_conn is None else nullcontext(db_conn)
    with manager as conn:
        with conn.transaction():
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (inventory.fsid,),
            )
            snapshot = conn.execute(
                """
                INSERT INTO capacity_snapshots (
                  fsid,osdmap_epoch,captured_at,collector_version,fresh,cluster_health_summary
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                RETURNING id
                """,
                (
                    inventory.fsid,
                    inventory.osdmap_epoch,
                    inventory.captured_at,
                    COLLECTOR_VERSION,
                    inventory.fresh,
                    json.dumps(inventory.cluster_health_summary, separators=(",", ":")),
                ),
            ).fetchone()
            snapshot_id = int(snapshot["id"])
            for row in inventory.osds:
                conn.execute(
                    """
                    INSERT INTO capacity_osds (
                      snapshot_id,osd_id,total_bytes,used_bytes,available_bytes,used_ratio,
                      is_up,is_in,host,device_class,scope_metadata
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (
                        snapshot_id,
                        row.osd_id,
                        row.total_bytes,
                        row.used_bytes,
                        row.available_bytes,
                        row.used_ratio,
                        row.is_up,
                        row.is_in,
                        row.host,
                        row.device_class,
                        json.dumps(row.scope_metadata, separators=(",", ":")),
                    ),
                )
            released = (
                reconcile_settling_reservations(conn, inventory.fsid, now=inventory.captured_at)
                if inventory.fresh
                else []
            )
    return {
        "snapshot_id": snapshot_id,
        "fsid": inventory.fsid,
        "osdmap_epoch": inventory.osdmap_epoch,
        "captured_at": inventory.captured_at.isoformat(),
        "fresh": inventory.fresh,
        "osd_count": len(inventory.osds),
        "scope_complete": bool(inventory.cluster_health_summary.get("capacity_scope_complete")),
        "released_reservation_ids": released,
    }


def _failed_inventory(
    fsid: str,
    status: Mapping[str, Any],
    exc: BaseException,
    captured_at: datetime,
) -> CapacityInventory:
    code = (
        exc.code
        if isinstance(exc, (CapacityTelemetryError, RbdAgentClientError))
        else "COLLECTOR_FAILED"
    )
    try:
        summary = _health_summary(status)
    except CapacityTelemetryError:
        summary = {
            "status": "UNKNOWN",
            "checks": [],
            "pg_states": {},
            "degraded": False,
            "remapped": False,
            "recovering": False,
            "backfilling": False,
            "has_degraded_or_remapped_pgs": False,
            "has_recovery_or_backfill": False,
            "full": False,
            "backfillfull": False,
            "nearfull": False,
        }
    summary.update(
        {
            "collector_error_code": str(code),
            "capacity_scope_complete": False,
            "affected_pools": [],
            "resolved_affected_pools": [],
            "scope_errors": [],
        }
    )
    return CapacityInventory(
        fsid=fsid,
        osdmap_epoch=_status_epoch(status),
        captured_at=captured_at,
        fresh=False,
        cluster_health_summary=summary,
        osds=(),
    )


def collect_capacity_once(
    *,
    client: RbdAgentClient | Any | None = None,
    store: Callable[[CapacityInventory], dict[str, Any]] | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Collect and persist one read-only capacity sample."""

    settings = get_settings()
    agent = client or RbdAgentClient.from_settings()
    expected_fsid = _normalize_fsid(
        getattr(agent, "expected_fsid", None) or settings.ceph_expected_fsid,
        "CEPH_EXPECTED_FSID",
    )
    persist = store or store_capacity_inventory
    clock = now or (lambda: datetime.now(timezone.utc))
    started_at = clock().astimezone(timezone.utc)
    status_for_failure: Mapping[str, Any] | None = None
    observations: list[datetime] = []
    try:
        before, timestamp = _unwrap_agent_result(agent.ceph_status(), "ceph.status", expected_fsid)
        status_for_failure = _mapping(before, "status_before")
        observations.append(timestamp)
        df, timestamp = _unwrap_agent_result(agent.ceph_osd_df(), "ceph.osd_df", expected_fsid)
        observations.append(timestamp)
        tree, timestamp = _unwrap_agent_result(agent.ceph_osd_tree(), "ceph.osd_tree", expected_fsid)
        observations.append(timestamp)
        pools, timestamp = _unwrap_agent_result(
            agent.ceph_pool_ls_detail(), "ceph.pool_ls_detail", expected_fsid
        )
        observations.append(timestamp)
        rules, timestamp = _unwrap_agent_result(
            agent.ceph_crush_rule_dump(), "ceph.crush_rule_dump", expected_fsid
        )
        observations.append(timestamp)
        after, timestamp = _unwrap_agent_result(agent.ceph_status(), "ceph.status", expected_fsid)
        observations.append(timestamp)
        finished_at = clock().astimezone(timezone.utc)
        inventory = parse_ceph_inventory(
            fsid=expected_fsid,
            status_before=_mapping(before, "status_before"),
            status_after=_mapping(after, "status_after"),
            osd_df=_mapping(df, "osd_df"),
            osd_tree=_mapping(tree, "osd_tree"),
            pool_details=_list(pools, "pool_details"),
            crush_rules=_list(rules, "crush_rules"),
            affected_pools=settings.rgw_affected_pool_set | settings.rbd_allowed_pool_set,
            captured_at=finished_at,
        )
        max_age = settings.capacity_metrics_max_age_seconds
        timing_safe = (
            finished_at >= started_at
            and (finished_at - started_at).total_seconds() <= max_age
            and all(
                timestamp <= finished_at + timedelta(seconds=1)
                and (finished_at - timestamp).total_seconds() <= max_age
                for timestamp in observations
            )
        )
        if not timing_safe:
            summary = dict(inventory.cluster_health_summary)
            summary["collector_error_code"] = "STALE_OR_FUTURE_AGENT_TELEMETRY"
            inventory = replace(inventory, fresh=False, cluster_health_summary=summary)
        return persist(inventory)
    except Exception as exc:
        # If status was trustworthy enough to identify the cluster and epoch,
        # persist an explicit invalid sample. This makes API state UNKNOWN now,
        # rather than displaying old data as 0% or waiting for it to age out.
        if status_for_failure is not None:
            try:
                persist(_failed_inventory(expected_fsid, status_for_failure, exc, clock()))
            except Exception:
                pass
        raise
