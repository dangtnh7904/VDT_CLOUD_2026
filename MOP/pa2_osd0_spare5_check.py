#!/usr/bin/env python3
"""Offline snapshot checks for the PA2 osd.0 -> osd.5 lab MOP.

No cluster commands or network calls. Exit 0 means only the named snapshot
check passed; 1 means HOLD (invalid/unsafe evidence), 3 means WAIT (a narrowly
recognized transient). These checks do not prove live identity, capacity, QoS,
weight-set behavior, scrub start, or uninterrupted mapping across snapshots.
Requires Python 3.6 or later; no third-party packages.
"""
import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


class Wait(Exception):
    pass


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def mapping(row):
    pg = row.get("pgid", "unknown")
    result = {}
    for key in ("up", "acting"):
        ids = row.get(key)
        need(isinstance(ids, list) and ids and all(type(i) is int and i >= 0 for i in ids), pg + ": invalid " + key)
        need(len(ids) == len(set(ids)), pg + ": duplicate OSD in " + key)
        primary = row.get(key + "_primary")
        need(type(primary) is int and primary in ids, pg + ": missing/invalid " + key + "_primary")
        result[key] = ids
        result[key + "_primary"] = primary
    return result


def state(row):
    value = row.get("state")
    need(isinstance(value, str) and value, row["pgid"] + ": missing state")
    return set(value.split("+"))


def stable(row):
    current = mapping(row)
    need(state(row) == {"active", "clean"}, row["pgid"] + ": requires completed active+clean, got " + row["state"])
    need(current["up"] == current["acting"] and current["up_primary"] == current["acting_primary"], row["pgid"] + ": up/acting not converged")
    return current


def pgs(document):
    need(isinstance(document, dict), "PG dump must be an object")
    rows = document.get("pg_stats")
    if rows is None:
        rows = document.get("pg_map", {}).get("pg_stats")
    need(isinstance(rows, list) and rows, "Missing or empty pg_stats: cannot prove coverage/isolation")
    result = {}
    for row in rows:
        need(isinstance(row, dict), "Invalid PG row")
        pg = row.get("pgid")
        need(isinstance(pg, str) and re.fullmatch(r"\d+\.[0-9a-f]+", pg), "Invalid PG ID")
        need(pg not in result, "Duplicate PG ID " + pg)
        mapping(row)
        state(row)
        result[pg] = row
    return result


def indexed(rows, key, label):
    need(isinstance(rows, list) and rows, "Missing " + label)
    result = {}
    for row in rows:
        need(isinstance(row, dict) and type(row.get(key)) is int, "Invalid " + label)
        need(row[key] not in result, "Duplicate " + label + " ID")
        result[row[key]] = row
    return result


def topology(crush):
    buckets = indexed(crush.get("buckets"), "id", "CRUSH buckets")
    devices = indexed(crush.get("devices"), "id", "CRUSH devices")
    types = {r["type_id"]: r["name"] for r in crush["types"]}

    def descendants(item, visited=None):
        visited = set() if visited is None else visited
        need(item not in visited, "CRUSH hierarchy cycle")
        if item >= 0:
            need(item in devices, "Unknown CRUSH device " + str(item))
            return {item}
        need(item in buckets, "Unknown CRUSH bucket " + str(item))
        result = set()
        for child in buckets[item]["items"]:
            result.update(descendants(child["id"], visited | {item}))
        return result

    hosts = {}
    for bucket in buckets.values():
        if types.get(bucket["type_id"]) == "host" and "~" not in bucket["name"]:
            for osd in descendants(bucket["id"]):
                need(osd not in hosts, "OSD has multiple base host parents: " + str(osd))
                hosts[osd] = bucket["name"]
    return hosts, descendants


def references(entry, target):
    for key in ("osds", "acting", "up"):
        if target in entry.get(key, []):
            return True
    if entry.get("primary") == target or entry.get("osd") == target:
        return True
    return any(pair.get("from") == target or pair.get("to") == target for pair in entry.get("mappings", []))


def make_plan(args):
    rows, om, crush = pgs(read(args.pgs)), read(args.osdmap), read(args.crush)
    pools = indexed(om.get("pools"), "pool", "pools")
    osds = indexed(om.get("osds"), "osd", "OSDs")
    rules = indexed(crush.get("rules"), "rule_id", "CRUSH rules")
    expected_ids = set()
    for pool in pools.values():
        need(type(pool.get("pg_num")) is int and pool["pg_num"] > 0, "Invalid pg_num")
        for key in ("pg_num_target", "pg_num_pending"):
            need(pool.get(key, pool["pg_num"]) == pool["pg_num"], "PG split/merge not stable for pool " + str(pool["pool"]))
        expected_ids.update(str(pool["pool"]) + "." + format(n, "x") for n in range(pool["pg_num"]))
    need(set(rows) == expected_ids, "Full PG coverage differs from pool pg_num; missing=" + str(sorted(expected_ids-set(rows))) + ", extra=" + str(sorted(set(rows)-expected_ids)))
    hosts, descendants = topology(crush)
    before, handoff, exceptions = {}, {}, []
    for pg, row in rows.items():
        before[pg] = stable(row)
        need(5 not in row["up"], pg + ": spare 5 already has membership; reconcile existing run")
        pool = pools[int(pg.split(".")[0])]
        need(pool.get("type") == 1, pg + ": helper supports replicated pools only")
        size, minimum = pool.get("size"), pool.get("min_size")
        need(type(size) is int and type(minimum) is int and 1 <= minimum <= size, pg + ": invalid size/min_size")
        need(len(row["up"]) == size, pg + ": mapping cardinality differs from pool size")
        if 0 not in row["up"]:
            continue
        need(row["acting_primary"] != 0, pg + ": transfer actual primary away from 0 before bind")
        rule = rules[pool["crush_rule"]]
        steps = rule["steps"]
        need(len(steps) == 3 and steps[0]["op"] == "take" and steps[2]["op"] == "emit", pg + ": unsupported CRUSH rule shape")
        selector = steps[1]
        host_rule = selector.get("op") == "chooseleaf_firstn" and selector.get("type") == "host"
        osd_rule = selector.get("op") == "choose_firstn" and selector.get("type") == "osd"
        need(selector.get("num") == 0 and (host_rule or osd_rule), pg + ": supports chooseleaf firstn host or choose firstn osd only")
        need(not osd_rule or args.allow_host_colocation, pg + ": OSD failure domain requires --allow-host-colocation lab acknowledgement")
        desired = [5 if osd == 0 else osd for osd in row["up"]]
        need(len(desired) == size and len(set(desired)) == size, pg + ": invalid desired replica cardinality")
        need(set(row["up"]) <= descendants(steps[0]["item"]), pg + ": source mapping outside rule take root/class")
        need(set(desired) <= descendants(steps[0]["item"]), pg + ": destination outside rule take root/class")
        need(all(osd in hosts for osd in desired), pg + ": missing base host parent")
        collocated = {host: [osd for osd in desired if hosts[osd] == host] for host in {hosts[osd] for osd in desired}}
        collocated = {host: members for host, members in collocated.items() if len(members) > 1}
        need(not collocated or not host_rule, pg + ": host rule rejects collocation " + str(collocated) + "; acknowledgement cannot override CRUSH")
        if collocated:
            exceptions.append({"pgid": pg, "hosts": collocated, "rule_id": pool["crush_rule"]})
        handoff[pg] = {"before": row["up"], "expected": desired, "primary": row["acting_primary"], "pool": pool["pool"], "size": size, "min_size": minimum, "rule_id": pool["crush_rule"], "rule": rule, "host_colocation": collocated}
    need(handoff, "No PG contains source osd.0")
    for name in ("pg_upmap", "pg_upmap_items", "pg_temp", "primary_temp"):
        entries = om.get(name, [])
        need(isinstance(entries, list), "Invalid " + name)
        for entry in entries:
            need(entry.get("pgid") not in handoff and not references(entry, 5), "Existing " + name + " conflicts with handoff/spare: " + str(entry))
    used = {osd for row in rows.values() for osd in row["up"]} | {0, 5}
    identities = {}
    for osd in used:
        need(osd in osds, "OSD absent from OSDMap: " + str(osd))
        info = osds[osd]
        need(info.get("up") == 1 and info.get("in") == 1 and number(info.get("weight")) and info["weight"] > 0, "OSD must be up/in with positive override reweight: " + str(osd))
        need(isinstance(info.get("uuid"), str) and info["uuid"], "Missing OSD UUID: " + str(osd))
        identities[str(osd)] = info["uuid"]
    need(isinstance(om.get("fsid"), str) and om["fsid"], "Missing cluster FSID")
    plan = {"schema": 1, "source": 0, "destination": 5, "fsid": om["fsid"], "osdmap_epoch": om.get("epoch"), "osd_uuids": identities, "pools": list(pools.values()), "crush_sha256": digest(crush), "pools_sha256": digest(list(pools.values())), "baseline": before, "handoff": handoff, "allow_host_colocation": args.allow_host_colocation, "host_colocation_exceptions": exceptions, "limitations": "Offline placement plan only; live admission, weight sets, digest, capacity, QoS and PRE/POST scrub require separate evidence."}
    with open(args.out, "x", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print("OFFLINE PLAN CHECK:", len(rows), "PGs covered;", len(handoff), "handoff PGs;", len(exceptions), "lab host-colocation exceptions. No live admission proven.")


def progress(args):
    rows, plan = pgs(read(args.pgs)), read(args.plan)
    need(plan.get("schema") == 1 and plan.get("source") == 0 and plan.get("destination") == 5, "Unsupported plan")
    baseline, handoff = plan["baseline"], plan["handoff"]
    need(set(rows) == set(baseline), "PG set changed; new/removed PGs require plan revision")
    lines = [line.strip() for line in Path(args.accepted).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    accepted = set(lines)
    need(len(accepted) == len(lines), "Duplicate accepted PG")
    need(accepted <= set(handoff), "Accepted list includes PG outside handoff")
    need(args.pending is None or args.pending in handoff and args.pending not in accepted, "Pending PG invalid/already accepted")
    waiting = []
    for pg, row in rows.items():
        actual = mapping(row)
        current_state = state(row)
        moved = pg in accepted or pg == args.pending
        expected = handoff[pg]["expected"] if moved else baseline[pg]["up"]
        promotion = moved and args.allow_destination_primary
        for key in ("up", "acting"):
            if promotion:
                need(set(actual[key]) == set(expected), pg + ": unexpected membership after promotion: " + str(actual[key]))
            elif pg == args.pending:
                need(actual[key] in (baseline[pg][key], expected), pg + ": unexpected mapping while pending: " + str(actual[key]))
            else:
                need(actual[key] == expected, pg + ": unexpected " + key + " mapping " + str(actual[key]))
            primary = actual[key + "_primary"]
            if promotion:
                need(primary in expected, pg + ": primary not in desired set")
            else:
                need(primary == baseline[pg][key + "_primary"], pg + ": primary changed unexpectedly")
                need(primary != 5, pg + ": destination became primary during replica validation")
        if current_state == {"active", "clean"}:
            need(actual["up"] == actual["acting"], pg + ": clean PG has different up/acting")
            need(actual["up_primary"] == actual["acting_primary"], pg + ": primary not converged")
            if not promotion and actual["up"] != expected:
                if pg == args.pending and actual["up"] == baseline[pg]["up"]:
                    waiting.append(pg + ": pending mapping not yet observed")
                else:
                    raise ValueError(pg + ": clean mapping differs from expected")
        elif {"active", "clean"} <= current_state and current_state <= {"active", "clean", "scrubbing", "deep"}:
            waiting.append(pg + ": scrub still running")
        elif pg == args.pending and "active" in current_state and current_state <= {"active", "clean", "remapped", "backfilling", "backfill_wait", "recovering", "recovery_wait", "degraded"}:
            waiting.append(pg + ": recovery not yet converged")
        else:
            raise ValueError(pg + ": unexpected PG state " + row["state"])
    if waiting:
        raise Wait("; ".join(waiting))
    print("SNAPSHOT MAPPING CHECK:", len(rows), "PGs; accepted", len(accepted), "; pending", args.pending or "none", "; mode", "post-promotion membership" if args.allow_destination_primary else "exact replica mapping", ". No scrub/identity/QoS acceptance inferred.")


def isolate(args):
    rows = pgs(read(args.pgs))
    hits = [pg for pg, row in rows.items() if args.osd in row["up"] or args.osd in row["acting"]]
    need(not hits, "OSD " + str(args.osd) + " still present in up/acting: " + str(hits))
    print("SNAPSHOT ISOLATION CHECK: osd." + str(args.osd) + " absent from up/acting in " + str(len(rows)) + " supplied PG rows. Full-cluster provenance must be checked separately.")


def timestamp(value):
    need(isinstance(value, str), "Missing timestamp")
    # Python 3.6 has no fromisoformat; its %z also needs +HHMM, not Z/+HH:MM.
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})"
        r"(?:\.(\d{1,6}))?(Z|[+-]\d{2}:?\d{2})", value)
    need(match is not None, "Timestamp requires ISO date/time and explicit timezone")
    base, fraction, offset = match.groups()
    offset = "+0000" if offset == "Z" else offset.replace(":", "")
    normalized = base.replace(" ", "T") + "." + (fraction or "0").ljust(6, "0") + offset
    result = datetime.strptime(normalized, "%Y-%m-%dT%H:%M:%S.%f%z")
    return result.astimezone(timezone.utc)


def scrub(args):
    before, after = read(args.before), read(args.after)
    need(isinstance(before, dict) and isinstance(after, dict), "Single PG stat objects required")
    need(isinstance(before.get("pgid"), str) and before["pgid"] == after.get("pgid"), "Scrub PG identity mismatch/missing")
    stable(before)
    old_map, new_map = mapping(before), mapping(after)
    need(old_map == new_map and old_map["up"] == old_map["acting"] and old_map["up_primary"] == old_map["acting_primary"], "Mapping/primary changed across scrub samples")
    for key in ("num_scrub_errors", "num_deep_scrub_errors", "num_shallow_scrub_errors"):
        value = after.get("stat_sum", {}).get(key)
        need(number(value) and value == 0, "Missing/nonzero scrub error counter: " + key)
    for flag in ("stats_invalid", "dirty_stats_invalid", "omap_stats_invalid"):
        need(after.get(flag, False) is False, "PG stats invalid: " + flag)
    old, new = timestamp(before.get("last_deep_scrub_stamp")), timestamp(after.get("last_deep_scrub_stamp"))
    need(new >= old, "Deep-scrub marker regressed")
    current_state = state(after)
    need({"active", "clean"} <= current_state and current_state <= {"active", "clean", "scrubbing", "deep"}, "PG not active+clean during scrub check: " + after["state"])
    if current_state != {"active", "clean"}:
        raise Wait("Scrub still in progress")
    if new == old:
        raise Wait("No fresh deep-scrub completion marker yet")
    if args.requested:
        need(new >= timestamp(args.requested), "Fresh marker predates this request")
    print("SCRUB MARKER CHECK:", after["pgid"], "fresh completion", after["last_deep_scrub_stamp"], "; same endpoint mapping; three error counters zero. Request/start/log/incarnation evidence remains separate.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action")
    p = commands.add_parser("plan")
    for field in ("pgs", "osdmap", "crush", "out"):
        p.add_argument("--" + field, required=True)
    p.add_argument("--allow-host-colocation", action="store_true")
    p = commands.add_parser("progress")
    for field in ("pgs", "plan", "accepted"):
        p.add_argument("--" + field, required=True)
    p.add_argument("--pending")
    p.add_argument("--allow-destination-primary", action="store_true")
    p = commands.add_parser("isolate")
    p.add_argument("--pgs", required=True)
    p.add_argument("--osd", required=True, type=int)
    p = commands.add_parser("scrub")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--requested")
    args = parser.parse_args(argv)
    if args.action is None:
        parser.error("a subcommand is required: plan, progress, isolate, scrub")
    try:
        {"plan": make_plan, "progress": progress, "isolate": isolate, "scrub": scrub}[args.action](args)
        return 0
    except Wait as error:
        print("WAIT:", error, file=sys.stderr)
        return 3
    except (ValueError, KeyError, TypeError, OSError, IndexError, RecursionError) as error:
        print("HOLD:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
