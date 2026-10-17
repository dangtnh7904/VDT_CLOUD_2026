"""Classify inspected RGW bucket default-encryption implementation rows."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
reasons = {
    "src/rgw/rgw_bucket_encryption.cc": "RGW-002: New S3 bucket-encryption XML parser/formatter persists the default encryption rule consumed by Quincy RGW.",
    "src/rgw/rgw_bucket_encryption.h": "RGW-002: New versioned RGWBucketEncryptionConfig encoding defines the persisted bucket policy schema and SSEAlgorithm/KMS key fields.",
    "src/rgw/rgw_common.cc": "RGW-002: Captures encryption request headers in crypt_attribute_map and maps missing bucket encryption configuration to the S3 error response.",
    "src/rgw/rgw_common.h": "RGW-002: Adds persistent bucket encryption policy/key attribute names, S3 error constant, and request crypto-header map.",
    "src/rgw/rgw_crypt.cc": "RGW-002: Quincy SSE-S3 write/read paths use bucket key and AES256 object mode, which Pacific does not decode as an encrypted mode.",
    "src/rgw/rgw_crypt.h": "RGW-002: Declares SSE-S3 bucket-key cleanup used when deleting a bucket with a generated Vault key.",
    "src/rgw/rgw_kms.cc": "RGW-002: Adds SSE-S3 Vault backend key create/reconstitute/remove paths required for Quincy AES256 bucket-default writes and reads.",
    "src/rgw/rgw_kms.h": "RGW-002: Declares SSE-S3 Vault key operations called by RGW encryption and bucket cleanup.",
    "src/rgw/rgw_op.cc": "RGW-002: Put/Get/DeleteBucketEncryption persist/read/remove bucket policy; bucket deletion also handles generated SSE-S3 key cleanup.",
    "src/rgw/rgw_op.h": "RGW-002: Defines S3 bucket-encryption operations with distinct IAM permissions and read/write operation masks.",
    "src/rgw/rgw_op_type.h": "RGW-002: Adds operation identifiers for bucket-encryption Get/Put/Delete authorization and dispatch.",
    "src/rgw/rgw_rest_s3.cc": "RGW-002: Routes ?encryption to new S3 operations and applies bucket encryption defaults on PUT/POST; Pacific falls through to ordinary bucket operations, including DELETE on empty bucket.",
    "src/rgw/rgw_rest_s3.h": "RGW-002: Adds S3 bucket-encryption REST response types and ?encryption query detection.",
}

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for path, reason in reasons.items():
    matches = [row for row in rows if row["path"] == path]
    assert len(matches) == 1, path
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], path
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "RGW-002"
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(reasons)} RGW bucket-encryption rows")
