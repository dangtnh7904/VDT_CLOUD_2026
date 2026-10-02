"""Record reviewed Crimson metadata wrapper and include-only endpoint hunks."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
trivial = {
    "src/crimson/osd/osd_meta.cc": "OSDMeta calls the same read operations with store. rather than store-> after a non-null reference refactor; keys, errors and decoded metadata are unchanged.",
    "src/crimson/osd/osd_meta.h": "FuturizedStore member and constructor parameter change from pointer to reference only; no on-disk or wire format hunk.",
    "src/crimson/osd/pg_meta.cc": "PGMeta uses the same collection and omap keys through a store reference; read/decode logic is unchanged.",
    "src/crimson/osd/pg_meta.h": "FuturizedStore member and constructor parameter change from pointer to reference only; no persisted metadata hunk.",
    "src/crimson/osd/osd_operations/recovery_subrequest.h": "Header dependency switches from specific PG message includes to MOSDFastDispatchOp; no declaration or request logic changes in this file.",
    "src/crimson/osd/osd_operations/pg_advance_map.h": "Only replaces the handle type with generic PipelineHandle; PGAdvanceMap stages and control flow are unchanged in this hunk; pipeline behavior is tracked in OSD-035.",
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in trivial} == set(trivial)
for row in rows:
    name = row["path"]
    if name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-crimson-meta: {trivial[name]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
