"""Classify the inspected IAM policy unit-test adjustment."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

matches = [row for row in rows if row["path"] == "src/test/rgw/test_rgw_iam_policy.cc"]
assert len(matches) == 1
row = matches[0]
assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
row["upgrade_impact"] = "trivial"
row["finding_id"] = "RGW-002"
row["impact_reason"] = "RGW-002 support: Parse3/Eval3 expected action masks add s3GetBucketEncryption; the remaining hunk renames SAL fixture types. No independent upgrade recipe, runtime, or acceptance gate changes."

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified IAM policy unit-test support row as trivial")
