"""Cross-reference default-enabled allocation-file path in owner 06."""

import csv
from pathlib import Path

csv_path = Path(__file__).resolve().parents[1] / "06-config-defaults.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
row = next(row for row in rows if row["path"] == "src/common/options/global.yaml.in")
assert row["upgrade_impact"] == "affect"
if "CFG-014" not in row["finding_id"]:
    row["finding_id"] += " CFG-014"
    row["impact_reason"] += " CFG-014: default-true bluestore_allocation_from_file gates the new null-FM allocation-file path on eligible OSDs."
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
