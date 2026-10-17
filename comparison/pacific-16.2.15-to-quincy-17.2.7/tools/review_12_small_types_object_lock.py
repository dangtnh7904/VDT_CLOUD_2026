"""Screen exact RGW spelling diffs and the default Object Lock arithmetic."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
namespace = {
    "src/rgw/rgw_lc_s3.cc",
    "src/rgw/rgw_ldap.cc",
    "src/rgw/rgw_policy_s3.cc",
    "src/rgw/services/svc_otp.cc",
    "src/rgw/rgw_multiparser.cc",
    "src/rgw/services/svc_bilog_rados.cc",
}
qualified = {
    "src/cls/2pc_queue/cls_2pc_queue_client.h",
    "src/cls/fifo/cls_fifo_types.h",
    "src/rgw/rgw_lc_s3.h",
    "src/rgw/rgw_public_access.cc",
    "src/rgw/rgw_resolve.h",
    "src/rgw/rgw_rest_pubsub_common.h",
}
qualified_substitution = {
    "src/cls/2pc_queue/cls_2pc_queue_client.h": ("const string& queue_name", "const std::string& queue_name"),
    "src/cls/fifo/cls_fifo_types.h": ("inline ostream&", "inline std::ostream&"),
    "src/rgw/rgw_lc_s3.h": ("LCExpiration_S3(string _days, string _date", "LCExpiration_S3(std::string _days, std::string _date"),
    "src/rgw/rgw_public_access.cc": ("ostream&", "std::ostream&"),
    "src/rgw/rgw_resolve.h": ("const string& hostname, string& cname", "const std::string& hostname, std::string& cname"),
    "src/rgw/rgw_rest_pubsub_common.h": ("string ", "std::string "),
}
assert qualified_substitution.keys() == qualified
cleanup = {"src/cls/rgw_gc/cls_rgw_gc.cc"}
chrono = {"src/rgw/rgw_log_backing.cc"}
affect = {"src/rgw/rgw_object_lock.cc"}
trivial = namespace | qualified | cleanup | chrono
assert len(trivial) == 14


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


for source in sorted(trivial | affect):
    old, new = changed_lines(source)
    if source in namespace:
        assert not old and new == ["using namespace std;"], source
    elif source in qualified:
        assert len(old) == len(new) and 1 <= len(old) <= 2, source
        before, after = qualified_substitution[source]
        assert all(before in a and a.replace(before, after) == b for a, b in zip(old, new)), source
    elif source in cleanup:
        assert old == ["#define dout_context g_ceph_context", "#define dout_subsys ceph_subsys_rgw"] and not new, source
        target = subprocess.check_output(
            ["git", "-C", str(repo), "show", "v17.2.7:" + source],
            text=True,
            encoding="utf-8",
        )
        assert "dout_context" not in target and "dout_subsys" not in target, source
    elif source in chrono:
        assert old == ["auto r = rgw::cls::fifo::get_meta(dpp, ioctx, oid, nullopt, &info,"], source
        assert new == [
            "using namespace std::chrono_literals;",
            "auto r = rgw::cls::fifo::get_meta(dpp, ioctx, oid, std::nullopt, &info,",
        ], source
    else:
        assert source in affect, source
        assert old == ["int64_t days = get_days();"], source
        assert new == ["using namespace std;", "int days = get_days();"], source

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for source in sorted(trivial | affect):
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source in affect:
        row.update(
            upgrade_impact="affect",
            finding_id="RGW-009",
            impact_reason="RGW-009: Quincy narrows the default Object Lock days accumulator from int64_t to int before multiplying by 86400; accepted long retention can overflow on new object writes.",
        )
    elif source in namespace:
        reason = "RGW-MECH-04: Only adds standard namespace visibility; no request, persistent state or upgrade-validation logic changes."
        row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)
    elif source in qualified:
        reason = "RGW-MECH-04: Only qualifies existing standard-library types with std::; resolved types and behavior are unchanged."
        row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)
    elif source in cleanup:
        reason = "RGW-MECH-04: Removes two unused local logging macro definitions; target file has no references to either macro."
        row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)
    else:
        reason = "RGW-MECH-04: Adds chrono literal namespace visibility and qualifies nullopt; FIFO metadata call and control flow are unchanged."
        row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(trivial)} exact mechanical diffs trivial and {len(affect)} Object Lock diff affect")
