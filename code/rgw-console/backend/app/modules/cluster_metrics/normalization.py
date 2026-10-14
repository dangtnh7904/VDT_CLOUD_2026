from __future__ import annotations

from typing import Any
import re


def daemon_source_valid(action: str, value: Any) -> bool:
    """Distinguish a real empty map from a failed/unrecognized source schema."""
    def named(item, field='name'):
        return isinstance(item, dict) and isinstance(item.get(field), str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,256}', item[field]) is not None
    if action == 'ceph.daemon_ls':
        return isinstance(value, list) and all(named(item, 'daemon_name') for item in value)
    if action == 'ceph.fs_dump':
        if not isinstance(value, dict) or not isinstance(value.get('filesystems'), list) or not isinstance(value.get('standbys'), list):
            return False
        if not all(named(item) for item in value['standbys']):
            return False
        for filesystem in value['filesystems']:
            if not isinstance(filesystem, dict) or not isinstance(filesystem.get('mdsmap'), dict):
                return False
            info = filesystem['mdsmap'].get('info')
            if not isinstance(info, dict) or not all(named(item) for item in info.values()):
                return False
        return True
    return True


def mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def rows(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def normalize(scope: str, evidence: dict[str, Any]) -> list[dict]:
    """Project known Ceph schemas without manufacturing missing observations."""
    def data(action: str):
        return evidence.get(action, {}).get("data")

    if scope == "cluster":
        status = mapping(data("ceph.status"))
        health = mapping(data("ceph.health_detail"))
        return [{"id": "cluster", "scope_type": scope, "name": "Cluster",
                 "health": health.get("status") or mapping(status.get("health")).get("status"),
                 "health_checks": health.get("checks"), "pgmap": status.get("pgmap"),
                 "capacity": mapping(data("ceph.df")).get("stats"),
                 "versions": data("ceph.versions")}]
    if scope == "mon":
        monmap = mapping(data("ceph.mon_dump"))
        quorum = mapping(data("ceph.quorum_status"))
        quorum_ids = quorum.get("quorum")
        return [{"id": str(row.get("name")), "name": row.get("name"), "scope_type": scope,
                 "rank": row.get("rank"), "address": row.get("public_addrs") or row.get("addr"),
                 "in_quorum": row.get("rank") in quorum_ids if isinstance(quorum_ids, list) else None,
                 "election_epoch": quorum.get("election_epoch"), "monmap_epoch": monmap.get("epoch")}
                for row in rows(monmap.get("mons")) if row.get("name") is not None]
    if scope == "mgr":
        state = mapping(data("ceph.mgr_dump"))
        modules = mapping(data("ceph.mgr_modules"))
        result = []
        if state.get("active_name"):
            result.append({"id": str(state["active_name"]), "name": state["active_name"], "scope_type": scope,
                           "role": "active", "available": state.get("available"), "gid": state.get("active_gid"),
                           "address": state.get("active_addr"), "enabled_modules": modules.get("enabled_modules")})
        result.extend({"id": str(row["name"]), "name": row["name"], "scope_type": scope,
                       "role": "standby", "gid": row.get("gid"), "available": None}
                      for row in rows(state.get("standbys")) if row.get("name"))
        return result
    if scope in {"rgw", "mds"}:
        # Orchestrator identifies deployed daemons, including stopped instances.
        # Do not infer availability or traffic from their presence in this list.
        deployed = {}
        for item in rows(data("ceph.daemon_ls")):
            name = item.get("daemon_name")
            if isinstance(name, str) and name.startswith(scope + "."):
                daemon_id = name.split(".", 1)[1]
                deployed[daemon_id] = {"id": daemon_id, "name": name, "scope_type": scope,
                    "status": item.get("status_desc"), "identity_source": "ceph.daemon_ls"}
        if scope == "rgw":
            return list(deployed.values())
        fsmap = mapping(data("ceph.fs_dump"))
        members = [(info, mapping(fs.get("mdsmap")).get("fs_name"), fs.get("id"))
                   for fs in rows(fsmap.get("filesystems"))
                   for info in rows(list(mapping(mapping(fs.get("mdsmap")).get("info")).values()))]
        members += [(standby, None, None) for standby in rows(fsmap.get("standbys"))]
        for info, filesystem, fscid in members:
            name = info.get("name")
            if not isinstance(name, str) or not name:
                continue
            daemon_id = name.removeprefix("mds.")
            deployed.setdefault(daemon_id, {"id": daemon_id, "name": "mds." + daemon_id, "scope_type": scope})
            deployed[daemon_id].update({"filesystem": filesystem, "filesystem_id": fscid,
                "rank": info.get("rank"), "gid": info.get("gid"), "state": info.get("state"),
                "address": info.get("addr") or info.get("addrs"), "laggy_since": info.get("laggy_since"),
                "fsmap_epoch": fsmap.get("epoch"), "identity_source": "ceph.fs_dump"})
        return list(deployed.values())
    if scope == "host":
        return [{"id": str(row["hostname"]), "name": row["hostname"], "scope_type": scope,
                 "address": row.get("addr"), "labels": row.get("labels"), "status": row.get("status"),
                 "cpu": None, "memory": None, "disk": None, "network": None,
                 "metric_reason": "HOST_METRICS_SOURCE_NOT_CONFIGURED"}
                for row in rows(data("ceph.host_ls")) if row.get("hostname")]
    if scope == "osd":
        tree = {row.get("id"): row for row in rows(mapping(data("ceph.osd_tree")).get("nodes"))}
        return [{"id": str(row["id"]), "name": f"osd.{row['id']}", "scope_type": scope,
                 "device_class": row.get("device_class"), "total_kb": row.get("kb"),
                 "used_kb": row.get("kb_used"), "available_kb": row.get("kb_avail"),
                 "utilization_percent": row.get("utilization"), "pg_count": row.get("pgs"),
                 "status": tree.get(row["id"], {}).get("status")}
                for row in rows(mapping(data("ceph.osd_df")).get("nodes")) if isinstance(row.get("id"), int) and row["id"] >= 0]
    if scope == "pool":
        capacity = {row.get("id"): row.get("stats") for row in rows(mapping(data("ceph.df")).get("pools"))}
        pool_rows = [{**row, "pool": row.get("pool", row.get("pool_id"))} for row in rows(data("ceph.pool_ls_detail"))]
        return [{"id": str(row["pool"]), "name": row.get("pool_name"), "scope_type": scope,
                 "type": row.get("type"), "size": row.get("size"), "min_size": row.get("min_size"),
                 "pg_num": row.get("pg_num"), "crush_rule": row.get("crush_rule"),
                 "application_metadata": row.get("application_metadata"), "capacity": capacity.get(row["pool"])}
                for row in pool_rows if isinstance(row.get("pool"), int)]
    return []


CATALOG = [
    {"id": "mon.in_quorum", "scope_type": "mon", "field": "in_quorum", "unit": "boolean", "kind": "gauge"},
    {"id": "mon.election_epoch", "scope_type": "mon", "field": "election_epoch", "unit": "epoch", "kind": "gauge"},
    {"id": "mgr.available", "scope_type": "mgr", "field": "available", "unit": "boolean", "kind": "gauge"},
    {"id": "osd.utilization_percent", "scope_type": "osd", "field": "utilization_percent", "unit": "percent", "kind": "gauge"},
    {"id": "osd.used_kb", "scope_type": "osd", "field": "used_kb", "unit": "KiB", "kind": "gauge"},
    {"id": "osd.pg_count", "scope_type": "osd", "field": "pg_count", "unit": "count", "kind": "gauge"},
    {"id": "pool.pg_num", "scope_type": "pool", "field": "pg_num", "unit": "count", "kind": "gauge"},
]


def metric_catalog() -> dict:
    return {"schema_version": 1, "items": [{**item, "source": "ceph_cli_snapshot", "capability": "SNAPSHOT_ONLY"} for item in CATALOG],
            "limitations": ["Snapshot samples are not a continuous metrics scrape.",
                             "Ceph throughput/latency history is available in Performance when its collector is configured.",
                             "Host CPU/RAM/disk/network and per-daemon process counters require an additional telemetry adapter."]}


def samples(collection: dict, metric_ids: list[str] | None = None) -> list[dict]:
    result = []
    for definition in CATALOG:
        if metric_ids and definition["id"] not in metric_ids:
            continue
        for row in collection.get("resources", []):
            if row.get("scope_type") != definition["scope_type"]:
                continue
            value = row.get(definition["field"])
            result.append({"metric_id": definition["id"], "resource_id": row["id"],
                           "scope_type": row["scope_type"], "unit": definition["unit"], "value": value,
                           "observed_at": collection.get("observed_at"),
                           "quality": "VALID" if value is not None else "UNSUPPORTED",
                           "reason": None if value is not None else "SOURCE_FIELD_MISSING",
                           "collection_id": collection.get("id"), "source": "ceph_cli_snapshot"})
    return result
