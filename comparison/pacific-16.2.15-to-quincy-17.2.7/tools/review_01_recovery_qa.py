"""Record recovery QA scripts whose execution/acceptance path changed."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "qa/standalone/erasure-code/test-erasure-eio.sh": "Test runner enables osd_mclock_override_recovery_settings and extends EC backfill_unfound polling from 100 to 240 iterations.",
    "qa/standalone/osd/osd-recovery-prio.sh": "Priority test forces osd-op-queue=wpq, so it no longer exercises Quincy's default mClock priority behavior.",
    "qa/standalone/osd/osd-recovery-space.sh": "Recovery-space test enables osd_mclock_override_recovery_settings so its osd_max_backfills=10 input remains effective under mClock.",
    "qa/standalone/osd/osd-recovery-stats.sh": "Undersized recovery test extends its polling/timeout loop from 60 to 300 iterations, changing pass/fail timing.",
    "qa/standalone/osd/osd-rep-recov-eio.sh": "Replicated recovery backfill_unfound test extends polling from 100 to 360 iterations, changing pass/fail timing.",
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in affect} == set(affect)
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
