"""Classify inspected common diagnostic, cache, timer and no-op hunks."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/common/BackTrace.cc": ("MSG-008", "BackTrace gains Python traceback dump/print implementation used by MGR Python exception crash dumps."),
    "src/common/BackTrace.h": ("MSG-008", "BackTrace becomes polymorphic, C-library trace cap drops 100 to 32 frames, and PyBackTrace is added for MGR crash diagnostics."),
    "src/common/PriorityCache.cc": ("MSG-009", "PriorityCache manager adds shift_bins loop invoked by BlueStore cache age-bin rotation."),
    "src/common/PriorityCache.h": ("MSG-009", "Cache interface exposes shift/import/set/get bins for BlueStore age-bin-based memory balancing."),
    "src/common/Timer.cc": ("MSG-010", "CommonSafeTimer adds real-clock deadline conversion into mono-clock schedule, changing timeout behavior around wall-clock adjustments."),
    "src/common/Timer.h": ("MSG-010", "CommonSafeTimer scheduler clock changes from real_clock to mono_clock while retaining real-clock overload for callers."),
    "src/common/WorkQueue.h": ("MSG-017", "New timeout setters are invoked by FileStore on runtime config changes for filestore_op_thread_timeout and suicide timeout."),
}
trivial = {
    "src/common/Continuation.h": "T05-common-runtime: Renames iterator and structured-binding variables; erases the same inserted processing iterator and in-flight iterator.",
    "src/common/StackStringStream.h": "T05-common-runtime: Marks existing stream override methods final; body and output are unchanged.",
    "src/common/Throttle.cc": "T05-common-runtime: Fixes perf-counter description text and removes unused BackoffThrottle cct initialization; throttle math is unchanged in this hunk.",
    "src/common/armor.c": "T05-common-runtime: Moves const qualifier onto pointer variable in C function parameters; encoded/unencoded byte loops are unchanged.",
    "src/common/armor.h": "T05-common-runtime: Updates pointer-const parameter declarations only; C ABI and armor format are unchanged.",
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
