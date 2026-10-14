from __future__ import annotations

from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _osdmap(status: dict[str, Any]) -> dict[str, Any]:
    outer = _mapping(status.get("osdmap"))
    return _mapping(outer.get("osdmap")) or outer


def normalize_inventory(
    raw: dict[str, Any],
    *,
    cluster_id: str,
    allowed_osds: frozenset[str],
    allowed_hosts: frozenset[str],
    allowed_pools: frozenset[str],
    allowed_device_classes: frozenset[str],
) -> dict[str, Any]:
    capacity = _mapping(raw.get("capacity"))
    status_before = _mapping(capacity.get("status_before"))
    status_after = _mapping(capacity.get("status_after"))
    df_rows = _rows(_mapping(capacity.get("osd_df")).get("nodes"))
    tree_rows = _rows(_mapping(capacity.get("osd_tree")).get("nodes"))
    pool_rows = _rows(capacity.get("pool_details"))
    osdmap_before = _osdmap(status_before)
    osdmap_after = _osdmap(status_after)

    limitations: list[str] = []
    epoch_before = _integer(osdmap_before.get("epoch"))
    epoch_after = _integer(osdmap_after.get("epoch"))
    if epoch_before is None or epoch_after is None:
        limitations.append("OSDMAP_EPOCH_MISSING")
    elif epoch_before != epoch_after:
        limitations.append("OSDMAP_CHANGED_DURING_COLLECTION")

    by_tree_id = {
        _integer(row.get("id")): row
        for row in tree_rows
        if _integer(row.get("id")) is not None
    }
    host_for: dict[int, str] = {}
    rack_for_host: dict[int, str] = {}
    for row in tree_rows:
        node_id = _integer(row.get("id"))
        node_type = row.get("type")
        children = row.get("children") if isinstance(row.get("children"), list) else []
        if node_type == "host" and node_id is not None:
            for child in children:
                child_id = _integer(child)
                if child_id is not None:
                    host_for[child_id] = str(row.get("name") or "")
        if node_type == "rack" and node_id is not None:
            for child in children:
                child_id = _integer(child)
                if child_id is not None:
                    rack_for_host[child_id] = str(row.get("name") or "")

    rack_for_osd: dict[int, str] = {}
    for osd_id, host_name in host_for.items():
        host_node = next(
            (
                row
                for row in tree_rows
                if row.get("type") == "host" and str(row.get("name") or "") == host_name
            ),
            None,
        )
        if host_node is not None:
            host_id = _integer(host_node.get("id"))
            if host_id is not None and host_id in rack_for_host:
                rack_for_osd[osd_id] = rack_for_host[host_id]

    osds: list[dict[str, Any]] = []
    for row in df_rows:
        osd_id = _integer(row.get("id"))
        if osd_id is None:
            limitations.append("OSD_WITHOUT_ID")
            continue
        tree = by_tree_id.get(osd_id, {})
        osd_name = str(osd_id)
        host = host_for.get(osd_id) or None
        device_class = row.get("device_class") or tree.get("device_class")
        reweight = _number(row.get("reweight"))
        osds.append(
            {
                "osd_id": osd_id,
                "name": tree.get("name") or f"osd.{osd_id}",
                "host": host,
                "rack": rack_for_osd.get(osd_id),
                "device_class": device_class,
                "up": tree.get("status") == "up" if tree.get("status") is not None else None,
                "in": reweight != 0 if reweight is not None else None,
                "total_kb": _integer(row.get("kb")),
                "used_kb": _integer(row.get("kb_used")),
                "available_kb": _integer(row.get("kb_avail")),
                "utilization_percent": _number(row.get("utilization")),
                "pg_count": _integer(row.get("pgs")),
                "allowed": (
                    bool(allowed_osds)
                    and osd_name in allowed_osds
                    and (not allowed_hosts or host in allowed_hosts)
                    and (not allowed_device_classes or device_class in allowed_device_classes)
                ),
            }
        )

    pools: list[dict[str, Any]] = []
    for row in pool_rows:
        name = row.get("pool_name") or row.get("name")
        pool_type = row.get("type")
        pools.append(
            {
                "pool_id": _integer(row.get("pool", row.get("pool_id"))),
                "name": name,
                "type": "replicated" if pool_type in {1, "1", "replicated"} else "erasure" if pool_type in {3, "3", "erasure"} else None,
                "size": _integer(row.get("size")),
                "min_size": _integer(row.get("min_size")),
                "pg_num": _integer(row.get("pg_num")),
                "crush_rule": row.get("crush_rule"),
                "allowed": bool(allowed_pools) and isinstance(name, str) and name in allowed_pools,
            }
        )

    if not df_rows:
        limitations.append("OSD_DF_EMPTY_OR_UNSUPPORTED")
    if not pool_rows:
        limitations.append("POOL_DETAILS_EMPTY_OR_UNSUPPORTED")

    return {
        "schema_version": 1,
        "cluster_id": cluster_id,
        "fsid": raw.get("fsid"),
        "observed_at": raw.get("observed_at"),
        "quality": "VALID" if not limitations else "INCONCLUSIVE",
        "health": _mapping(status_after.get("health")).get("status"),
        "osdmap_epoch": epoch_after,
        "osds": sorted(osds, key=lambda item: item["osd_id"]),
        "pools": sorted(pools, key=lambda item: str(item.get("name") or "")),
        "versions": _mapping(raw.get("versions")),
        "limitations": sorted(set(limitations)),
    }
