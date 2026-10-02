"""Classify inspected initialization, timing and platform compatibility hunks."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/common/common_init.cc": ("MSG-014", "common_preinit now fills an empty host setting from short hostname, affecting Graylog/log metadata and effective runtime config."),
    "src/common/code_environment.cc": ("MSG-030", "Process-name discovery switches from prctl to pthread_getname_np where supported; global_init uses the resulting diagnostic name."),
    "src/common/compat.cc": ("MSG-031", "Sensitive-buffer erasure chooses memset_s through CMake HAVE_MEMSET_S instead of __STDC_LIB_EXT1__; RBD encryption callers use ceph_memzero_s."),
    "src/common/condition_variable_debug.h": ("MSG-010", "Debug condition-variable waits now convert steady-clock deadlines to realtime before pthread_cond_timedwait."),
    "src/common/ceph_time.h": ("MSG-032", "Windows builds retain platform-provided coarse clock constants instead of unconditionally aliasing them to precise clocks."),
    "src/common/allocator.h": ("MSG-033", "Legacy custom allocator fallback for old tcmalloc is removed; RBD completion and crypto queues now use default Boost allocator."),
    "src/common/async/context_pool.h": ("MSG-034", "io_context_pool worker lambda loses noexcept, changing how uncaught ioctx.run exceptions reach thread termination in OSD/MGR/global init."),
}
trivial = {
    "src/common/ceph_crypto.cc": "T05-crypto: Adds compiler diagnostic push/pop to silence OpenSSL deprecated API warnings; crypto calls and return values are unchanged.",
    "src/common/ceph_crypto.h": "T05-crypto: Adds compiler warning suppression around existing declarations; no changed cryptographic operation or signature.",
    "src/common/ceph_time.cc": "T05-time: Changes exact_timespan_str formatting and digit separators; only in-tree call is config test, while numeric duration and clock calculations are unchanged.",
    "src/common/Tub.h": "T05-removed-helper: Legacy internal Tub template is deleted after all in-tree target includes/usages disappear; no target runtime call path remains in this hunk.",
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
