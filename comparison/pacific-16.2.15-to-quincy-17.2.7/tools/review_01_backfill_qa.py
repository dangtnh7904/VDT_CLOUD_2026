"""Screen renamed standalone backfill QA scripts by endpoint behavior."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "qa/standalone/osd-backfill/osd-backfill-prio.sh": "Renamed script also forces wpq instead of target default mClock, changing the scheduler exercised by backfill-priority QA.",
    "qa/standalone/osd-backfill/osd-backfill-recovery-log.sh": "Renamed script also enables mClock recovery-setting override so osd_max_backfills=1 remains effective in QA.",
    "qa/standalone/osd-backfill/osd-backfill-space.sh": "Renamed script also enables mClock recovery-setting override and expands wait_for_not_backfilling from 240 to 1200 in active cases.",
    "qa/standalone/osd-backfill/osd-backfill-stats.sh": "Renamed script also extends EC-backfill polling limit from 60 to 240 iterations, changing QA timeout acceptance.",
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in affect} == set(affect)
assert all(r["status"] == "R" for r in rows if r["path"] in affect)
for row in rows:
    if row["path"] in affect:
        assert not row["upgrade_impact"], row["path"]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "OSD-052"
        row["impact_reason"] = f"OSD-052: {affect[row['path']]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
