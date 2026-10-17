"""Record the Keystone 401 authentication-result difference between endpoints."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag, source):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", tag + ":" + source],
        text=True,
        encoding="utf-8",
    )


old = show("v16.2.15", "src/rgw/rgw_auth_keystone.cc")
new = show("v17.2.7", "src/rgw/rgw_auth_keystone.cc")
marker = "/* send request */\n  ret = validate.process(null_yield);"
assert old.count(marker) == 1 and new.count(marker) == 1
old_block = old[old.index(marker) : old.index("/* now parse response */", old.index(marker))]
new_block = new[new.index(marker) : new.index("/* now parse response */", new.index(marker))]
status = "if (validate.get_http_status() =="
error = "if (ret < 0) {"
assert old_block.index(status) < old_block.index(error)
assert new_block.index(error) < new_block.index(status)
assert "return std::make_pair(boost::none, -ERR_SIGNATURE_NO_MATCH);" in old_block
assert "return std::make_pair(boost::none, -ERR_SIGNATURE_NO_MATCH);" in new_block
assert "return result_t::reject(failure_reason);" in old
assert "return result_t::reject(failure_reason);" not in new
assert "return result_t::deny(failure_reason);" in new

errors = show("v17.2.7", "src/rgw/rgw_http_errors.h")
http = show("v17.2.7", "src/rgw/rgw_http_client.cc")
auth = show("v17.2.7", "src/rgw/rgw_auth_s3.h")
assert "case 401:\n      return -EPERM;" in errors
assert "status = rgw_http_error_to_errno(http_status);" in http
assert 'default_order = { "sts", "external", "local" }' in auth

history = subprocess.check_output(
    ["git", "-C", str(repo), "log", "--format=%h", "v17.2.7..v16.2.15", "--", "src/rgw/rgw_auth_keystone.cc"],
    text=True,
    encoding="utf-8",
)
assert "373dbd4da24" in history and "026112f0765" in history

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
row = by_path["src/rgw/rgw_auth_keystone.cc"]
assert row["upgrade_impact"] == "affect" and row["finding_id"] == "RGW-010"
row["finding_id"] = "RGW-010,RGW-011"
row["impact_reason"] += " RGW-011: Quincy tests the negative HTTP client result before Keystone 401 status, turning a specific signature rejection into a generic denied auth result that may fall through to later engines."

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Added RGW-011 to the existing Keystone affecting row")
