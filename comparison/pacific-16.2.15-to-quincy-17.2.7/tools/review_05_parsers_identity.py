"""Classify inspected command parsers, object identity, lockdep and NUMA hunks."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/common/ceph_argparse.cc": ("MSG-035", "argv_to_vec now returns a fresh vector and asserts argc>0; daemon and client entrypoints call the new startup API."),
    "src/common/ceph_argparse.h": ("MSG-035", "argv_to_vec signature changes from output parameter to returned vector, requiring source rebuild of callers."),
    "src/common/cmdparse.cc": ("MSG-036", "Command descriptions gate boolean req/positional metadata on SERVER_QUINCY and validate CephBool, with legacy bool compatibility paths."),
    "src/common/cmdparse.h": ("MSG-036", "Command getval API accepts string_view and exposes optional/default helpers used by command handlers."),
    "src/common/iso_8601.cc": ("MSG-037", "ISO timestamp formatter accepts caller-selected date/time separators used for RGW v4 x-amz-date."),
    "src/common/iso_8601.h": ("MSG-037", "No-separator timestamp helper feeds RGW signed outbound request date, while default formatting retains separators."),
    "src/common/strtol.cc": ("MSG-038", "C-string strict numeric overloads and exported functions are removed in favor of string_view/template APIs used by command/config parsers."),
    "src/common/strtol.h": ("MSG-038", "Integral parsing now requires charconv/from_chars and drops fallback plus C-string overload declarations, changing source build/API constraints."),
    "src/common/hobject.cc": ("MSG-039", "Escaping of hobject name/key/namespace switches from snprintf to to_chars on persisted/displayed object identity strings."),
    "src/common/hobject.h": ("MSG-039", "Crimson ghobject constructor now interprets incoming key hash as bitwise-reversed via set_bitwise_key_u32 for SeaStore key decode."),
    "src/common/hobject_fmt.h": ("MSG-039", "New fmt formatter for hobject is used by OSD type formatting and can affect object identifiers in diagnostics."),
    "src/common/lockdep.cc": ("MSG-040", "Debug lockdep grows ID space from 4096 to 131072 and changes dependency matrix representation and backtrace type."),
    "src/common/lockdep.h": ("MSG-040", "Lockdep calls become compile-time no-ops without CEPH_DEBUG_MUTEX, changing availability of runtime lock-order diagnostics."),
    "src/common/numa.cc": ("MSG-041", "With DPDK, affinity setter now skips lcore-worker threads while binding other daemon threads."),
}
trivial = {
    "src/common/obj_bencher.cc": "T05-bencher: Adds std namespace imports only; benchmark IO and measurement bodies are unchanged in this hunk.",
    "src/common/obj_bencher.h": "T05-bencher: Qualifies std::ostream and std::string in existing declarations; function types and benchmark behavior are unchanged.",
    "src/common/str_list.cc": "T05-strlist: Return-by-value get_str_vec directly invokes the same for_each_substr lambda previously reached through the output-parameter overload; token sequence is unchanged.",
}
selected = set(affect) | set(trivial)
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    path = row["path"]
    if path not in selected:
        continue
    assert not row["upgrade_impact"], path
    if path in affect:
        fid, reason = affect[path]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[path]
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
