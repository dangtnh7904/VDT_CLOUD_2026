"""Record reviewed Crimson heartbeat endpoint rows."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/crimson/osd/heartbeat.cc": (
        "Heartbeat startup switches from try_bind to bind with configured retries and delay; heartbeat messenger getters let OSD::_send_boot replace blank advertised front/back IPs with learned public/cluster addresses."
    ),
    "src/crimson/osd/heartbeat.h": (
        "Heartbeat exposes front/back messenger references to OSD::_send_boot for blank-IP replacement; connection send ownership also changes to MessageURef."
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
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "OSD-050"
        row["impact_reason"] = f"OSD-050: {affect[row['path']]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
