"""Offline OSDMap worker. Only a shared spool is mounted; never Ceph credentials."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import subprocess
import struct
import tempfile
import time
from uuid import UUID

MAX_MAP = 16 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
MAX_PGS = 100000
TOOL = "/usr/bin/osdmaptool"
CRUSH_TOOL = "/usr/bin/crushtool"
PARSER_VERSION = 2
UNASSIGNED = {-1, 2147483647}
EXPECTED_TOOL_SHA256 = {
    "osdmaptool_sha256": "c1532cfd43e6a0cfab5c6a3bd3da405ac7224606646f9351fe34bf5fb2ed1fe0",
    "crushtool_sha256": "187ab0d81224f4e692a4376b728a86f380dffa599529bd7b9749389a086952ce",
}
PG_RE = re.compile(r"^(\d+\.[0-9a-f]+) raw \(\[([^\]]*)\], p(-?\d+)\) up \(\[([^\]]*)\], p(-?\d+)\) acting \(\[([^\]]*)\], p(-?\d+)\)$")


def limited():
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))


def run_tool(args, cwd, tool=TOOL):
    # File-backed output is kernel-bounded, unlike unbounded PIPE capture.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        result = subprocess.run([tool] + args, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                stdout=output, stderr=errors, timeout=40, preexec_fn=limited,
                                env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"})
        if result.returncode:
            raise ValueError("OSDMAP_TOOL_FAILED")
        output.seek(0)
        data = output.read(MAX_OUTPUT + 1)
        if len(data) > MAX_OUTPUT:
            raise ValueError("OSDMAP_OUTPUT_LIMIT")
        return data.decode("utf-8", errors="strict")


def parse_placements(text, expected):
    rows = {}
    for line in text.splitlines():
        line = line.strip()
        match = PG_RE.fullmatch(line)
        if not match:
            if re.match(r"^\d+\.[0-9a-f]+\s", line):
                raise ValueError("OSDMAP_PLACEMENT_PARSE_FAILED")
            continue
        values = match.groups()
        if values[0] in rows:
            raise ValueError("OSDMAP_DUPLICATE_PG")
        row = {}
        for name, pos in (("raw", 1), ("up", 3), ("acting", 5)):
            row[name] = [int(x) for x in values[pos].split(",")] if values[pos] else []
            row[name + "_primary"] = int(values[pos + 1])
            assigned = [x for x in row[name] if x not in UNASSIGNED]
            if len(set(assigned)) != len(assigned) or any(x < 0 for x in assigned):
                raise ValueError("OSDMAP_PLACEMENT_MEMBERS_INVALID")
            if row[name + "_primary"] not in UNASSIGNED and row[name + "_primary"] not in assigned:
                raise ValueError("OSDMAP_PLACEMENT_PRIMARY_INVALID")
        rows[values[0]] = row
    if len(rows) != expected:
        raise ValueError("OSDMAP_INCOMPLETE_PG_COVERAGE")
    return rows


def mapping_diagnostics(rows, pools, osd_ids):
    """An undersized mapping is evidence, not a healthy placement assertion."""
    sizes = {p["pool"]: p["size"] for p in pools}
    allowed = set(osd_ids)
    warnings = []
    for pgid, row in rows.items():
        pool = int(pgid.split(".")[0])
        for name in ("raw", "up", "acting"):
            assigned = [x for x in row[name] if x not in UNASSIGNED]
            if any(x not in allowed for x in assigned):
                raise ValueError("OSDMAP_PLACEMENT_OSD_UNKNOWN")
            if len(row[name]) > sizes[pool]:
                raise ValueError("OSDMAP_PLACEMENT_SIZE_INVALID")
            if len(assigned) < sizes[pool]:
                warnings.append({"pgid": pgid, "set": name, "code": "UNDERSIZED_MAPPING",
                                 "expected_members": sizes[pool], "assigned_members": len(assigned)})
    return warnings


def compare_placements(before, after, osd_ids, placement_set="acting"):
    if set(before) != set(after):
        raise ValueError("OSDMAP_SCOPE_MISMATCH")
    counts = {x: {"osd_id": x, "before_pg": 0, "after_pg": 0, "before_primary": 0, "after_primary": 0} for x in osd_ids}
    changes = []
    for pgid, left in before.items():
        right = after[pgid]
        for label, row in (("before", left), ("after", right)):
            for osd in row[placement_set]:
                if osd in counts:
                    counts[osd][label + "_pg"] += 1
            if row[placement_set + "_primary"] in counts:
                counts[row[placement_set + "_primary"]][label + "_primary"] += 1
        if left != right:
            membership = any(set(left[k]) != set(right[k]) for k in ("raw", "up", "acting"))
            order = any(left[k] != right[k] and set(left[k]) == set(right[k]) for k in ("raw", "up", "acting"))
            primary = any(left[k + "_primary"] != right[k + "_primary"] for k in ("raw", "up", "acting"))
            changes.append({"pgid": pgid, "before": left, "after": right,
                            "membership_changed": membership, "order_changed": order, "primary_changed": primary})
    for row in counts.values():
        row["delta_pg"] = row["after_pg"] - row["before_pg"]
        row["delta_primary"] = row["after_primary"] - row["before_primary"]
    return {"summary": {"changed_pgs": len(changes),
                        "membership_changes": sum(x["membership_changed"] for x in changes),
                        "order_changes": sum(x["order_changed"] for x in changes),
                        "primary_changes": sum(x["primary_changed"] for x in changes)},
            "pg_changes": changes, "osd_distribution": [counts[x] for x in sorted(counts)]}


def tool_identity():
    result = {}
    for name, path in (("osdmaptool", TOOL), ("crushtool", CRUSH_TOOL)):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        result[name + "_sha256"] = digest.hexdigest()
    return result


def simulate(request, directory, tool_version):
    raw = base64.b64decode(request["map"], validate=True)
    if not 0 < len(raw) <= MAX_MAP or hashlib.sha256(raw).hexdigest() != request["base_sha256"]:
        raise ValueError("OSDMAP_HASH_OR_SIZE_INVALID")
    baseline = directory / "base.osdmap"
    with baseline.open("xb") as handle:
        handle.write(raw)
    os.chmod(str(baseline), 0o400)
    decoded = json.loads(run_tool([str(baseline), "--dump", "json"], directory))
    if decoded.get("fsid") != request["fsid"]:
        raise ValueError("OSDMAP_FSID_MISMATCH")
    pools = decoded.get("pools", [])
    chosen_pool = request.get("pool_id")
    if chosen_pool is not None and chosen_pool not in [p["pool"] for p in pools]:
        raise ValueError("OSDMAP_POOL_NOT_FOUND")
    scoped = [p for p in pools if chosen_pool is None or p["pool"] == chosen_pool]
    if "allowed_pool_ids" in request and any(p["pool"] not in request["allowed_pool_ids"] for p in scoped):
        # Re-check the decoded binary: the cluster may create a pool between
        # the API's allowlist read and map export.
        raise ValueError("OSDMAP_POOL_SCOPE_REJECTED")
    # EC shard semantics do not share the replicated-pool acceptance suite.
    # Never label an untested EC run as a supported successful preview.
    if any(p.get("type") != 1 for p in scoped):
        raise ValueError("OSDMAP_POOL_TYPE_UNSUPPORTED")
    if any(type(p.get("pg_num")) is not int or type(p.get("size")) is not int
           or p["pg_num"] <= 0 or p["size"] <= 0 for p in scoped):
        raise ValueError("OSDMAP_POOL_SCHEMA_INVALID")
    expected = sum(p["pg_num"] for p in scoped)
    if not 0 < expected <= MAX_PGS or any(p["size"] >= 30 for p in scoped):
        raise ValueError("OSDMAP_SCOPE_LIMIT")
    expected_pgids = {"{}.{}".format(p["pool"], format(i, "x")) for p in scoped for i in range(p["pg_num"])}
    osd_ids = [o["osd"] for o in decoded.get("osds", [])]
    if any(type(x) is not int or x < 0 for x in osd_ids) or len(set(osd_ids)) != len(osd_ids):
        raise ValueError("OSDMAP_OSD_SCHEMA_INVALID")
    changes = request["changes"]
    if not 0 < len(changes) <= 128 or len({x["osd_id"] for x in changes}) != len(changes):
        raise ValueError("OSDMAP_CHANGES_INVALID")
    for change in changes:
        weight = change["crush_weight"]
        if type(change["osd_id"]) is not int or change["osd_id"] not in osd_ids or type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 32767:
            raise ValueError("OSDMAP_CHANGES_INVALID")
    scope = [] if chosen_pool is None else ["--pool", str(chosen_pool)]
    before_crush_file, after_crush_file = directory / "before.crush", directory / "after.crush"
    before_text = run_tool([str(baseline), "--test-map-pgs-dump-all", "--export-crush", str(before_crush_file)] + scope, directory)
    before_crush = json.loads(run_tool(["-i", str(before_crush_file), "--dump", "-f", "json"], directory, CRUSH_TOOL))
    weights = ",".join("{}:{:.8f}".format(x["osd_id"], x["crush_weight"]) for x in changes)
    after_text = run_tool([str(baseline), "--adjust-crush-weight", weights, "--test-map-pgs-dump-all", "--export-crush", str(after_crush_file)] + scope, directory)
    after_crush = json.loads(run_tool(["-i", str(after_crush_file), "--dump", "-f", "json"], directory, CRUSH_TOOL))
    def leaf_weights(crush):
        return {item['id']: item['weight'] for bucket in crush['buckets'] for item in bucket['items'] if item['id'] >= 0}
    before_weights, after_weights = leaf_weights(before_crush), leaf_weights(after_crush)
    effective = []
    for change in changes:
        osd = change['osd_id']
        quantized = int(struct.unpack('f', struct.pack('f', float('{:.8f}'.format(change['crush_weight']))))[0] * 65536)
        if osd not in before_weights or after_weights.get(osd) != quantized:
            raise ValueError('OSDMAP_WEIGHT_CHANGE_NOT_VERIFIED')
        effective.append({'osd_id': osd, 'requested': change['crush_weight'], 'before': before_weights[osd] / 65536,
                          'effective_after': after_weights[osd] / 65536})
    if hashlib.sha256(baseline.read_bytes()).hexdigest() != request["base_sha256"]:
        raise ValueError("OSDMAP_BASELINE_CHANGED")
    before, after = parse_placements(before_text, expected), parse_placements(after_text, expected)
    if set(before) != expected_pgids or set(after) != expected_pgids:
        raise ValueError("OSDMAP_PG_SCOPE_INVALID")
    before_warnings = mapping_diagnostics(before, scoped, osd_ids)
    after_warnings = mapping_diagnostics(after, scoped, osd_ids)
    result = compare_placements(before, after, osd_ids)
    result.update({"base_epoch": decoded["epoch"], "tool_version": tool_version,
                   "parser_version": PARSER_VERSION, "tool_binary_sha256": tool_identity(),
                   "mapping_validation": {"quality": "PARTIAL" if before_warnings or after_warnings else "VALID",
                                          "before_warnings": before_warnings, "after_warnings": after_warnings,
                                          "failure_domain_checked": False},
                   "osd_distribution_by_set": {name: compare_placements(before, after, osd_ids, name)["osd_distribution"]
                                               for name in ("raw", "up", "acting")},
                   "crush_effects": {"weight_set_semantics": "native_pacific_sync_changed_items_and_parent_weights",
                       "weight_sets_changed": before_crush.get('choose_args') != after_crush.get('choose_args'),
                       "effective_weights": effective,
                       "before_choose_args_sha256": hashlib.sha256(json.dumps(before_crush.get('choose_args'), sort_keys=True).encode()).hexdigest(),
                       "after_choose_args_sha256": hashlib.sha256(json.dumps(after_crush.get('choose_args'), sort_keys=True).encode()).hexdigest()},
                   "scope": {"pool_id": chosen_pool, "pool_ids": [p["pool"] for p in scoped],
                             "pool_types": ["replicated"], "pg_count": expected},
                   "output_sha256": {"before": hashlib.sha256(before_text.encode()).hexdigest(),
                                     "after": hashlib.sha256(after_text.encode()).hexdigest(),
                                     "before_crush": hashlib.sha256(before_crush_file.read_bytes()).hexdigest(),
                                     "after_crush": hashlib.sha256(after_crush_file.read_bytes()).hexdigest()},
                   "placement_sha256": {"before": hashlib.sha256(json.dumps(before, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                                        "after": hashlib.sha256(json.dumps(after, sort_keys=True, separators=(",", ":")).encode()).hexdigest()},
                   "candidate_persisted": False})
    return result


def atomic_json(path, payload):
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_OUTPUT:
        raise ValueError("OSDMAP_OUTPUT_LIMIT")
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        handle.write(encoded)
    temporary.replace(path)


def main():
    spool = Path(os.environ.get("OSDMAP_PREVIEW_SPOOL", "/spool"))
    spool.mkdir(parents=True, exist_ok=True)
    version = run_tool(["--version"], spool).strip()
    if not re.search(r"\b16\.2\.15\b", version):
        raise ValueError("Only the tested Ceph 16.2.15 adapter is enabled")
    binaries = tool_identity()
    # Pacific crushtool has no --version action. Pin both binaries from the
    # tested amd64 base image rather than inferring its version from a name.
    if binaries != EXPECTED_TOOL_SHA256:
        raise ValueError("Only the tested Ceph 16.2.15 amd64 tool binaries are enabled")
    while True:
        atomic_json(spool / "capabilities.json", {"available": True, "tool_version": version,
                    "operations": ["crush_weight"], "pool_types": ["replicated"],
                    "parser_version": PARSER_VERSION, "tool_binary_sha256": binaries, "heartbeat": time.time()})
        for job in sorted(spool.iterdir()):
            try:
                UUID(job.name)
            except ValueError:
                continue
            if job.is_symlink() or not job.is_dir() or job.parent != spool:
                continue
            source = job / "request.json"
            if not source.exists() or source.is_symlink() or (job / "result.json").exists():
                continue
            try:
                if source.stat().st_size > MAX_OUTPUT:
                    raise ValueError("OSDMAP_INPUT_LIMIT")
                request = json.loads(source.read_text())
                if time.time() - request["queued_at"] > 300:
                    raise ValueError("OSDMAP_REQUEST_EXPIRED")
                with tempfile.TemporaryDirectory(prefix="osdmap-") as scratch:
                    result = simulate(request, Path(scratch), version)
                if job.is_dir():
                    atomic_json(job / "result.json", {"ok": True, "result": result})
            except Exception as exc:
                code = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("OSDMAP_") else "OSDMAP_WORKER_FAILED"
                if job.is_dir():
                    atomic_json(job / "result.json", {"ok": False, "code": code})
        time.sleep(0.25)


if __name__ == "__main__":
    main()
