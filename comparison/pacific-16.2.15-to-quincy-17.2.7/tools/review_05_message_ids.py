"""Classify shared message dispatch changes used by MON and MDS paths."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
findings = {
    "src/msg/Message.cc": (
        "MSG-001;MSG-007",
        "Message decoder registers new MON used-pending-keys request and MDS dentry-unlink ACK message, enabling rotation and replica-unlink completion paths.",
    ),
    "src/msg/Message.h": (
        "MSG-001;MSG-007",
        "Defines MON used-pending-keys and MDS dentry-unlink ACK wire IDs; Message also narrows get_data_len return to uint32_t and adds Crimson unique-message factory.",
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
