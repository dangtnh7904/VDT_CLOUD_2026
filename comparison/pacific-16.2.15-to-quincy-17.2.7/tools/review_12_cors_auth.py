"""Record the endpoint difference in signed S3 CORS preflight authentication."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
paths = {
    "src/rgw/rgw_auth_keystone.cc",
    "src/rgw/rgw_auth_keystone.h",
    "src/rgw/rgw_rest_s3.cc",
}


def show(tag, source):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", tag + ":" + source],
        text=True,
        encoding="utf-8",
    )


local_old = show("v16.2.15", "src/rgw/rgw_rest_s3.cc")
local_new = show("v17.2.7", "src/rgw/rgw_rest_s3.cc")
assert '/* Ignore signature for HTTP OPTIONS */\n  if (s->op_type == RGW_OP_OPTIONS_CORS)' in local_old
assert '/* Ignore signature for HTTP OPTIONS */' not in local_new
assert 'return result_t::deny(-ERR_SIGNATURE_NO_MATCH);' in local_new

key_old = show("v16.2.15", "src/rgw/rgw_auth_keystone.cc")
key_new = show("v17.2.7", "src/rgw/rgw_auth_keystone.cc")
assert 'bool ignore_signature = (s->op_type == RGW_OP_OPTIONS_CORS);' in key_old
assert 'if (ignore_signature) {' in key_old
assert 'signature, signature_factory, ignore_signature);' in key_old
assert 'bool ignore_signature = (s->op_type == RGW_OP_OPTIONS_CORS);' not in key_new
assert 'if (ignore_signature) {' not in key_new
assert 'signature, signature_factory);' in key_new

header_old = show("v16.2.15", "src/rgw/rgw_auth_keystone.h")
header_new = show("v17.2.7", "src/rgw/rgw_auth_keystone.h")
assert 'bool ignore_signature) const;' in header_old
assert 'bool ignore_signature) const;' not in header_new

commit = subprocess.check_output(
    ["git", "-C", str(repo), "log", "--format=%h", "v17.2.7..v16.2.15", "--", "src/rgw/rgw_auth_keystone.cc"],
    text=True,
    encoding="utf-8",
)
assert "34c71dadba0" in commit

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in sorted(paths):
    row = by_path[source]
    if source == "src/rgw/rgw_rest_s3.cc":
        assert row["upgrade_impact"] == "affect" and row["finding_id"] == "RGW-002", source
        row["finding_id"] = "RGW-002,RGW-010"
        row["impact_reason"] += " RGW-010: Local S3 auth in Quincy checks the signature of signed CORS OPTIONS; Pacific skips it after key lookup."
    else:
        assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
        row.update(
            upgrade_impact="affect",
            finding_id="RGW-010",
            impact_reason="RGW-010: Pacific's warm-cache Keystone EC2 auth skips signature comparison for CORS OPTIONS, while Quincy has no ignore_signature path; signed preflight may differ during mixed-version rollout.",
        )

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Recorded RGW-010 on Keystone source/header and existing RGW-002 REST S3 row")
