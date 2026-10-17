"""Classify IAM role forwarding/metadata sync and exact OTP adapters."""

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


# Quincy forwards seven role-mutating IAM operations from a non-metadata-master
# zone. Pacific has no corresponding branch and creates/updates the local role.
base_rest_role = show("v16.2.15", "src/rgw/rgw_rest_role.cc")
target_rest_role = show("v17.2.7", "src/rgw/rgw_rest_role.cc")
assert "is_meta_master" not in base_rest_role
assert "forward_iam_request_to_master" not in base_rest_role
assert target_rest_role.count("if (!store->is_meta_master())") == 7
assert target_rest_role.count("store->forward_iam_request_to_master(") == 7
assert "role.create(s, true, y)" in base_rest_role
assert "role->create(s, true, role_id, y)" in target_rest_role
for operation in (
    "RGWCreateRole::execute",
    "RGWDeleteRole::execute",
    "RGWModifyRole::execute",
    "RGWPutRolePolicy::execute",
    "RGWDeleteRolePolicy::execute",
    "RGWTagRole::execute",
    "RGWUntagRole::execute",
):
    assert operation in base_rest_role and operation in target_rest_role

# The target preserves the form body for forwarding. Two target loops erase
# Tags.member iterators in-place; keep this assertion as a validation hazard.
base_iam = show("v16.2.15", "src/rgw/rgw_rest_iam.cc")
target_iam = show("v17.2.7", "src/rgw/rgw_rest_iam.cc")
assert "new RGWCreateRole;" in base_iam
assert "new RGWCreateRole(this->bl_post_body);" in target_iam
assert "new RGWTagRole(this->bl_post_body);" in target_iam
assert target_rest_role.count("val_map.erase(it);") == 3
assert target_rest_role.count('find("Tags.member.") == 0') == 3

# IAM forwarding uses service-aware SigV4 and removes PayloadHash from the
# non-S3 canonical query. These paths are absent from the Pacific endpoint.
base_client = show("v16.2.15", "src/rgw/rgw_rest_client.cc")
target_client = show("v17.2.7", "src/rgw/rgw_rest_client.cc")
assert 'service == "iam"' not in base_client
assert 'service == "iam"' in target_client
assert target_client.count('s == "iam"') >= 2
assert 'info.args.remove("PayloadHash")' in target_client
base_conn = show("v16.2.15", "src/rgw/rgw_rest_conn.cc")
target_conn = show("v17.2.7", "src/rgw/rgw_rest_conn.cc")
assert "forward_iam_request" not in base_conn
assert "RGWRESTConn::forward_iam_request" in target_conn
base_auth_h = show("v16.2.15", "src/rgw/rgw_auth_s3.h")
target_auth_h = show("v17.2.7", "src/rgw/rgw_auth_s3.h")
assert "gen_v4_canonical_qs" not in base_auth_h
assert "gen_v4_canonical_qs(const req_info& info, bool is_non_s3_op);" in target_auth_h

# Target role objects retain the v3/compat1 binary payload and existing raw OID
# prefix, but add a roles metadata handler that logs/syncs this section.
base_role_h = show("v16.2.15", "src/rgw/rgw_role.h")
target_role_h = show("v17.2.7", "src/rgw/rgw_role.h")
for source in (base_role_h, target_role_h):
    assert "ENCODE_START(3, 1, bl)" in source
    for field in (
        "id",
        "name",
        "path",
        "arn",
        "creation_date",
        "trust_policy",
        "perm_policy_map",
        "tenant",
        "max_session_duration",
    ):
        assert f"encode({field}, bl);" in source
assert "RGWRoleMetadataHandler" not in base_role_h
assert "class RGWRoleMetadataHandler" in target_role_h
assert 'get_type() final { return "roles";' in target_role_h

target_role = show("v17.2.7", "src/rgw/rgw_role.cc")
assert "RGWRoleMetadataHandler::do_get" in target_role
assert "RGWRoleMetadataHandler::do_put" in target_role
assert "RGWRoleMetadataHandler::do_remove" in target_role
assert "role->create(dpp, true, info.id, y)" in target_role

target_role_svc = show("v17.2.7", "src/rgw/services/svc_role_rados.cc")
assert 'RGWSI_MBSObj_Handler_Module("roles")' in target_role_svc
assert "prefix(role_oid_prefix)" in target_role_svc
assert "return prefix + key" in target_role_svc

# The generic metadata backend now preserves raw attrs (including role tags)
# and threads role reads/writes through the SObj backend.
base_meta = show("v16.2.15", "src/rgw/services/svc_meta_be.cc")
target_meta = show("v17.2.7", "src/rgw/services/svc_meta_be.cc")
assert "get_raw_attrs" not in base_meta
assert "get_entry(ctx, key, params, objv_tracker, y, dpp, get_raw_attrs)" in target_meta
base_sobj = show("v16.2.15", "src/rgw/services/svc_meta_be_sobj.cc")
target_sobj = show("v17.2.7", "src/rgw/services/svc_meta_be_sobj.cc")
assert "get_raw_attrs" not in base_sobj
assert "params.refresh_version, get_raw_attrs" in target_sobj

base_service = show("v16.2.15", "src/rgw/rgw_service.cc")
target_service = show("v17.2.7", "src/rgw/rgw_service.cc")
assert "role_rados" not in base_service
assert "role_rados->start(y, dpp)" in target_service
assert "RGWRoleMetadataHandler" in target_service
assert "meta.role->attach(meta.mgr)" in target_service

# A Pacific metadata consumer has no roles handler. Its manager returns ENOENT,
# and its sync shard explicitly keeps the marker behind any failed entry.
base_metadata = show("v16.2.15", "src/rgw/rgw_metadata.cc")
assert "if (iter == handlers.end())\n    return -ENOENT;" in base_metadata
base_sync = show("v16.2.15", "src/rgw/rgw_sync.cc")
assert "on any error code from RGWMetaSyncSingleEntryCR, we do not advance" in base_sync
assert "can_adjust_marker=false" in base_sync

# Quincy adds a role-sync test, but it is not executed by this source review.
base_test = show("v16.2.15", "src/test/rgw/rgw_multi/tests.py")
target_test = show("v17.2.7", "src/test/rgw/rgw_multi/tests.py")
assert "def test_role_sync" not in base_test
assert "def test_role_sync" in target_test
assert "zonegroup_meta_checkpoint" in target_test

# OTP only accepts the expanded virtual signature and does not consume the new
# flag. Its operation body remains unrelated to role raw-attribute handling.
target_otp = show("v17.2.7", "src/rgw/services/svc_meta_be_otp.cc")
target_otp_h = show("v17.2.7", "src/rgw/services/svc_meta_be_otp.h")
assert target_otp.count("get_raw_attrs") == 1
assert target_otp_h.count("get_raw_attrs") == 1


affect = {
    "src/rgw/rgw_auth_s3.h": "RGW-030: Extends canonical-query generation for non-S3 SigV4, used when a Quincy non-master forwards IAM role mutations to the metadata master.",
    "src/rgw/rgw_rest_client.cc": "RGW-030: Adds IAM-aware SigV4 scope/PayloadHash handling required to forward role mutations from non-master zones.",
    "src/rgw/rgw_rest_client.h": "RGW-030: Extends the forwarding interface with an IAM service selector used by non-master role operations.",
    "src/rgw/rgw_rest_conn.cc": "RGW-030: Implements the signed IAM request sent from a non-master zone to the metadata master.",
    "src/rgw/rgw_rest_conn.h": "RGW-030: Exposes the IAM forwarding operation used by role REST writes.",
    "src/rgw/rgw_rest_iam.cc": "RGW-030: Preserves the IAM POST body and passes it to role mutation handlers so non-master requests can be forwarded.",
    "src/rgw/rgw_rest_iam.h": "RGW-030: Stores the IAM POST body in the handler for forwarding role mutations.",
    "src/rgw/rgw_rest_role.cc": "RGW-030: Forwards seven role mutations on non-master zones, reuses the master's RoleId locally, and introduces target-only tag-parameter iterator hazards requiring validation.",
    "src/rgw/rgw_rest_role.h": "RGW-030: Extends role mutation operations with the POST body and SAL role interfaces used by master forwarding.",
    "src/rgw/rgw_role.cc": "RGW-030: Adds the roles metadata get/put/remove handler so role objects and attributes enter multisite metadata synchronization.",
    "src/rgw/rgw_role.h": "RGW-030: Splits role state into the SAL metadata object/handler while retaining v3 encoding and exposing sync version, mtime and attrs.",
    "src/rgw/rgw_service.cc": "RGW-030: Starts the RADOS role service and registers/attaches the new roles metadata handler.",
    "src/rgw/rgw_service.h": "RGW-030: Adds role service and metadata-handler ownership to RGW service/control state.",
    "src/rgw/services/svc_meta_be.cc": "RGW-030: Propagates the raw-attribute read flag needed to synchronize role tagging attrs.",
    "src/rgw/services/svc_meta_be.h": "RGW-030: Extends metadata backend get/list interfaces for raw role attrs and DPP-aware iteration.",
    "src/rgw/services/svc_meta_be_sobj.cc": "RGW-030: Passes the raw-attribute flag into system-object reads and DPP into metadata iteration for the roles backend.",
    "src/rgw/services/svc_meta_be_sobj.h": "RGW-030: Extends the SObj metadata backend interface used by the new roles section.",
    "src/rgw/services/svc_role_rados.cc": "RGW-030: Implements the roles metadata section over the existing roles pool and role OID prefix.",
    "src/rgw/services/svc_role_rados.h": "RGW-030: Defines the RADOS role service and metadata backend ownership started by RGW.",
}

trivial = {
    "src/rgw/services/svc_meta_be_otp.cc": "RGW-META-OTP-ADAPTER-01: Accepts the new get_raw_attrs virtual parameter but does not use it; OTP read behavior is unchanged.",
    "src/rgw/services/svc_meta_be_otp.h": "RGW-META-OTP-ADAPTER-01: Qualifies STL types and follows the metadata get signature; no OTP field, storage or synchronization behavior changes here.",
}

updates = {
    **{path: ("affect", "RGW-030", reason) for path, reason in affect.items()},
    **{path: ("trivial", "", reason) for path, reason in trivial.items()},
}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for path, (impact, finding, reason) in updates.items():
    row = by_path[path]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], path
    row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified 19 IAM-role forwarding/sync rows affect and two OTP adapters trivial")
