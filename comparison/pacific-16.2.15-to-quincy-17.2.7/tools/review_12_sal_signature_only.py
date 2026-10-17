"""Classify exact RGW header/definition signature-only SAL changes."""

import csv
import re
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
expected_pairs = {
    "src/rgw/rgw_asio_frontend.h": 1,
    "src/rgw/rgw_os_lib.cc": 1,
    "src/rgw/rgw_rest_bucket.h": 1,
    "src/rgw/rgw_rest_config.h": 1,
    "src/rgw/rgw_rest_metadata.h": 2,
    "src/rgw/rgw_rest_realm.h": 1,
    "src/rgw/rgw_rest_s3website.h": 3,
    "src/rgw/rgw_rest_usage.h": 1,
    "src/rgw/rgw_rest_user.h": 1,
    "src/rgw/rgw_sync_module_es_rest.h": 1,
    "src/rgw/rgw_sync_module_pubsub_rest.h": 1,
}


def changed_lines(source):
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", source],
        text=True, encoding="utf-8")
    old, new = [], []
    for line in diff.splitlines():
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("-") and line[1:].strip():
            old.append(line[1:])
        if line.startswith("+") and line[1:].strip():
            new.append(line[1:])
    return old, new


for source, count in expected_pairs.items():
    old, new = changed_lines(source)
    assert len(old) == len(new) == count, source
    for before, after in zip(old, new):
        changed = before.replace("rgw::sal::RGWRadosStore", "rgw::sal::Store")
        changed = re.sub(r"(?<![:\w])string\b", "std::string", changed)
        assert changed != before, (source, before)
        assert re.sub(r"\s+", "", changed) == re.sub(r"\s+", "", after), (
            source, before, after)

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in expected_pairs:
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row.update(
        upgrade_impact="trivial", finding_id="",
        impact_reason="RGW-TYPE-03: Exact endpoint diff changes only RGWRadosStore to SAL Store in a declaration/definition or qualifies string with std; no request processing, wire format, or QA acceptance logic changes in this file.")

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(expected_pairs)} exact RGW signature-only rows trivial")
