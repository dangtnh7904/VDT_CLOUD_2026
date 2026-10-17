#!/usr/bin/env python3
"""Add the skill-standard binary impact gate without erasing legacy review data."""

from __future__ import annotations

import argparse
import codecs
import csv
import io
from pathlib import Path


LEGACY_AFFECT = {"material", "conditional", "mixed"}
LEGACY_TRIVIAL = {"support", "trivial"}


def expand(*items: int | tuple[int, int]) -> set[int]:
    result: set[int] = set()
    for item in items:
        if isinstance(item, tuple):
            result.update(range(item[0], item[1] + 1))
        else:
            result.add(item)
    return result


def quote_field(value: str) -> str:
    if any(char in value for char in ';"\r\n'):
        return '"' + value.replace('"', '""') + '"'
    return value


def build_explicit_specs() -> dict[int, dict[int, tuple[str, str, str]]]:
    specs: dict[int, dict[int, tuple[str, str, str]]] = {n: {} for n in range(1, 7)}

    def add(
        owner: int,
        indices: set[int],
        impact: str,
        finding_id: str,
        reason: str,
    ) -> None:
        for index in indices:
            if index in specs[owner]:
                raise AssertionError(f"owner {owner:02d}: duplicate mapping for index {index}")
            specs[owner][index] = (impact, finding_id, reason)

    # Owner 01: the affect set is the union of the explicit Owner/evidence ledgers.
    add(1, expand(1578, 1579), "affect", "OSD-002", "EC recovery error handling changes daemon failure and recovery behavior.")
    add(1, expand(1580, 1581), "affect", "OSD-007, OSD-011, OSD-012", "OSD lifecycle, map delivery and mClock restart behavior affect rolling execution.")
    add(1, expand(1582), "affect", "OSD-013", "RBD read-only metadata capability behavior differs by primary version.")
    add(1, expand(1588, 1589), "affect", "OSD-007", "Past-interval and OSDMap trim state changes peering behavior.")
    add(1, expand(1590), "affect", "OSD-012", "Startup, shutdown and recovery-delete handling changes failure behavior.")
    add(1, expand(1591), "affect", "OSD-003, OSD-005", "PGLog trimming and clean-region persistence affect recovery across restart.")
    add(1, expand(1592), "affect", "OSD-003", "PGLog duplicate guards affect restart and recovery observability.")
    add(1, expand(1593, 1594), "affect", "OSD-001, OSD-006, OSD-007", "Peering and recovery selection differs while primaries move during rolling upgrade.")
    add(1, expand(1595, 1596), "affect", "OSD-008, OSD-014", "PrimaryLogPG recovery and manifest semantics affect data correctness.")
    add(1, expand(1597, 1598), "affect", "OSD-004", "Scrub abort and reservation handling affects stabilization.")
    add(1, expand(1599, 1600), "affect", "OSD-010", "Legacy SnapMapper conversion changes object-key recovery correctness.")
    add(1, expand(1601), "affect", "OSD-014", "Manifest reference counting changes recovery correctness.")
    add(1, expand(1604, 1605), "affect", "OSD-005, OSD-007", "Persisted missing and superblock state affects restart and rollback rehearsal.")
    add(1, expand(1606, 1607), "affect", "OSD-004", "Scrub map comparison and abort handling affects stabilization.")
    add(1, expand((1608, 1612)), "affect", "OSD-011", "mClock scheduler capacity handling changes OSD restart behavior when enabled.")
    add(1, expand((1613, 1616)), "affect", "OSD-004", "Scrub state-machine changes affect mixed-primary validation.")
    add(1, expand(1577), "trivial", "", "Private fmt build linkage has no independent package runtime or compatibility path.")
    add(1, expand(1586, 1587, 1602, 1603), "trivial", "", "Diagnostic and read-data lock optimization hunks have no independent upgrade acceptance path.")
    add(1, expand(754, 941, 993, 1034, 1046, 2510, 2511, 2512), "trivial", "", "Test, QA or marker evidence has no independent runtime effect.")

    # Owner 02: every non-P2 source/tool row participates in one or more BS findings.
    add(2, expand((1552, 1557), (1563, 1568), 1574, 1575), "affect", "BS-007", "Allocator behavior changes extent placement and recovery timing.")
    add(2, expand(1558, 1559), "affect", "BS-001, BS-002, BS-006, BS-007, BS-010", "BlueFS log, replay, allocation and metric semantics change after OSD restart.")
    add(2, expand(1560), "affect", "BS-006", "BlueRocks file placement and allocation behavior changes after restart.")
    add(2, expand(1561, 1562), "affect", "BS-003, BS-004, BS-005, BS-006, BS-008, BS-009, BS-010", "BlueStore replay, repair, placement and observability paths affect upgrade safety.")
    add(2, expand(1569, 1570), "affect", "BS-001, BS-006", "BlueFS transaction encoding creates a per-OSD rollback boundary.")
    add(2, expand(1571, 2564, 2565), "affect", "BS-009", "Provisioning and offline tool behavior is upgrade-relevant when the runbook invokes it.")
    add(2, expand(1572, 1573), "affect", "BS-005, BS-008", "BlueStore metadata and shared-blob handling affects repair and correctness.")
    add(2, expand((2426, 2428), (2502, 2509)), "trivial", "", "Repository test evidence has no independent runtime effect.")

    # Owner 03: the build-only row is explicitly screened out in section 4.
    add(3, expand(1099), "trivial", "", "Static internal-library build composition does not alter official package runtime compatibility.")
    add(3, expand(1100), "affect", "KVBD-005", "Block-device open and errno handling changes restart failure behavior.")
    add(3, expand(1272), "affect", "KVBD-001, KVBD-002", "KV iterator bounds and range-delete API change storage behavior.")
    add(3, expand(1273), "affect", "KVBD-001, KVBD-002, KVBD-003, KVBD-004", "RocksDB iterator, reshard and conditional compaction behavior changes.")
    add(3, expand(1274), "affect", "KVBD-001, KVBD-002, KVBD-003", "RocksDB API and reshard behavior changes.")
    add(3, expand(2590), "affect", "KVBD-007", "Offline repair no longer loses its DB handle; tool use remains conditional.")

    # Owner 04: binary labels are derived from the explicit 52-row disposition ledger.
    add(4, expand(1490, 1491), "affect", "MON-004", "CephX rotating-key publication changes Paxos and reconnect behavior.")
    add(4, expand((1493, 1495)), "affect", "MON-011", "Masked config matching can change effective OSD configuration on reconnect.")
    add(4, expand((1496, 1500)), "affect", "MON-003", "MON election and connection tracking changes rolling quorum behavior.")
    add(4, expand(1501, 1502), "affect", "MON-005, MON-008", "CephFS state and pool command behavior changes control-plane validation.")
    add(4, expand(1503, (1506, 1509)), "affect", "MON-009", "MGR and health-store proposal behavior affects control-plane stabilization.")
    add(4, expand(1504, 1505), "affect", "MON-005", "Old FSMap and standby-replay handling changes CephFS failover behavior.")
    add(4, expand(1510), "affect", "CFG-002", "OSD profile gains permission to persist mClock capacity during restart.")
    add(4, expand(1511, 1512), "affect", "MON-004", "MonClient reconnect after auth proposal retry affects upgrade continuity.")
    add(4, expand(1513), "affect", "MON-008", "Command schema changes pool and autoscaler acceptance behavior.")
    add(4, expand((1514, 1518)), "affect", "MON-003, MON-007, MON-009", "MonMap, election and proposal changes affect rolling control-plane state.")
    add(4, expand(1519, 1520), "affect", "MON-001, MON-002, MON-006, MON-007, MON-008", "OSDMap state, release gates and placement commands affect mixed-version safety.")
    add(4, expand(1521, 1522), "affect", "MON-006", "PG merge and map trimming changes placement stabilization.")
    add(4, expand(1523, 1524), "affect", "MON-009", "Paxos service proposal behavior affects post-restart convergence.")
    add(4, expand((1583, 1585)), "affect", "MON-001, MON-002, MON-006, MON-007", "OSDMap encoding and mapping state create feature and rollback boundaries.")
    add(4, expand(2563, 2591), "affect", "MON-010", "Offline recovery tools are upgrade-relevant when explicitly invoked.")
    add(4, expand(1492), "trivial", "", "Build composition has no independent official-package compatibility path.")
    add(4, expand((395, 397), (1061, 1066), (2496, 2498)), "trivial", "", "QA and workunit changes support findings but do not affect a running cluster independently.")

    # Owner 05: mappings follow the explicit 92-row ledger and finding evidence lists.
    add(5, expand(1097, 1098), "affect", "MSG-001", "CephX rotating-key state publication changes auth continuity.")
    add(5, expand(1215, 1216, 1460), "affect", "MSG-003", "OSD lifecycle and mark-down message handling changes restart behavior.")
    add(5, expand(1219, 1224), "affect", "MSG-004", "Buffer and lock safety fixes change daemon abort behavior.")
    add(5, expand(1220, 1221, 1228), "affect", "MSG-005", "Crypto and CRC paths conditionally affect platform compatibility.")
    add(5, expand(1230, 1231, 1237, 1238, 1240), "affect", "MSG-006", "Address binding and MON selection changes startup connectivity.")
    add(5, expand(1246, 1545), "affect", "MSG-007", "Range-blocklist feature and CIDR address encoding create a fleet gate.")
    add(5, expand(1247, 1454, 1455), "affect", "MSG-008", "CephFS request and session encoding changes mixed client/MDS behavior.")
    add(5, expand(1458, (1530, 1532)), "affect", "MSG-009", "MMgrUpdate adds a MON-target to MGR-base compatibility edge.")
    add(5, expand(1533, 1534, 1537), "affect", "MSG-002", "Messenger reconnect and shutdown race fixes affect service continuity.")
    owner5_trivial = expand(
        1096, (1208, 1214), 1217, 1218, 1222, 1223, 1229, (1232, 1234), 1239,
        (1241, 1245), (1251, 1257), 1261, 1262, (1389, 1392), 1452, 1453,
        1456, 1457, 1459, 1461, 1528, 1529, (1535, 1536), (1538, 1544), 1623,
        2398, (2416, 2419), 2421, 2422, (2499, 2501), 2547, 2661,
    )
    add(5, owner5_trivial, "trivial", "", "Support, observability, test or mechanical change has no independent upgrade outcome.")

    # Owner 06: runtime registry/config rows are affect; documentation rows remain support/trivial.
    add(6, expand((1225, 1227)), "affect", "CFG-002", "Config API changes are exercised by mClock capacity handling during OSD restart.")
    add(6, expand(1235, 1236), "affect", "CFG-001, CFG-002, CFG-003, CFG-004, CFG-005, CFG-006, CFG-007", "Option defaults and schema change daemon behavior after role restart.")
    add(6, expand((159, 173)), "trivial", "", "Documentation evidence does not independently change runtime upgrade behavior.")

    return specs


def find_component(directory: Path, owner: int) -> Path:
    matches = sorted(directory.glob(f"{owner:02d}-*.csv"))
    if len(matches) != 1:
        raise AssertionError(f"owner {owner:02d}: expected one CSV, found {matches}")
    return matches[0]


def migrate_file(
    path: Path,
    owner: int,
    explicit: dict[int, tuple[str, str, str]] | None,
    *,
    check_only: bool,
) -> tuple[int, int]:
    raw = path.read_bytes()
    if not raw.startswith(codecs.BOM_UTF8):
        raise AssertionError(f"{path}: expected UTF-8 BOM")
    text = raw[len(codecs.BOM_UTF8):].decode("utf-8")
    physical_lines = text.splitlines()
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    if len(physical_lines) != len(rows) + 1:
        raise AssertionError(f"{path}: embedded newlines are not supported by this preserving migration")
    if not rows:
        raise AssertionError(f"{path}: empty component")

    fieldnames = list(rows[0])
    if fieldnames[:21] != [
        "index", "base_tag", "target_tag", "path", "old_path", "status", "status_detail",
        "additions", "deletions", "binary", "old_mode", "new_mode", "old_blob", "new_blob",
        "group", "owner_report", "priority", "file_type", "review_mode", "analysis_decision", "diff_note",
    ]:
        raise AssertionError(f"{path}: immutable prefix mismatch")

    if explicit is not None:
        actual = {int(row["index"]) for row in rows}
        if actual != set(explicit):
            raise AssertionError(
                f"{path}: explicit ledger mismatch missing={sorted(actual - set(explicit))} "
                f"extra={sorted(set(explicit) - actual)}"
            )
        additions = ["upgrade_impact"]
        if "finding_id" not in fieldnames:
            additions.append("finding_id")
        additions.append("impact_reason")
        values = [explicit[int(row["index"])] for row in rows]
    else:
        required = {"upgrade_disposition", "finding_id", "disposition_reason"}
        if not required.issubset(fieldnames):
            raise AssertionError(f"{path}: missing legacy review fields")
        additions = ["upgrade_impact", "impact_reason"]
        values = []
        for row in rows:
            legacy = row["upgrade_disposition"].strip()
            if legacy in LEGACY_AFFECT:
                impact = "affect"
            elif legacy in LEGACY_TRIVIAL:
                impact = "trivial"
            else:
                raise AssertionError(f"{path}: invalid legacy disposition {legacy!r}")
            values.append((impact, row["finding_id"].strip(), row["disposition_reason"].strip()))

    binary_present = "upgrade_impact" in fieldnames or "impact_reason" in fieldnames
    if binary_present:
        if not {"upgrade_impact", "impact_reason", "finding_id"}.issubset(fieldnames):
            raise AssertionError(f"{path}: partial binary schema")
        affect = 0
        trivial = 0
        for row, (impact, finding_id, reason) in zip(rows, values, strict=True):
            assert row["upgrade_impact"].strip() == impact, (path, row["index"], "upgrade_impact")
            assert row["finding_id"].strip() == finding_id, (path, row["index"], "finding_id")
            assert row["impact_reason"].strip() == reason, (path, row["index"], "impact_reason")
            affect += impact == "affect"
            trivial += impact == "trivial"
        return affect, trivial

    if check_only:
        raise AssertionError(f"{path}: binary impact columns are missing")

    for column in additions:
        if column in fieldnames:
            raise AssertionError(f"{path}: binary column {column!r} already exists; refusing to overwrite")

    output = [physical_lines[0] + ";" + ";".join(additions)]
    affect = 0
    trivial = 0
    for line, row, (impact, finding_id, reason) in zip(physical_lines[1:], rows, values, strict=True):
        if impact == "affect":
            affect += 1
            if not finding_id:
                raise AssertionError(f"{path}: affect index {row['index']} has no finding_id")
        elif impact == "trivial":
            trivial += 1
        else:
            raise AssertionError(f"{path}: invalid impact {impact!r}")
        if not reason:
            raise AssertionError(f"{path}: index {row['index']} has no impact reason")
        if "finding_id" in additions:
            appended = [impact, finding_id, reason]
        else:
            appended = [impact, reason]
        output.append(line + ";" + ";".join(quote_field(value) for value in appended))

    migrated = codecs.BOM_UTF8 + ("\r\n".join(output) + "\r\n").encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".binary-impact.tmp")
    temporary.write_bytes(migrated)
    temporary.replace(path)
    return affect, trivial


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    explicit_specs = build_explicit_specs()

    total_affect = 0
    total_trivial = 0
    for owner in range(1, 16):
        path = find_component(directory, owner)
        affect, trivial = migrate_file(
            path, owner, explicit_specs.get(owner), check_only=args.check_only
        )
        total_affect += affect
        total_trivial += trivial
        print(f"{path.name}: affect={affect} trivial={trivial} total={affect + trivial}")

    if total_affect + total_trivial != 2665:
        raise AssertionError("suite binary totals do not reconcile to the master inventory")
    print(f"suite: affect={total_affect} trivial={total_trivial} total={total_affect + total_trivial}")


if __name__ == "__main__":
    main()
