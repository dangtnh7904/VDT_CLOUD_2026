"""Classify RGW Beast metadata header separator handling."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

new = {
    "src/rgw/rgw_asio_client.cc": "RGW-008: Beast header-to-environment mapping now converts wire underscores to hyphens, preserving distinction from wire hyphens for metadata; other hunk needs review.",
    "src/rgw/rgw_auth_s3.cc": "RGW-008: SigV4 signed-header environment lookup applies matching underscore/hyphen swap, affecting signed requests with underscore headers; other auth hunks need review.",
}
for source, reason in new.items():
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row.update(upgrade_impact="affect", finding_id="RGW-008", impact_reason=reason)

common = by_path["src/rgw/rgw_common.cc"]
assert common["upgrade_impact"] == "affect" and "RGW-008:" not in common["impact_reason"]
common["impact_reason"] += " RGW-008: init_meta_info swaps environment underscores/hyphens so wire metadata underscores remain underscores in persisted attr names."

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified two metadata-header rows and updated rgw_common.cc")
