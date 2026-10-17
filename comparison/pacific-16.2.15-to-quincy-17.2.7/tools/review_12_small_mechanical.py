"""Screen exact, small RGW/CLS spelling and logging net diffs."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
namespace = {
    "src/cls/queue/cls_queue_client.cc",
    "src/cls/queue/cls_queue_src.cc",
    "src/rgw/rgw_arn.cc",
    "src/rgw/rgw_cors_s3.cc",
    "src/rgw/rgw_env.cc",
    "src/rgw/rgw_es_query.cc",
    "src/rgw/rgw_formats.cc",
    "src/rgw/rgw_gc.cc",
    "src/rgw/rgw_jsonparser.cc",
    "src/rgw/rgw_multi_del.cc",
    "src/rgw/rgw_resolve.cc",
    "src/rgw/rgw_tag_s3.cc",
    "src/rgw/rgw_xml.cc",
    "src/rgw/services/svc_cls.cc",
    "src/rgw/services/svc_finisher.cc",
    "src/rgw/services/svc_mdlog.cc",
    "src/rgw/services/svc_meta.cc",
    "src/rgw/services/svc_zone_utils.cc",
}
qualified = {
    "src/rgw/rgw_cors_s3.h",
    "src/rgw/rgw_public_access.h",
    "src/rgw/services/svc_bilog_rados.h",
    "src/rgw/services/svc_config_key.h",
}
checkpoint = {
    "src/rgw/rgw_sync_checkpoint.cc",
    "src/rgw/rgw_sync_checkpoint.h",
}
logging = {"src/rgw/rgw_period_puller.cc"}
all_paths = namespace | qualified | checkpoint | logging
assert len(all_paths) == 25


def changed_lines(source):
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", source],
        text=True,
        encoding="utf-8",
    )
    removed, added = [], []
    for line in diff.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-") and line[1:].strip():
            removed.append(line[1:].strip())
        if line.startswith("+") and line[1:].strip():
            added.append(line[1:].strip())
    return removed, added


for source in sorted(all_paths):
    old, new = changed_lines(source)
    if source in namespace:
        assert not old and new in (["using namespace std;"], ["using std::string;"]), source
    elif source in qualified:
        assert len(old) == len(new) == 1, source
        assert old[0] == new[0].replace("std::", ""), source
    elif source in checkpoint:
        assert old and len(old) == len(new), source
        assert all(a.replace("RGWRadosStore", "RadosStore").replace(" *store", "* store") == b for a, b in zip(old, new)), source
    else:
        assert source in logging and len(old) == len(new) == 2, source
        assert all("lderr(conn->get_ctx())" in line for line in old), source
        assert all("ldpp_dout(dpp, -1)" in line for line in new), source
        assert all(a.split("<<", 1)[1] == b.split("<<", 1)[1] for a, b in zip(old, new)), source

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in sorted(all_paths):
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source in namespace:
        reason = "RGW-MECH-01: Only adds a standard namespace/type using declaration; no request, state, schema or upgrade-validation logic changes."
    elif source in qualified:
        reason = "RGW-MECH-01: Only qualifies existing standard-library type with std::; signature resolves to the same type."
    elif source in checkpoint:
        reason = "RGW-MECH-02: Only renames the SAL RADOS store type in a declaration/definition; checkpoint control flow is unchanged."
    else:
        reason = "RGW-MECH-03: Period pull parse/decode error logs keep the same text and error level, adding request DPP context only."
    row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(all_paths)} exact mechanical RGW/CLS diffs as trivial")
