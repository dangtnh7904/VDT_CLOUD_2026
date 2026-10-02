"""Classify inspected auth, tracing, runtime and logging hunks."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/auth/AuthServer.h": ("MSG-042", "Removes a virtual AuthServer connection-mode query, changing the C++ vtable/API for out-of-tree auth subclasses or callers; in-tree negotiation retains pick_con_mode."),
    "src/common/Throttle.h": ("MSG-043", "Selects Crimson perf-counter header for Seastar without Alien and removes unused BackoffThrottle state, affecting conditional build/layout."),
    "src/common/ceph_atomic.h": ("MSG-044", "dummy_atomic assignment now returns its value and integral operations use templated SFINAE excluding enums, changing C++ compile/API behavior."),
    "src/common/intrusive_lru.h": ("MSG-045", "LRU destructor no longer calls set_target_size(0), so remaining unreferenced entries are not explicitly evicted during teardown."),
    "src/common/subsys.h": ("MSG-046", "Adds RGW datacache, SeaStore, AlienStore, mClock and exporter log subsystems with independent defaults and config routing."),
    "src/common/tracer.cc": ("MSG-047", "Replaces OpenTracing Jaeger initialization with OpenTelemetry Jaeger exporter and config-gated spans, plus versioned span-context encode/decode."),
    "src/common/tracer.h": ("MSG-047", "Replaces OpenTracing span API with OpenTelemetry types and non-Jaeger stubs used by OSD/RGW tracing call sites."),
    "src/common/util.cc": ("MSG-048", "Cgroup memory-limit probing is now Linux-only; non-Linux Unix builds return zero without touching Linux cgroup paths."),
    "src/log/LogClock.h": ("MSG-049", "Uses CMake HAVE_SUSECONDS_T probe instead of preprocessor test on a typedef name, affecting portability of log-clock builds."),
    "src/common/crc32c_ppc_asm.S": ("MSG-050", "POWER8 CRC32C vector assembly gains Clang/local header support and configurable constants/symbols; production entrypoint remains __crc32_vpmsum."),
    "src/common/crc32c_ppc_fast_zero_asm.S": ("MSG-050", "POWER8 append-zeros Barrett constants change and reflected reduction is added, requiring checksum equivalence testing on NULL-buffer path."),
    "src/common/ppc-asm.h": ("MSG-050", "Adds local PPC assembler macros selected by the Clang build path of the CRC32C vector assembly."),
    "src/common/ppc-opcode.h": ("MSG-050", "Adds PPC vector opcode macro definitions used by CRC32C assembly and related toolchain compatibility."),
}
trivial = {
    "src/common/openssl_opts_handler.cc": "T05-openssl: Qualifies existing std::to_string/ostream and suppresses deprecated ENGINE warning; module loading statements are unchanged.",
    "src/log/test.cc": "T05-logtest: Test entrypoint follows the new argv_to_vec signature while passing the same argv range to global_init; test cases are unchanged.",
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
    if row["upgrade_impact"]:
        if path in affect:
            assert row["upgrade_impact"] == "affect" and row["finding_id"] == affect[path][0], path
        else:
            assert row["upgrade_impact"] == "trivial" and row["impact_reason"] == trivial[path], path
        continue
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
