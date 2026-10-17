"""Classify ACL source relocation and SAL user-lookup adapters."""

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


base_acl_h = show("v16.2.15", "src/rgw/rgw_acl.h")
target_acl_h = show("v17.2.7", "src/rgw/rgw_acl.h")
target_acl = show("v17.2.7", "src/rgw/rgw_acl.cc")
base_dencoder = show("v16.2.15", "src/rgw/rgw_dencoder.cc")
base_json = show("v16.2.15", "src/rgw/rgw_json_enc.cc")

# ACL wire versions and compatibility floors are unchanged. The large addition
# to rgw_acl.cc relocates the same dump/test/URI helpers from the old aggregate
# encoder sources rather than adding an authorization decision.
for marker in (
    "ENCODE_START(5, 3, bl)",
    "ENCODE_START(4, 3, bl)",
    "ENCODE_START(3, 2, bl)",
    "ENCODE_START(2, 2, bl)",
):
    assert marker in base_acl_h and marker in target_acl_h
for symbol in (
    "void ACLPermission::dump",
    "void ACLGrant::dump",
    "void RGWAccessControlList::dump",
    "void ACLOwner::dump",
    "void RGWAccessControlPolicy::dump",
):
    assert symbol in base_json and symbol in target_acl, symbol
assert "ACLGroupTypeEnum ACLGrant::uri_to_group" in base_dencoder
assert "ACLGroupTypeEnum ACLGrant::uri_to_group" in target_acl

# S3 continues to resolve email/uid grants through the same RADOS user backend,
# copy the same id/display name, and recognize the same two group URIs.
base_s3 = show("v16.2.15", "src/rgw/rgw_acl_s3.cc")
target_s3 = show("v17.2.7", "src/rgw/rgw_acl_s3.cc")
assert "user_ctl->get_info_by_email(dpp, id_val, &info, null_yield)" in base_s3
assert "store->get_user_by_email(dpp, id_val, null_yield, &user)" in target_s3
assert "user_ctl->get_info_by_uid(dpp, user, &info, null_yield)" in base_s3
assert "std::unique_ptr<rgw::sal::User> user = store->get_user(rgw_user(id_val));" in target_s3
assert "ret = user->load_user(dpp, null_yield);" in target_s3
for source in (base_dencoder, target_s3):
    assert 'http://acs.amazonaws.com/groups/global/AllUsers' in source
    assert 'http://acs.amazonaws.com/groups/global/AuthenticatedUsers' in source
    assert "return ACL_GROUP_ALL_USERS;" in source
    assert "return ACL_GROUP_AUTHENTICATED_USERS;" in source

# Swift's missing-user behavior also remains a canonical grant with an empty
# display name; successful lookup uses the same id/display name pair.
base_swift = show("v16.2.15", "src/rgw/rgw_acl_swift.cc")
target_swift = show("v17.2.7", "src/rgw/rgw_acl_swift.cc")
assert "user_ctl->get_info_by_uid(dpp, user, &grant_user, null_yield)" in base_swift
assert "user = store->get_user(rgw_user(uid));" in target_swift
assert "if (user->load_user(dpp, null_yield) < 0)" in target_swift
assert "grant.set_canon(user, std::string(), perm);" in base_swift
assert "grant.set_canon(user->get_id(), std::string(), perm);" in target_swift
assert "grant.set_canon(user, grant_user.display_name, perm);" in base_swift
assert "grant.set_canon(user->get_id(), user->get_display_name(), perm);" in target_swift


reasons = {
    "src/rgw/rgw_acl.cc": "RGW-ACL-ADAPTER-01: Relocates existing ACL dump/test/URI helpers from the aggregate encoder sources and adds DPP logging; ACL permission evaluation and wire versions are unchanged.",
    "src/rgw/rgw_acl.h": "RGW-ACL-ADAPTER-01: Qualifies standard-library types and threads DPP into referer logging while preserving ACL fields, encodings, permission masks and evaluation order.",
    "src/rgw/rgw_acl_s3.cc": "RGW-ACL-ADAPTER-02: Replaces S3 ACL RGWUserCtl uid/email lookups with equivalent SAL user loads and copies the same id/display name; canned grants and group URI mapping are unchanged.",
    "src/rgw/rgw_acl_s3.h": "RGW-ACL-ADAPTER-02: Updates S3 ACL signatures from RGWUserCtl to the SAL Store and qualifies STL types; no ACL contract or permission behavior changes in this declaration row.",
    "src/rgw/rgw_acl_swift.cc": "RGW-ACL-ADAPTER-03: Replaces Swift ACL uid lookups with equivalent SAL user loads, retaining successful id/display-name grants and missing-user empty-name grants.",
    "src/rgw/rgw_acl_swift.h": "RGW-ACL-ADAPTER-03: Updates Swift ACL helper signatures from RGWUserCtl to the SAL Store; ACL parsing, masks and grant interfaces remain unchanged.",
}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for path, reason in reasons.items():
    row = by_path[path]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], path
    row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified six ACL relocation/SAL adapter rows trivial")
