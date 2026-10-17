"""Verify RGW usage REST scope when a requested bucket cannot be loaded."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


def is_ancestor(commit: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, tag],
        check=False,
    )
    assert result.returncode in (0, 1)
    return result.returncode == 0


zipper_commit = "72d1a363263cf707d022ee756122236ba175cda2"
later_error_check = "ad7c577a6731aa980d78def45f5d0a975915852d"
assert not is_ancestor(zipper_commit, "v16.2.15")
assert is_ancestor(zipper_commit, "v17.2.7")
assert not is_ancestor(later_error_check, "v17.2.7")

base_rest = show("v16.2.15", "src/rgw/rgw_rest_usage.cc")
target_rest = show("v17.2.7", "src/rgw/rgw_rest_usage.cc")
base_usage = show("v16.2.15", "src/rgw/rgw_usage.cc")
target_usage = show("v17.2.7", "src/rgw/rgw_usage.cc")
target_sal_rados = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")

# Pacific forwards the requested uid and bucket filters directly to the usage
# class. It does not require bucket metadata lookup before applying the filter.
assert "RGWUsage::show(this, store->getRados(), uid, bucket_name" in base_rest
assert "RGWUsage::trim(this, store->getRados(), uid, bucket_name" in base_rest
assert "store->read_usage(dpp, uid, bucket_name" in base_usage
assert "store->trim_usage(dpp, uid, bucket_name" in base_usage

# Quincy first loads a SAL bucket for both GET and DELETE, but v17.2.7 ignores
# the return code. Split the two execute() bodies so each route is checked.
get_start = target_rest.index("void RGWOp_Usage_Get::execute")
get_end = target_rest.index("class RGWOp_Usage_Delete", get_start)
delete_start = target_rest.index("void RGWOp_Usage_Delete::execute")
delete_end = target_rest.index("RGWOp *RGWHandler_Usage::op_get", delete_start)
for body in (target_rest[get_start:get_end], target_rest[delete_start:delete_end]):
    assert "store->get_bucket(nullptr, user.get(), std::string(), bucket_name" in body
    assert "op_ret = store->get_bucket" not in body
    assert "if (op_ret < 0)" not in body

# The RADOS SAL loader only assigns the output unique_ptr after load succeeds.
# A negative load result therefore leaves bucket.get() null at the REST caller.
bucket_loader_start = target_sal_rados.index(
    "int RadosStore::get_bucket(const DoutPrefixProvider* dpp, User* u, const rgw_bucket& b"
)
bucket_loader_end = target_sal_rados.index(
    "int RadosStore::get_bucket(User* u, const RGWBucketInfo& i", bucket_loader_start
)
bucket_loader = target_sal_rados[bucket_loader_start:bucket_loader_end]
assert bucket_loader.index("ret = bp->load_bucket") < bucket_loader.index("if (ret < 0)")
assert bucket_loader.index("return ret;") < bucket_loader.index("bucket->reset(bp);")

# The REST route always creates a non-null User object. When the requested
# bucket failed to load, show()/trim() fall back to the whole user. An empty
# user id maps to the all-usage backend call through RadosUser as well.
for body in (target_rest[get_start:get_end], target_rest[delete_start:delete_end]):
    assert "std::unique_ptr<rgw::sal::User> user = store->get_user" in body

show_start = target_usage.index("int RGWUsage::show")
show_end = target_usage.index("int RGWUsage::trim", show_start)
show_body = target_usage[show_start:show_end]
assert show_body.index("if (bucket)") < show_body.index("else if (user)")
assert show_body.index("user->read_usage") < show_body.index("store->read_all_usage")

trim_start = target_usage.index("int RGWUsage::trim")
trim_end = target_usage.index("int RGWUsage::clear", trim_start)
trim_body = target_usage[trim_start:trim_end]
assert trim_body.index("if (bucket)") < trim_body.index("else if (user)")
assert trim_body.index("user->trim_usage") < trim_body.index("store->trim_all_usage")

user_read_start = target_sal_rados.index("int RadosUser::read_usage")
user_read_end = target_sal_rados.index("int RadosUser::trim_usage", user_read_start)
user_read = target_sal_rados[user_read_start:user_read_end]
assert "std::string bucket_name;" in user_read
assert "read_usage(dpp, get_id(), bucket_name" in user_read

user_trim_start = target_sal_rados.index("int RadosUser::trim_usage")
user_trim_end = target_sal_rados.index("int RadosUser::load_user", user_trim_start)
user_trim = target_sal_rados[user_trim_start:user_trim_end]
assert "std::string bucket_name;" in user_trim
assert "trim_usage(dpp, get_id(), bucket_name" in user_trim

# The Store-level "all" methods use the same empty uid/empty bucket pair. This
# proves that the always-present REST User with an empty id reaches the global
# RADOS filter when a requested bucket failed to load.
all_read_start = target_sal_rados.index("int RadosStore::read_all_usage")
all_read_end = target_sal_rados.index("int RadosStore::trim_all_usage", all_read_start)
all_read = target_sal_rados[all_read_start:all_read_end]
assert "rgw_user uid;" in all_read
assert "std::string bucket_name;" in all_read
assert "read_usage(dpp, uid, bucket_name" in all_read

all_trim_start = target_sal_rados.index("int RadosStore::trim_all_usage")
all_trim_end = target_sal_rados.index("int RadosStore::get_config_key_val", all_trim_start)
all_trim = target_sal_rados[all_trim_start:all_trim_end]
assert "rgw_user uid;" in all_trim
assert "std::string bucket_name;" in all_trim
assert "trim_usage(dpp, uid, bucket_name" in all_trim

# A later commit explicitly made both routes return the bucket-load error.
# This corroborates the target endpoint gap but is not part of Quincy 17.2.7.
later_diff = subprocess.check_output(
    [
        "git",
        "-C",
        str(repo),
        "show",
        "--format=%B",
        "--unified=50",
        later_error_check,
        "--",
        "src/rgw/rgw_rest_usage.cc",
    ],
    text=True,
    encoding="utf-8",
)
assert "rgw/sal: rename loading get_bucket()s to load_bucket()" in later_diff
assert later_diff.count("op_ret = driver->load_bucket") >= 2
assert later_diff.count("if (op_ret < 0)") >= 2


new_rows = {
    "src/rgw/rgw_rest_usage.cc": (
        "affect",
        "RGW-045",
        "RGW-045: Quincy resolves a requested usage bucket through SAL but ignores a failed lookup in both GET and DELETE; the null bucket is passed onward instead of returning the error, enabling a broader user/global fallback.",
    ),
    "src/rgw/rgw_usage.cc": (
        "affect",
        "RGW-045",
        "RGW-045: The target usage dispatcher treats a null bucket as user scope (or all scope for an empty user id), so a failed REST bucket lookup can broaden usage output or trim beyond the requested bucket; Pacific applies uid/bucket filters directly.",
    ),
    "src/rgw/rgw_usage.h": (
        "affect",
        "RGW-045",
        "RGW-045: The usage API changes from explicit uid/bucket filters to nullable SAL User/Bucket parameters, establishing the fallback contract that broadens scope after a failed bucket lookup.",
    ),
}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for path, (impact, finding, reason) in new_rows.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified usage REST scope: 3 affect")
