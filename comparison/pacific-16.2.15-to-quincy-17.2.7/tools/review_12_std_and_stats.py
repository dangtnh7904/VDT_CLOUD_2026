"""Classify exact standard-type spelling and endpoint-equivalent stats reset diffs."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
standard = {
    "src/rgw/rgw_client_io.h",
    "src/rgw/rgw_compression_types.h",
    "src/rgw/rgw_cors_swift.h",
    "src/rgw/rgw_formats.h",
    "src/rgw/rgw_lib_frontend.h",
    "src/rgw/rgw_meta_sync_status.h",
    "src/rgw/rgw_multi_del.h",
    "src/rgw/rgw_rest_oidc_provider.h",
    "src/rgw/rgw_rest_user_policy.h",
    "src/rgw/rgw_token.h",
    "src/rgw/rgw_worker.h",
    "src/rgw/services/svc_bucket.cc",
    "src/rgw/services/svc_mdlog.h",
    "src/rgw/services/svc_meta.h",
    "src/rgw/services/svc_otp.h",
    "src/rgw/services/svc_sys_obj_core_types.h",
    "src/rgw/services/svc_zone_utils.h",
}
stats = "src/rgw/services/svc_bi_rados.cc"
assert len(standard) == 17


def changed_lines(source):
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", source],
        text=True,
        encoding="utf-8",
    )
    old, new = [], []
    for line in diff.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-") and line[1:].strip():
            old.append(line[1:].strip())
        if line.startswith("+") and line[1:].strip():
            new.append(line[1:].strip())
    return old, new


for source in sorted(standard):
    old, new = changed_lines(source)
    assert old and len(old) == len(new), source
    if source == "src/rgw/rgw_client_io.h":
        old = [line.replace("wanting to to use", "wanting to use") for line in old]
    assert all(a.replace("std::", "") == b.replace("std::", "") for a, b in zip(old, new)), source
    assert any(a != b for a, b in zip(old, new)), source

old, new = changed_lines(stats)
assert not old and new == [
    "using namespace std;",
    "result->count = 0;",
    "result->size = 0;",
    "result->size_rounded = 0;",
]

# The stats reset preserves the behavior of the old endpoint after the SAL
# caller changed from an empty temporary RGWBucketEnt to a reused bucket ent.
pacific = subprocess.check_output(
    ["git", "-C", str(repo), "show", "v16.2.15:src/rgw/rgw_bucket.cc"],
    text=True,
    encoding="utf-8",
)
quincy = subprocess.check_output(
    ["git", "-C", str(repo), "show", "v17.2.7:src/rgw/rgw_sal_rados.cc"],
    text=True,
    encoding="utf-8",
)
common = subprocess.check_output(
    ["git", "-C", str(repo), "show", "v17.2.7:src/rgw/rgw_common.h"],
    text=True,
    encoding="utf-8",
)
assert "RGWBucketEnt ent;\n  if (!pent)" in pacific
assert "sync_user_stats(dpp, owner->get_id(), info, y, &ent)" in quincy
assert "RGWBucketEnt()\n    : size(0)," in common

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in sorted(standard | {stats}):
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source == stats:
        reason = "RGW-MECH-05: Reset counters before summing shard stats only offsets the Quincy SAL caller's reused bucket ent; Pacific supplied a fresh zero-initialized ent. No endpoint stats behavior change established."
    else:
        reason = "RGW-MECH-05: Exact net hunk only qualifies standard-library names with std:: (plus one comment typo); resolved types, data and control flow are unchanged."
    row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(standard)} standard-name and 1 endpoint-equivalent stats diff trivial")
