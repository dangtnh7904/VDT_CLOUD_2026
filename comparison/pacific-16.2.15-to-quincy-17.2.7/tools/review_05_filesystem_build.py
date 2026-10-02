"""Record unconditional std::filesystem requirement in two source files."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
reason = {
    "src/common/ConfUtils.cc": "MSG-025: Source build now requires std::filesystem here instead of accepting experimental/filesystem fallback on older toolchains.",
    "src/global/global_init.cc": "MSG-025: Source build now requires std::filesystem here instead of accepting experimental/filesystem fallback on older toolchains.",
}
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in reason} == set(reason)
for row in rows:
    if row["path"] not in reason:
        continue
    assert row["upgrade_impact"] in {"", "trivial"}, row["path"]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "MSG-025"
    row["impact_reason"] = reason[row["path"]]
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
