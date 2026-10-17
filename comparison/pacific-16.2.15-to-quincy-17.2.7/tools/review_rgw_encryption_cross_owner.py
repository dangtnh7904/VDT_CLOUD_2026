"""Link inspected RGW encryption config/build rows to RGW-002."""

import csv
from pathlib import Path


root = Path(__file__).resolve().parents[1]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        return reader.fieldnames, list(reader)


def write(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


config = root / "06-config-defaults.csv"
fields, rows = read(config)
assert fields is not None
matches = [row for row in rows if row["path"] == "src/common/options/rgw.yaml.in"]
assert len(matches) == 1
row = matches[0]
assert row["upgrade_impact"] == "affect" and row["finding_id"] == "CFG-008"
assert "RGW-002" not in row["impact_reason"]
row["impact_reason"] += " RGW-002: Same file also adds SSE-S3 Vault backend and per-bucket key-template options used by bucket default encryption."
write(config, fields, rows)

build = root / "13-build-packaging-submodules.csv"
fields, rows = read(build)
assert fields is not None
matches = [row for row in rows if row["path"] == "src/rgw/CMakeLists.txt"]
assert len(matches) == 1
row = matches[0]
assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
row["upgrade_impact"] = "affect"
row["finding_id"] = "RGW-002"
row["impact_reason"] = "RGW-002: Target adds rgw_bucket_encryption.cc to librgw_common_srcs, making new S3 bucket-encryption XML/schema code part of RGW build; other build hunks remain for owner-13 review."
write(build, fields, rows)

print("Linked RGW encryption config and build rows")
