#!/usr/bin/env python3
"""Collect a version-tolerant, read-only baseline for one or more Ceph OSDs."""

import argparse
import ipaddress
import json
import math
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Union
from uuid import uuid4


SCHEMA_VERSION = 1
COLLECTOR_VERSION = "1.0.5"
JsonValue = Any
# Use typing aliases so the module can also load on Python 3.6.
RunCommand = Callable[[Sequence[str]], Dict[str, Any]]
ENVIRONMENT_OUTPUT_BYTES = 8192
ENVIRONMENT_ERROR_BYTES = 2048


class CollectionError(RuntimeError):
    """A required Ceph command failed or returned unusable output."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _command_name(args: Sequence[str]) -> str:
    return " ".join(args)


def run_command(args: Sequence[str], *, timeout_seconds: float = 45.0) -> Dict[str, Any]:
    """Run an argv-only command and return a bounded evidence envelope."""

    started_at = utc_now()
    try:
        completed = subprocess.run(
            list(args),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise CollectionError(f"command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CollectionError(f"command timed out: {_command_name(args)}") from exc

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    evidence: Dict[str, Any] = {
        "command": list(args),
        "started_at": started_at,
        "completed_at": utc_now(),
        "exit_code": completed.returncode,
        "stderr": stderr[-4000:],
    }
    if completed.returncode != 0:
        evidence["error"] = "COMMAND_FAILED"
        return evidence

    try:
        evidence["data"] = json.loads(stdout)
        evidence["format"] = "json"
    except json.JSONDecodeError:
        evidence["data"] = stdout
        evidence["format"] = "text"
    return evidence


def _ceph(ceph_command: Union[Sequence[str], str], *parts: str) -> List[str]:
    prefix = [ceph_command] if isinstance(ceph_command, str) else list(ceph_command)
    return [*prefix, *parts]


def run_environment_command(
    args: Sequence[str], *, timeout_seconds: float = 2.0
) -> Dict[str, Any]:
    """Run one fixed environment probe with bounded in-memory output.

    Drain both pipes even after the evidence limit is reached, so noisy tools
    cannot fill a pipe or grow memory indefinitely. No shell is involved.
    """
    started_at = utc_now()
    evidence: Dict[str, Any] = {"command": list(args), "started_at": started_at}
    try:
        process = subprocess.Popen(
            list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        evidence.update({
            "completed_at": utc_now(), "exit_code": None,
            "error": "COMMAND_NOT_FOUND", "stderr": "",
        })
        return evidence
    except OSError:
        evidence.update({
            "completed_at": utc_now(), "exit_code": None,
            "error": "EXECUTION_FAILED", "stderr": "",
        })
        return evidence

    stdout = bytearray()
    stderr = bytearray()
    lengths = [0, 0]

    def drain(pipe: Any, target: bytearray, limit: int, index: int) -> None:
        try:
            while True:
                block = pipe.read(4096)
                if not block:
                    break
                lengths[index] += len(block)
                if len(target) < limit:
                    target.extend(block[:limit - len(target)])
        finally:
            pipe.close()

    readers = [
        threading.Thread(target=drain, args=(process.stdout, stdout, ENVIRONMENT_OUTPUT_BYTES, 0)),
        threading.Thread(target=drain, args=(process.stderr, stderr, ENVIRONMENT_ERROR_BYTES, 1)),
    ]
    for reader in readers:
        reader.daemon = True
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for reader in readers:
        # Fixed probes do not intentionally leave background descendants.
        # Do not hang this collector if an unexpected child retains a pipe.
        reader.join(timeout=0.2)

    truncated = lengths[0] > ENVIRONMENT_OUTPUT_BYTES or lengths[1] > ENVIRONMENT_ERROR_BYTES
    evidence.update({
        "completed_at": utc_now(), "exit_code": process.returncode,
        "format": "text", "data": stdout.decode("utf-8", "replace").strip(),
        "stderr": stderr.decode("utf-8", "replace").strip(),
        "stdout_bytes": lengths[0], "stderr_bytes": lengths[1],
        "truncated": truncated,
    })
    if timed_out:
        evidence["error"] = "COMMAND_TIMED_OUT"
    elif process.returncode != 0:
        evidence["error"] = "COMMAND_FAILED"
    elif truncated:
        evidence["error"] = "OUTPUT_TRUNCATED"
    elif any(reader.is_alive() for reader in readers):
        evidence["error"] = "OUTPUT_INCOMPLETE"
    return evidence


def _safe_environment_text(value: Any, maximum: int = 1024) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return re.sub(r"[\x00-\x1f\x7f]", " ", value.strip())[:maximum]


def _environment_os() -> Dict[str, Any]:
    """Read only allowlisted distribution metadata from the standard file."""
    values: Dict[str, Any] = {}
    try:
        with open("/etc/os-release", "rb") as handle:
            encoded = handle.read(8193)
        if len(encoded) > 8192:
            return {"source": "/etc/os-release", "quality": "PARTIAL", "reason": "OUTPUT_TRUNCATED"}
        allowed = {"ID": "id", "NAME": "name", "VERSION_ID": "version_id", "VERSION": "version", "PRETTY_NAME": "pretty_name"}
        for line in encoded.decode("utf-8", "replace").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in allowed:
                values[allowed[key]] = _safe_environment_text(value.strip().strip("\"'"))
        values.update({"source": "/etc/os-release", "quality": "VALID" if values else "PARTIAL"})
    except OSError:
        values.update({"source": "/etc/os-release", "quality": "PARTIAL", "reason": "SOURCE_UNAVAILABLE"})
    return values


def _environment_shell() -> Dict[str, Any]:
    configured = _safe_environment_text(os.environ.get("SHELL"), 512)
    parent_executable = None
    try:
        parent_executable = _safe_environment_text(os.readlink("/proc/{}/exe".format(os.getppid())), 512)
    except (OSError, AttributeError):
        pass
    return {
        "configured_path": configured,
        "configured_source": "env:SHELL" if configured else None,
        "observed_parent_executable": parent_executable,
        "observed_source": "procfs:parent_exe" if parent_executable else None,
        "quality": "VALID" if configured or parent_executable else "PARTIAL",
        "reason": None if configured or parent_executable else "SHELL_SOURCE_UNAVAILABLE",
        "note": "Configured login shell and parent executable are evidence, not a claim that an interactive shell is active.",
    }


def _clock_environment(evidence: Dict[str, Any]) -> Dict[str, Any]:
    properties: Dict[str, str] = {}
    usable = evidence.get("exit_code") == 0 and not evidence.get("error")
    if usable:
        for line in str(evidence.get("data") or "").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"NTP", "NTPSynchronized", "Timezone", "LocalRTC"}:
                properties[key] = value.strip()

    def boolean(key: str) -> Optional[bool]:
        value = properties.get(key)
        return True if value == "yes" else False if value == "no" else None

    synchronized = boolean("NTPSynchronized")
    return {
        "ntp_enabled": boolean("NTP"),
        "synchronized": synchronized,
        "time_zone": _safe_environment_text(properties.get("Timezone")),
        "local_rtc": boolean("LocalRTC"),
        "quality": "VALID" if usable and synchronized is not None else "PARTIAL",
        "source": "timedatectl properties on SSH client host",
        "reason": (
            "CLOCK_UNSYNCHRONIZED" if synchronized is False
            else "CLOCK_STATUS_UNAVAILABLE" if synchronized is None else None
        ),
        "evidence": evidence,
    }


def collect_environment(
    *, ceph_command: Union[Sequence[str], str] = "ceph",
    runner: RunCommand = run_environment_command,
) -> Dict[str, Any]:
    """A0.1 evidence for this host only; never infer other daemon hosts."""
    started_at = utc_now()
    commands = {
        "ceph": _ceph(ceph_command, "--version"),
        "rbd": ["rbd", "--version"],
        "rados": ["rados", "--version"],
        "ssh": ["ssh", "-V"],
        "osdmaptool": ["osdmaptool", "--version"],
        "crushtool": ["crushtool", "--version"],
        "clock": ["timedatectl", "show", "--property=NTP", "--property=NTPSynchronized", "--property=Timezone", "--property=LocalRTC"],
    }

    def probe(item: Any) -> Any:
        key, command = item
        try:
            evidence = dict(runner(command))
        except Exception:
            evidence = {"command": list(command), "exit_code": None, "error": "EXECUTION_FAILED", "stderr": ""}
        # Also bound injected/custom runners used by integrations and tests.
        evidence["command"] = list(command)
        for field, limit in (("data", ENVIRONMENT_OUTPUT_BYTES), ("stderr", ENVIRONMENT_ERROR_BYTES)):
            value = evidence.get(field)
            if isinstance(value, str):
                encoded = value.encode("utf-8", "replace")
                if len(encoded) > limit:
                    evidence[field] = encoded[:limit].decode("utf-8", "replace")
                    evidence["truncated"] = True
                    evidence["error"] = "OUTPUT_TRUNCATED"
            elif value is not None:
                # Environment probes are text-only; do not retain unbounded JSON.
                evidence.pop(field, None)
                evidence["error"] = "UNEXPECTED_OUTPUT_FORMAT"
        return key, evidence

    with ThreadPoolExecutor(max_workers=3) as executor:
        evidence_by_key = dict(executor.map(probe, commands.items()))
    tools: Dict[str, Any] = {}
    errors: List[Dict[str, Any]] = []
    for key in commands:
        evidence = evidence_by_key[key]
        usable = evidence.get("exit_code") == 0 and not evidence.get("error")
        if not usable:
            errors.append({
                "command": list(commands[key]), "code": evidence.get("error") or "COMMAND_FAILED",
                "required": key == "ceph",
            })
        if key == "clock":
            continue
        output = evidence.get("data") or (evidence.get("stderr") if key == "ssh" else None)
        version = _safe_environment_text(str(output).splitlines()[0]) if usable and output else None
        if usable and not version:
            errors.append({"command": list(commands[key]), "code": "VERSION_NOT_REPORTED", "required": key == "ceph"})
        tools[key] = {
            "available": False if evidence.get("error") == "COMMAND_NOT_FOUND" else True if evidence.get("exit_code") is not None else None,
            "version": version,
            "quality": "VALID" if version else "PARTIAL",
            "evidence": evidence,
        }
    clock = _clock_environment(evidence_by_key["clock"])
    if clock["reason"]:
        errors.append({"command": list(commands["clock"]), "code": clock["reason"], "required": False})
    try:
        kernel = os.uname()
        kernel_source = "os.uname"
    except AttributeError:
        kernel = platform.uname()
        kernel_source = "platform.uname"
    host = {
        "hostname": _safe_environment_text(socket.gethostname()),
        "hostname_source": "socket.gethostname",
        "kernel": {
            "system": _safe_environment_text(kernel.system if hasattr(kernel, "system") else kernel.sysname),
            "release": _safe_environment_text(kernel.release),
            "machine": _safe_environment_text(kernel.machine),
            "source": kernel_source,
        },
        "os": _environment_os(),
    }
    if host["os"]["quality"] != "VALID":
        errors.append({"code": host["os"].get("reason") or "OS_METADATA_UNAVAILABLE", "required": False})
    shell = _environment_shell()
    if shell["quality"] != "VALID":
        errors.append({"code": shell["reason"], "required": False})
    completed_at = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "CEPH_CLIENT_ENVIRONMENT",
        "collector_version": COLLECTOR_VERSION,
        "scope": "SSH_CLIENT_HOST_ONLY",
        "started_at": started_at, "completed_at": completed_at, "collected_at": completed_at,
        "quality": "PARTIAL" if errors else "VALID", "errors": errors,
        "host": host,
        "shell": shell,
        "python": {
            "version": platform.python_version(), "implementation": platform.python_implementation(),
            "executable": _safe_environment_text(sys.executable), "source": "collector process",
        },
        "tools": tools, "clock": clock,
        "coverage": {
            "host_scope": "Only the host running this SSH helper; not all cluster/daemon hosts.",
            "clock_scope": "Local synchronization status only; no clock offset, quorum or cluster-wide clock assurance.",
            "tools_scope": "Read-only client/version availability; does not run workloads or modify cluster configuration.",
            "secrets": "No environment dump, credentials, key files, shell history or process command lines collected.",
        },
    }


def _run_evidence(
    runner: RunCommand,
    args: Sequence[str],
    *,
    required: bool,
    fatal: bool = False,
    errors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    try:
        evidence = runner(args)
    except Exception as exc:
        evidence = {
            "command": list(args),
            "exit_code": None,
            "error": "EXECUTION_FAILED",
            "stderr": str(exc)[:4000],
        }
    if evidence.get("exit_code") != 0:
        errors.append(
            {
                "command": _command_name(args),
                "code": evidence.get("error") or "COMMAND_FAILED",
                "message": evidence.get("stderr") or "command failed",
                "required": required,
            }
        )
        if fatal:
            exit_code = evidence.get("exit_code")
            detail = str(evidence.get("stderr") or evidence.get("error") or "unknown error")
            raise CollectionError(
                f"required command failed: {_command_name(args)} "
                f"(exit_code={exit_code}): {detail[:1000]}"
            )
    return evidence


def _data(evidence: Any) -> Any:
    return evidence.get("data") if isinstance(evidence, dict) else None


def _mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("pg_stats", "pg_map", "items", "nodes", "osds"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return [row for row in candidate if isinstance(row, dict)]
    return []


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _first(value: Any, *keys: str) -> Any:
    if not isinstance(value, dict):
        return None
    for key in keys:
        candidate = value.get(key)
        if candidate not in (None, "", [], {}):
            return candidate
    return None


def _metadata_row(value: Any, osd_id: int) -> Dict[str, Any]:
    if isinstance(value, dict):
        if "id" in value or "hostname" in value or "ceph_version" in value:
            return value
        nested = value.get(str(osd_id)) or value.get(f"osd.{osd_id}")
        if isinstance(nested, dict):
            return nested
    for row in _rows(value):
        candidate = _int(_first(row, "id", "osd", "osd_id"))
        if candidate == osd_id:
            return row
    return {}


def _find_osd_row(value: Any, osd_id: int) -> Dict[str, Any]:
    for row in _rows(value):
        if _int(_first(row, "id", "osd", "osd_id")) == osd_id:
            return row
    return {}


def _split_tokens(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = [str(item) for item in value]
    elif isinstance(value, str):
        raw = re.split(r"[\s,;]+", value)
    else:
        raw = []
    return [item.strip() for item in raw if item.strip()]


def _device_path(value: str) -> str:
    if value.startswith("/dev/"):
        return value
    if re.fullmatch(r"(?:sd[a-z]+\d*|vd[a-z]+\d*|xvd[a-z]+\d*|nvme\d+n\d+(?:p\d+)?|dm-\d+)", value):
        return f"/dev/{value}"
    return value


def _unique(values: Iterable[Any]) -> List[Any]:
    result: List[Any] = []
    for value in values:
        if value not in (None, "") and value not in result:
            result.append(value)
    return result


def _device_summary(metadata: Dict[str, Any], df_row: Dict[str, Any]) -> Dict[str, Any]:
    roles = {
        "data": {
            "path": _first(
                metadata,
                "bluestore_bdev_partition_path",
                "bluestore_bdev_dev_node",
                "osd_data_device",
            ),
            "devices": _first(metadata, "bluestore_bdev_devices", "devices"),
            "size_bytes": _int(_first(metadata, "bluestore_bdev_size", "osd_data_size")),
        },
        "db": {
            "path": _first(
                metadata,
                "bluefs_db_partition_path",
                "bluefs_db_dev_node",
                "block_db",
            ),
            "devices": _first(metadata, "bluefs_db_devices", "block_db_devices"),
            "size_bytes": _int(_first(metadata, "bluefs_db_size", "block_db_size")),
        },
        "wal": {
            "path": _first(
                metadata,
                "bluefs_wal_partition_path",
                "bluefs_wal_dev_node",
                "block_wal",
            ),
            "devices": _first(metadata, "bluefs_wal_devices", "block_wal_devices"),
            "size_bytes": _int(_first(metadata, "bluefs_wal_size", "block_wal_size")),
        },
    }
    all_paths: List[str] = []
    for role in roles.values():
        if isinstance(role["path"], str):
            role["path"] = _device_path(role["path"])
            all_paths.append(role["path"])
        physical = [_device_path(item) for item in _split_tokens(role["devices"])]
        role["physical_devices"] = physical
        all_paths.extend(physical)
        role.pop("devices", None)

    capacity_bytes = _int(df_row.get("kb"))
    capacity_bytes = capacity_bytes * 1024 if capacity_bytes is not None else None
    if roles["data"]["size_bytes"] is None:
        roles["data"]["size_bytes"] = capacity_bytes

    device_ids = _split_tokens(_first(metadata, "device_ids", "device_id"))
    return {
        "data": roles["data"],
        "db": roles["db"],
        "wal": roles["wal"],
        "all_paths": _unique(all_paths),
        "device_ids": device_ids,
        "mapping_source": "ceph_osd_metadata",
    }


def _extract_ips(value: Any) -> List[str]:
    text = str(value or "")
    found: List[str] = []
    candidates = re.findall(r"\[[0-9a-fA-F:]+\]|(?:\d{1,3}\.){3}\d{1,3}", text)
    for candidate in candidates:
        candidate = candidate.strip("[]")
        try:
            parsed = str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
        if parsed not in found:
            found.append(parsed)
    return found


def _network_summary(metadata: Dict[str, Any], find_data: Dict[str, Any]) -> Dict[str, Any]:
    public_values = [
        _first(metadata, "front_addr", "public_addr"),
        _first(find_data, "front_addr", "public_addr", "ip"),
    ]
    cluster_values = [
        _first(metadata, "back_addr", "cluster_addr"),
        _first(find_data, "back_addr", "cluster_addr"),
    ]
    public_ips = _unique(ip for value in public_values for ip in _extract_ips(value))
    cluster_ips = _unique(ip for value in cluster_values for ip in _extract_ips(value))
    return {
        "public_ip": public_ips[0] if public_ips else None,
        "public_ips": public_ips,
        "cluster_ip": cluster_ips[0] if cluster_ips else None,
        "cluster_ips": cluster_ips,
        "raw_public_address": public_values[0],
        "raw_cluster_address": cluster_values[0],
    }


def _pg_ids(value: Any) -> List[str]:
    ids: List[str] = []
    for row in _rows(value):
        pgid = _first(row, "pgid", "pg_id", "pg")
        if pgid is not None and str(pgid) not in ids:
            ids.append(str(pgid))
    return sorted(ids)


def _crush_location(find_data: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    location = find_data.get("crush_location")
    if isinstance(location, dict):
        return location
    location = metadata.get("crush_location")
    if isinstance(location, dict):
        return location
    return {}


def normalize_osd(
    osd_id: int,
    *,
    common: Dict[str, Any],
    evidence: Dict[str, Any],
    errors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    metadata = _metadata_row(_data(evidence.get("metadata")), osd_id)
    find_data = _mapping(_data(evidence.get("find")))
    df_row = _find_osd_row(_data(common.get("osd_df_tree")), osd_id)
    tree_row = _find_osd_row(_data(common.get("osd_tree")), osd_id)
    dump_row = _find_osd_row(_mapping(_data(common.get("osd_dump"))).get("osds"), osd_id)
    pg_evidence_ok = _mapping(evidence.get("pg_by_osd")).get("exit_code") == 0
    primary_pg_evidence_ok = _mapping(evidence.get("pg_by_primary")).get("exit_code") == 0
    pg_ids = _pg_ids(_data(evidence.get("pg_by_osd"))) if pg_evidence_ok else []
    primary_pg_ids = (
        _pg_ids(_data(evidence.get("pg_by_primary"))) if primary_pg_evidence_ok else []
    )
    location = _crush_location(find_data, metadata)
    hostname = _first(metadata, "hostname", "host") or location.get("host") or find_data.get("host")

    total_kib = _int(df_row.get("kb"))
    used_kib = _int(df_row.get("kb_used"))
    available_kib = _int(df_row.get("kb_avail"))
    utilization = _float(_first(df_row, "utilization", "percent_used"))
    if utilization is None and total_kib and used_kib is not None:
        utilization = round(used_kib * 100.0 / total_kib, 6)

    warnings: List[str] = []
    reported_pgs = _int(_first(df_row, "pgs", "pg_count"))
    if reported_pgs is not None and pg_ids and reported_pgs != len(pg_ids):
        warnings.append("PG_COUNT_DIFFERS_FROM_OSD_DF")
    if not pg_evidence_ok:
        warnings.append("PG_LIST_UNAVAILABLE")
    if not primary_pg_evidence_ok:
        warnings.append("PRIMARY_PG_LIST_UNAVAILABLE")
    if not hostname:
        warnings.append("HOST_NOT_REPORTED")

    devices = _device_summary(metadata, df_row)
    if not devices["all_paths"]:
        warnings.append("DEVICE_PATH_NOT_REPORTED_BY_CEPH_METADATA")

    up_value = _first(dump_row, "up")
    in_value = _first(dump_row, "in")
    if up_value is None and tree_row.get("status") is not None:
        up_value = tree_row.get("status") == "up"
    if in_value is None:
        reweight = _float(_first(df_row, "reweight"))
        if reweight is None:
            reweight = _float(tree_row.get("reweight"))
        in_value = reweight is not None and reweight > 0

    required_errors = [item for item in errors if item.get("required")]
    quality = "INCONCLUSIVE" if required_errors else "PARTIAL" if errors or warnings else "VALID"
    return {
        "schema_version": SCHEMA_VERSION,
        "quality": quality,
        "warnings": sorted(set(warnings)),
        "errors": errors,
        "identity": {
            "osd_id": osd_id,
            "name": f"osd.{osd_id}",
            "osd_fsid": (
                _first(metadata, "osd_fsid", "uuid", "fsid")
                or _first(dump_row, "uuid", "osd_fsid")
            ),
            "hostname": hostname,
            "crush_location": location,
            "device_class": _first(df_row, "device_class", "class") or tree_row.get("device_class"),
        },
        "version": {
            "ceph_version": _first(metadata, "ceph_version", "version"),
            "ceph_version_short": _first(metadata, "ceph_version_short", "release"),
            "container_image": _first(metadata, "container_image", "container_image_name"),
            "container_image_id": _first(metadata, "container_image_id", "container_image_digest"),
        },
        "network": _network_summary(metadata, find_data),
        "devices": devices,
        "capacity": {
            "total_bytes": total_kib * 1024 if total_kib is not None else None,
            "used_bytes": used_kib * 1024 if used_kib is not None else None,
            "available_bytes": available_kib * 1024 if available_kib is not None else None,
            "used_percent": utilization,
        },
        "state": {
            "up": bool(up_value) if up_value is not None else None,
            "in": bool(in_value) if in_value is not None else None,
            "status": tree_row.get("status"),
            "crush_weight": _float(_first(df_row, "crush_weight", "weight")),
            "reweight": (
                _float(_first(df_row, "reweight"))
                if _first(df_row, "reweight") is not None
                else _float(tree_row.get("reweight"))
            ),
            "primary_affinity": _float(dump_row.get("primary_affinity")),
        },
        "placement_groups": {
            "count": len(pg_ids) if pg_evidence_ok else None,
            "primary_count": len(primary_pg_ids) if primary_pg_evidence_ok else None,
            "reported_by_osd_df": reported_pgs,
            "pg_ids": pg_ids if pg_evidence_ok else None,
            "primary_pg_ids": primary_pg_ids if primary_pg_evidence_ok else None,
        },
        "evidence": evidence,
    }


def _common_commands(ceph_command: Union[Sequence[str], str]) -> Dict[str, List[str]]:
    return {
        "status": _ceph(ceph_command, "status", "--format=json"),
        "health_detail": _ceph(ceph_command, "health", "detail", "--format=json"),
        "pg_stat": _ceph(ceph_command, "pg", "stat", "--format=json"),
        "pool_ls_detail": _ceph(ceph_command, "osd", "pool", "ls", "detail", "--format=json"),
        "versions": _ceph(ceph_command, "versions", "--format=json"),
        "osd_tree": _ceph(ceph_command, "osd", "tree", "--format=json"),
        "osd_dump": _ceph(ceph_command, "osd", "dump", "--format=json"),
        "osd_df_tree": _ceph(ceph_command, "osd", "df", "tree", "--format=json"),
        "config_dump": _ceph(ceph_command, "config", "dump", "--format=json"),
    }


def _osd_commands(ceph_command: Union[Sequence[str], str], osd_id: int) -> Dict[str, List[str]]:
    name = f"osd.{osd_id}"
    return {
        "metadata": _ceph(ceph_command, "osd", "metadata", str(osd_id), "--format=json"),
        "find": _ceph(ceph_command, "osd", "find", str(osd_id), "--format=json"),
        "pg_by_osd": _ceph(ceph_command, "pg", "ls-by-osd", name, "--format=json"),
        "pg_by_primary": _ceph(ceph_command, "pg", "ls-by-primary", name, "--format=json"),
        "config_effective": _ceph(
            ceph_command,
            "config",
            "show-with-defaults",
            name,
            "--format=json",
        ),
        "device_inventory": _ceph(
            ceph_command,
            "device",
            "ls-by-daemon",
            name,
            "--format=json",
        ),
    }


def _osd_ids_from_df(common: Dict[str, Any]) -> List[int]:
    # Assignment expressions would prevent startup on Python 3.6 and 3.7.
    ids = set()
    for row in _rows(_data(common.get("osd_df_tree"))):
        candidate = _int(row.get("id"))
        if candidate is not None and candidate >= 0:
            ids.add(candidate)
    return sorted(ids)


def collect(
    *,
    osd_ids: Optional[Sequence[int]],
    ceph_bin: str = "ceph",
    ceph_args: Sequence[str] = (),
    runner: RunCommand = run_command,
) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    ceph_command = [ceph_bin, *ceph_args]
    fsid_evidence = _run_evidence(
        runner,
        _ceph(ceph_command, "fsid"),
        required=True,
        fatal=True,
        errors=errors,
    )
    fsid = str(_data(fsid_evidence) or "").strip()
    if not fsid:
        raise CollectionError("ceph fsid returned an empty value")

    common: Dict[str, Any] = {"fsid": fsid_evidence}
    for key, command in _common_commands(ceph_command).items():
        common[key] = _run_evidence(runner, command, required=False, errors=errors)

    selected_ids = sorted(set(osd_ids or _osd_ids_from_df(common)))
    if not selected_ids:
        raise CollectionError("no OSD IDs were selected or discovered")

    osds: List[Dict[str, Any]] = []
    for osd_id in selected_ids:
        osd_errors: List[Dict[str, Any]] = []
        evidence: Dict[str, Any] = {}
        for key, command in _osd_commands(ceph_command, osd_id).items():
            evidence[key] = _run_evidence(
                runner,
                command,
                required=key in {"metadata", "find", "pg_by_osd", "pg_by_primary"},
                errors=osd_errors,
            )
        osds.append(
            normalize_osd(
                osd_id,
                common=common,
                evidence=evidence,
                errors=osd_errors,
            )
        )

    osd_qualities = {item["quality"] for item in osds}
    collection_quality = (
        "INCONCLUSIVE"
        if "INCONCLUSIVE" in osd_qualities
        else "PARTIAL"
        if errors or "PARTIAL" in osd_qualities
        else "VALID"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "CEPH_OSD_BASELINE",
        "collector_version": COLLECTOR_VERSION,
        "collection_id": str(uuid4()),
        "collected_at": utc_now(),
        "cluster_fsid": fsid,
        "quality": collection_quality,
        "errors": errors,
        "osd_count": len(osds),
        "osds": osds,
        "cluster_evidence": common,
    }


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only identity, device, capacity, PG and config evidence for Ceph OSDs."
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + COLLECTOR_VERSION)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--osd",
        type=int,
        action="append",
        dest="osd_ids",
        help="OSD ID to collect; repeat for multiple OSDs",
    )
    selection.add_argument("--all", action="store_true", help="collect every OSD found in ceph osd df tree")
    selection.add_argument("--environment-only", action="store_true", help="collect read-only A0.1 client-host environment instead of OSD evidence")
    parser.add_argument("--ceph-bin", default="ceph", help="Ceph CLI executable (default: ceph)")
    parser.add_argument("--sudo-ceph", action="store_true", help="Run each fixed Ceph command with sudo -n; keep Python unprivileged")
    parser.add_argument("--cluster", help="Ceph cluster name passed as --cluster")
    parser.add_argument("--conf", type=Path, help="path to ceph.conf")
    parser.add_argument("--name", help="CephX client name, for example client.admin")
    parser.add_argument("--keyring", type=Path, help="path to the CephX keyring")
    parser.add_argument("--timeout", type=float, default=45.0, help="command timeout in seconds")
    parser.add_argument("--output", type=Path, help="write JSON atomically to this path; stdout if omitted")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        print("error: --timeout must be finite and greater than zero", file=sys.stderr)
        return 2

    def configured_runner(command: Sequence[str]) -> Dict[str, Any]:
        prefix = ["sudo", "-n"] if args.sudo_ceph else []
        return run_command([*prefix, *command], timeout_seconds=args.timeout)

    try:
        ceph_args: List[str] = []
        if args.cluster:
            ceph_args.extend(["--cluster", args.cluster])
        if args.conf:
            ceph_args.extend(["--conf", str(args.conf)])
        if args.name:
            ceph_args.extend(["--name", args.name])
        if args.keyring:
            ceph_args.extend(["--keyring", str(args.keyring)])
        if args.environment_only:
            def environment_runner(command: Sequence[str]) -> Dict[str, Any]:
                return run_environment_command(command, timeout_seconds=min(args.timeout, 3.0))

            ceph_version_command = (["sudo", "-n"] if args.sudo_ceph else []) + [args.ceph_bin]
            payload = collect_environment(ceph_command=ceph_version_command, runner=environment_runner)
        else:
            payload = collect(
                osd_ids=None if args.all else args.osd_ids,
                ceph_bin=args.ceph_bin,
                ceph_args=ceph_args,
                runner=configured_runner,
            )
    except CollectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        _atomic_write(args.output.resolve(), payload)
        print(str(args.output.resolve()))
    else:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
