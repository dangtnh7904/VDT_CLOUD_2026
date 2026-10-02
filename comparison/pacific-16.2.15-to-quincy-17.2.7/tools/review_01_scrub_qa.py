"""Screen scrub QA changes that alter executed checks or scheduler."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "qa/standalone/scrub/osd-scrub-dump.sh": "Forces wpq scheduler, drops duplicate scrub-sleep argument and narrows PG-state grep to +scrubbing; executed scrub QA differs from target default mClock.",
    "qa/standalone/scrub/osd-scrub-repair.sh": "Auto-repair case forces wpq and changes setup/teardown; scrub-warning case accepts either regular-only or combined regular/deep warning count.",
    "qa/standalone/scrub/osd-scrub-snaps.sh": "Snap-mapper test changes two expected repair-log regexes from flat snap IDs to brace-formatted IDs, changing pass/fail matching.",
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
        row["finding_id"] = "OSD-053"
        row["impact_reason"] = f"OSD-053: {affect[row['path']]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
