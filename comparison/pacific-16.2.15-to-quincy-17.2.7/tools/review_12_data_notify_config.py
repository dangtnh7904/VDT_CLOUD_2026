"""Cross-reference the already affecting RGW options row with RGW-003."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "06-config-defaults.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

matches = [row for row in rows if row["path"] == "src/common/options/rgw.yaml.in"]
assert len(matches) == 1
row = matches[0]
assert row["upgrade_impact"] == "affect" and row["finding_id"] == "CFG-008"
assert "RGW-003" not in row["impact_reason"]
row["impact_reason"] += " RGW-003: Same file documents zero rgw_data_notify_interval_msec as disabling multisite notifications; default remains 200."

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Linked RGW notification config row to RGW-003")
