"""Verify and classify the RGW STS/OIDC endpoint cluster."""

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


# Pacific carries a later backport that removes the unused AssumeRole metadata
# write. The Quincy endpoint does not contain that commit and still performs a
# load/store after generating credentials.
remove_write_commit = "0f7a3af26d87f0fdcd52a19ff1373e9536782165"
message = subprocess.check_output(
    ["git", "-C", str(repo), "show", "-s", "--format=%B", remove_write_commit],
    text=True,
    encoding="utf-8",
)
assert "AssumeRole no longer writes to user metadata" in message
assert "field was unused" in message
assert is_ancestor(remove_write_commit, "v16.2.15")
assert not is_ancestor(remove_write_commit, "v17.2.7")

base_sts = show("v16.2.15", "src/rgw/rgw_sts.cc")
target_sts = show("v17.2.7", "src/rgw/rgw_sts.cc")
base_sts_h = show("v16.2.15", "src/rgw/rgw_sts.h")
target_sts_h = show("v17.2.7", "src/rgw/rgw_sts.h")
for token in (
    "int STSService::storeARN",
    "//Save ARN with the user",
    "response.retCode = storeARN(dpp, arn, y);",
    "user->get_info().assumed_role_arn = arn;",
    "user->store_user(dpp, y, false, &user->get_info())",
    "return -ERR_NO_SUCH_ENTITY;",
    "return -ERR_INTERNAL_ERROR;",
):
    assert token not in base_sts
    assert token in target_sts
assert "storeARN(" not in base_sts_h
assert "storeARN(" in target_sts_h

# The user-info slot remains wire-compatible. Pacific encodes an empty local
# string and discards the decoded value; Quincy exposes the same slot as a real
# member. This separates the request-time write risk from a format migration.
base_common = show("v16.2.15", "src/rgw/rgw_common.h")
target_common = show("v17.2.7", "src/rgw/rgw_common.h")
decode_v22 = "DECODE_START_LEGACY_COMPAT_LEN_32(22, 9, 9, bl);"
assert decode_v22 in base_common and decode_v22 in target_common
assert base_common.count("std::string assumed_role_arn; // removed") == 2
assert "std::string assumed_role_arn; // removed" not in target_common
assert "std::string assumed_role_arn;" in target_common
assert "encode(assumed_role_arn, bl);" in base_common
assert "encode(assumed_role_arn, bl);" in target_common
assert "decode(assumed_role_arn, bl);" in base_common
assert "decode(assumed_role_arn, bl);" in target_common

# JWT discovery, principal/session tags, and policy evaluation already exist at
# both endpoints through branch-specific backports. The net REST diff is SAL,
# ownership, logging-context, and qualification plumbing.
base_rest_sts = show("v16.2.15", "src/rgw/rgw_rest_sts.cc")
target_rest_sts = show("v17.2.7", "src/rgw/rgw_rest_sts.cc")
for token in (
    "/.well-known/openid-configuration",
    "principal_tags",
    "rgw::IAM::stsTagSession, boost::none",
    "p.eval(s->env, *s->auth.identity, op, boost::none)",
):
    assert token in base_rest_sts
    assert token in target_rest_sts

# OIDC provider persistence moves behind SAL/RadosOIDCProvider while retaining
# the v3 payload, object prefix, pool operations, and create/get/delete/list
# behavior.
base_oidc_h = show("v16.2.15", "src/rgw/rgw_oidc_provider.h")
target_oidc_h = show("v17.2.7", "src/rgw/rgw_oidc_provider.h")
for source in (base_oidc_h, target_oidc_h):
    assert "ENCODE_START(3, 1, bl);" in source
    for token in ("provider_url", "arn", "creation_date", "tenant", "client_ids", "thumbprints"):
        assert f"encode({token}, bl);" in source
target_sal = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")
for token in (
    "RadosOIDCProvider::store_url",
    "RadosOIDCProvider::read_url",
    "RadosOIDCProvider::delete_obj",
    "RGWOIDCProvider::oidc_url_oid_prefix",
    "rgw_put_system_obj",
    "rgw_get_system_obj",
    "rgw_delete_system_obj",
):
    assert token in target_sal

# The corrected IAM user-policy response/request names and decode wrapper exist
# at both endpoints. The remaining diff routes the same operations through SAL.
base_user_policy = show("v16.2.15", "src/rgw/rgw_rest_user_policy.cc")
target_user_policy = show("v17.2.7", "src/rgw/rgw_rest_user_policy.cc")
for token in (
    'encode_json("PolicyName"',
    'encode_json("UserName"',
    'encode_json("PolicyDocument"',
    'open_object_section("PolicyNames")',
):
    assert token in base_user_policy
    assert token in target_user_policy

# POST-policy changes are namespace qualification plus equivalent emplacement.
base_policy = show("v16.2.15", "src/rgw/rgw_policy_s3.h")
target_policy = show("v17.2.7", "src/rgw/rgw_policy_s3.h")
assert "var_checks.push_back(pair<string, string>(var, value));" in base_policy
assert "var_checks.emplace_back(var, value);" in target_policy


new_rows = {
    "src/rgw/rgw_sts.cc": (
        "affect",
        "RGW-040",
        "RGW-040: Quincy still loads and stores user metadata after each successful AssumeRole to persist an unused assumed-role ARN; Pacific 16.2.15 carries the backport that removes this write and its extra failure path.",
    ),
    "src/rgw/rgw_sts.h": (
        "affect",
        "RGW-040",
        "RGW-040: Quincy declares the private storeARN helper used by AssumeRole; Pacific 16.2.15 removed it with the unused user-metadata write.",
    ),
    "src/rgw/rgw_oidc_provider.cc": (
        "trivial",
        "",
        "RGW-STS-SAL-01: Moves OIDC provider RADOS persistence/listing behind SAL while retaining validation, object identity, pool operations, and encoded provider behavior.",
    ),
    "src/rgw/rgw_oidc_provider.h": (
        "trivial",
        "",
        "RGW-STS-SAL-01: Converts the OIDC provider to a SAL interface; the v3 encoding and provider fields remain unchanged at both endpoints.",
    ),
    "src/rgw/rgw_rest_oidc_provider.cc": (
        "trivial",
        "",
        "RGW-STS-SAL-01: Routes the same OIDC create/get/delete/list REST operations through SAL provider objects and DPP logging.",
    ),
    "src/rgw/rgw_rest_sts.cc": (
        "trivial",
        "",
        "RGW-STS-SAL-02: Keeps endpoint JWT discovery, principal/session tags, and optional resource-policy evaluation while changing SAL ownership, DPP calls, and standard-name qualification.",
    ),
    "src/rgw/rgw_rest_sts.h": (
        "trivial",
        "",
        "RGW-STS-SAL-02: Updates STS REST declarations for SAL Store, unique ownership, DPP, and standard-name qualification without changing the endpoint operations.",
    ),
    "src/rgw/rgw_rest_user_policy.cc": (
        "trivial",
        "",
        "RGW-STS-SAL-03: Retains corrected IAM user-policy parameter/response names and decode behavior while routing equivalent user load/read/store operations through SAL.",
    ),
    "src/rgw/rgw_policy_s3.h": (
        "trivial",
        "",
        "RGW-STS-STD-01: Qualifies standard-library types and replaces construction-plus-push_back with equivalent emplace_back; POST-policy checks and fields are unchanged.",
    ),
    "doc/radosgw/STS.rst": (
        "trivial",
        "",
        "RGW-STS-DOC-01: Corrects STS configuration spelling, examples, capability setup, and the 16-character key note; it does not change executable behavior.",
    ),
    "doc/radosgw/STSLite.rst": (
        "trivial",
        "",
        "RGW-STS-DOC-01: Corrects STS Lite configuration examples, key-length note, and Python print syntax; it does not change executable behavior.",
    ),
}

existing_additions = {
    "src/rgw/rgw_common.h": (
        "RGW-040",
        "RGW-040: Preserves user-info encoding v22 and the assumed-role ARN slot, but Quincy exposes the slot as a stored field while Pacific encodes an empty value and discards it after removing the unused AssumeRole metadata write.",
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

for path, (finding, reason) in existing_additions.items():
    row = by_path[path]
    assert row["upgrade_impact"] == "affect", path
    findings = row["finding_id"].split(",") if row["finding_id"] else []
    if finding not in findings:
        row["finding_id"] = ",".join(findings + [finding])
        row["impact_reason"] = (row["impact_reason"] + " " + reason).strip()
    else:
        assert reason in row["impact_reason"], path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified STS/OIDC cluster: 2 affect, 9 trivial; extended 1 existing affect row")
