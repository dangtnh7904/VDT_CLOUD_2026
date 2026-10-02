"""Classify block-device geometry and ID normalization in common runtime."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
findings = {
    "src/common/blkdev.cc": (
        "MSG-011;MSG-012",
        "BlkDev reads queue/optimal_io_size for BlueStore allocation sizing when enabled; device model encoding collapses double underscores, changing reported device IDs on affected hosts.",
    ),
    "src/common/blkdev.h": (
        "MSG-011",
        "BlkDev adds optimal IO size API used by KernelDevice and BlueStore when selecting minimum allocation size.",
    ),
}
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in findings} == set(findings)
for row in rows:
    path = row["path"]
    if path not in findings:
        continue
    assert not row["upgrade_impact"], path
    fid, reason = findings[path]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = fid
    row["impact_reason"] = f"{fid}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
