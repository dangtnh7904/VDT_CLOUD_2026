"""Record screened Crimson PG and OpsExecuter endpoint behavior."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/crimson/osd/pg.cc": (
        "OSD-034;OSD-037;OSD-039;OSD-044;OSD-045;OSD-047;OSD-048",
        "PG now publishes retained stats, splits transaction submit/commit, repairs corrupted objects then retries, interrupts ObjectContext access on interval change, rejects peering events with stale sent epochs, and cancels reservations/timers on stop.",
    ),
    "src/crimson/osd/pg.h": (
        "OSD-034;OSD-037;OSD-044;OSD-045;OSD-047;OSD-048",
        "PG API stores published stats, exposes interruptible object access and duplicate-request completion, declares repair_object, stale-event guards and shutdown coordination.",
    ),
    "src/crimson/osd/ops_executer.cc": (
        "OSD-038;OSD-044;OSD-049",
        "OpsExecuter dispatches new CMPXATTR, OMAPRMKEYS and LIST_WATCHERS operations, passes delta_stats into PGBackend and connects watch effects to the owning PG.",
    ),
    "src/crimson/osd/ops_executer.h": (
        "OSD-035;OSD-036;OSD-038;OSD-044;OSD-045;OSD-047",
        "OpsExecuter supports internal request message parameters, per-op stats, interruptible futures and lifetime/rollback handling across submitted and completed transactions.",
    ),
}

with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in affect} == set(affect)
for row in rows:
    if row["path"] in affect:
        assert not row["upgrade_impact"], row["path"]
        finding_ids, reason = affect[row["path"]]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding_ids
        row["impact_reason"] = f"{finding_ids}: {reason}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
