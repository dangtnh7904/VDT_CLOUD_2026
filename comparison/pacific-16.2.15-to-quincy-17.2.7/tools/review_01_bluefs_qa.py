"""Record reviewed BlueFS expansion/offline-tool QA scenario."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
target = "qa/standalone/osd/osd-bluefs-volume-ops.sh"
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
matched = [row for row in rows if row["path"] == target]
assert len(matched) == 1 and not matched[0]["upgrade_impact"]
row = matched[0]
row["upgrade_impact"] = "affect"
row["finding_id"] = "OSD-058"
row["impact_reason"] = (
    "OSD-058: QA retries BlueFS spillover generation and adds an offline "
    "allocmap/fsck/bluefs-bdev-expand/qfsck/restart path; script shell syntax "
    "in retry assignment and size comparison needs lab validation before use as an upgrade gate."
)
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
