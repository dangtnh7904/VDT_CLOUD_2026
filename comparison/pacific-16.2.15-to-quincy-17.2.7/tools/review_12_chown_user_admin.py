"""Verify RGW bucket/user chown rework and adjacent user-admin parity."""

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


def section(source: str, start: str, end: str | None = None) -> str:
    begin = source.index(start)
    finish = source.index(end, begin) if end else len(source)
    return source[begin:finish]


chown_commit = "62d97388c77b23a7e322f7692faaefbf570593ff"
assert not is_ancestor(chown_commit, "v16.2.15")
assert is_ancestor(chown_commit, "v17.2.7")
message = subprocess.check_output(
    ["git", "-C", str(repo), "show", "-s", "--format=%B", chown_commit],
    text=True,
    encoding="utf-8",
)
assert "Chown was not unlinking" in message
assert "partially leaving the ownership wrong" in message

base_bucket = show("v16.2.15", "src/rgw/rgw_bucket.cc")
target_bucket = show("v17.2.7", "src/rgw/rgw_bucket.cc")
base_user = show("v16.2.15", "src/rgw/rgw_user.cc")
target_user = show("v17.2.7", "src/rgw/rgw_user.cc")
base_rados = show("v16.2.15", "src/rgw/rgw_sal_rados.cc")
target_rados = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")
target_db = show("v17.2.7", "src/rgw/rgw_sal_dbstore.cc")

# Pacific's bucket-admin chown iterates object ACLs. The user-rename path links
# the bucket to the new owner and calls that ACL loop, but never unlinks the
# old owner mapping. Its RADOS SAL unlink method is an unimplemented stub.
base_ctl = section(
    base_bucket,
    "int RGWBucketCtl::chown(",
    "int RGWBucketCtl::read_bucket_stats(",
)
for token in (
    "list_op.params.list_versions = true;",
    "acl.remove_canon_user_grant(owner.get_id());",
    "grant.set_canon(user_id, display_name, RGW_PERM_FULL_CONTROL);",
    "store->getRados()->set_attr",
):
    assert token in base_ctl
base_rename = section(
    base_user,
    "int RGWUser::execute_rename(",
    "int RGWUser::execute_add(",
)
assert "bucket->link(dpp, &new_user, y);" in base_rename
assert "bucket->chown(&new_user, &old_user, y, dpp);" in base_rename
assert "bucket->unlink" not in base_rename
base_sal_chown = section(
    base_rados,
    "int RGWRadosBucket::unlink(",
    "int RGWRadosBucket::put_instance_info(",
)
assert "return -1;" in base_sal_chown
assert "store->ctl()->bucket->chown" in base_sal_chown

# Quincy first unlinks/relinks the bucket, then traverses all object versions
# through the SAL Object::chown() API. Both bucket-admin chown and user rename
# call the same helper. The sequence is not atomic: failures during object ACL
# processing can occur after the bucket mapping changed. A bucket->chown
# failure also only sets err_msg, so the object ACL loop can still run.
target_helper = section(
    target_bucket,
    "int rgw_chown_bucket_and_objects(",
)
assert "ret = bucket->chown(dpp, *new_user, y);" in target_helper
assert "params.list_versions = true;" in target_helper
assert "ret = r_obj->chown(*new_user, dpp, y);" in target_helper
assert target_helper.index("bucket->chown") < target_helper.index("bucket->list")
target_bucket_failure = section(
    target_helper, "if (ret < 0)", "/* Now chown on all the objects"
)
assert "set_err_msg" in target_bucket_failure
assert "return" not in target_bucket_failure
target_admin_chown = section(
    target_bucket,
    "int RGWBucket::chown(",
    "int RGWBucket::set_quota(",
)
assert "bucket->set_owner(old_user.get());" in target_admin_chown
assert "return rgw_chown_bucket_and_objects" in target_admin_chown
target_rename = section(
    target_user,
    "int RGWUser::execute_rename(",
    "int RGWUser::execute_add(",
)
assert "rgw_chown_bucket_and_objects" in target_rename
assert "bucket->link(" not in target_rename
target_bucket_chown = section(
    target_rados,
    "int RadosBucket::chown(",
    "int RadosBucket::put_info(",
)
assert "this->unlink(dpp, owner, y)" in target_bucket_chown
assert "this->link(dpp, &new_user, y)" in target_bucket_chown
target_object_chown = section(
    target_rados,
    "int RadosObject::chown(",
    "MPSerializer* RadosObject::get_serializer(",
)
for token in (
    "get_obj_attrs",
    "RGW_ATTR_ACL",
    "acl.remove_canon_user_grant(owner.get_id());",
    "grant.set_canon(new_user.get_id(), new_user.get_display_name(), RGW_PERM_FULL_CONTROL);",
    "set_obj_attrs",
):
    assert token in target_object_chown

# The DBStore implementation adopts the interface, but its object chown is a
# no-op. Keep its rows attached to the conditional finding rather than claiming
# that it gains RADOS-equivalent ACL behavior.
db_object_chown = section(
    target_db,
    "int DBObject::chown(",
    "MPSerializer* DBObject::get_serializer(",
)
assert "return 0;" in db_object_chown
assert "RGW_ATTR_ACL" not in db_object_chown

# The apparent master-zone key fix is endpoint parity: Pacific contains the
# release-branch backport while Quincy contains the original commit. The REST
# net diff is SAL construction plus removal of a user-caps parameter that the
# modify implementation never consumed; caps have their own operation.
base_master_fix = "ec99a687289268d231614244416b2605ab9afc4f"
target_master_fix = "be23f5b2dd88c7d2bc2525825e30294f13f6585d"
assert is_ancestor(base_master_fix, "v16.2.15")
assert not is_ancestor(base_master_fix, "v17.2.7")
assert not is_ancestor(target_master_fix, "v16.2.15")
assert is_ancestor(target_master_fix, "v17.2.7")
base_rest = show("v16.2.15", "src/rgw/rgw_rest_user.cc")
target_rest = show("v17.2.7", "src/rgw/rgw_rest_user.cc")
for source in (base_rest, target_rest):
    assert source.count("fetch_access_keys_from_master(") == 3
    assert "op_state.op_access_keys = std::move(ui.access_keys);" in source
    assert "RGWUserAdminOp_Caps::add" in source
base_rest_modify = section(
    base_rest,
    "void RGWOp_User_Modify::execute(",
    "class RGWOp_User_Remove",
)
target_rest_modify = section(
    target_rest,
    "void RGWOp_User_Modify::execute(",
    "class RGWOp_User_Remove",
)
assert 'RESTArgs::get_string(s, "user-caps", caps, &caps);' in base_rest_modify
assert 'RESTArgs::get_string(s, "user-caps", caps, &caps);' not in target_rest_modify
for source in (base_user, target_user):
    modify = section(source, "int RGWUser::execute_modify(", "int RGWUser::modify(")
    assert "caps.add" not in modify
    assert "RGWUserAdminOp_Caps::add" in source
    assert "op_state.op_access_keys" in source


new_rows = {
    "src/rgw/rgw_bucket.cc": (
        "affect",
        "RGW-047",
        "RGW-047: Quincy routes bucket chown and user rename through a shared unlink/relink and per-object-version ACL helper; after bucket->chown returns an error the helper only records err_msg and continues the object loop, so persistent ownership/ACL updates can be partial. Pacific can leave the old user mapping linked.",
    ),
    "src/rgw/rgw_sal_dbstore.cc": (
        "affect",
        "RGW-047",
        "RGW-047: DBStore adopts the new bucket/object chown contract, but DBObject::chown returns success without changing ACLs; applicability is conditional on the experimental DBStore backend and is not equivalent to RADOS.",
    ),
    "src/rgw/rgw_sal_dbstore.h": (
        "affect",
        "RGW-047",
        "RGW-047: DBStore declares the new bucket-owner and object-chown interface used by the shared chown helper; its object implementation remains a no-op, so backend behavior must be treated separately.",
    ),
    "src/rgw/rgw_user.cc": (
        "affect",
        "RGW-047",
        "RGW-047: User rename uses the shared bucket/object chown helper instead of the legacy link-plus-ACL path; the helper can continue changing object ACLs after a bucket-owner change error, so unlink/relink and ACL updates need partial-state validation.",
    ),
    "src/rgw/rgw_rest_user.cc": (
        "trivial",
        "",
        "RGW-USER-REST-SAL-01: Both endpoints already fetch and persist master-zone access keys for user create/modify via release-specific copies of the same fix; remaining net hunks construct SAL-backed op state and remove an unused user-caps parse from modify.",
    ),
}

existing_rows = {
    "src/rgw/rgw_bucket.h": (
        "RGW-047",
        "RGW-047: Declares the shared bucket-and-object chown helper and new SAL-based bucket state used by bucket chown and user rename.",
    ),
    "src/rgw/rgw_sal.h": (
        "RGW-047",
        "RGW-047: Changes Bucket::chown to require the current owner and adds Object::chown, defining the unlink/relink plus per-object ACL contract.",
    ),
    "src/rgw/rgw_sal_rados.cc": (
        "RGW-047",
        "RGW-047: RADOS bucket chown now unlinks the old owner before linking the new one, and RadosObject::chown rewrites the ACL owner/full-control grant.",
    ),
    "src/rgw/rgw_sal_rados.h": (
        "RGW-047",
        "RGW-047: Declares the RADOS implementations of the revised bucket chown and new object ACL chown contract.",
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

for path, (finding, reason) in existing_rows.items():
    row = by_path[path]
    assert row["upgrade_impact"] == "affect", path
    ids = [item for item in row["finding_id"].split(",") if item]
    if finding not in ids:
        row["finding_id"] = ",".join(ids + [finding])
    if reason not in row["impact_reason"]:
        row["impact_reason"] = row["impact_reason"].rstrip() + " " + reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified RGW chown/user-admin cluster: 4 affect, 1 trivial; enriched 4 affect rows")
