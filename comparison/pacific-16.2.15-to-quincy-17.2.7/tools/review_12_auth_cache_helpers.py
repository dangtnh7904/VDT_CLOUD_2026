"""Classify RGW auth/SAL adapters and relocated helper implementations."""

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


# The authentication endpoint keeps the same lookup order and account fields;
# Quincy only routes them through SAL and replaces boost::optional with
# std::optional. TempURL still tries the implicit tenant before the global uid
# and then loads the bucket owner.
base_auth = show("v16.2.15", "src/rgw/rgw_auth.cc")
target_auth = show("v17.2.7", "src/rgw/rgw_auth.cc")
assert "ctl->user->get_info_by_uid(dpp, tenanted_uid, &user_info, null_yield)" in base_auth
assert "user = store->get_user(tenanted_uid);" in target_auth
assert "if (user->load_user(dpp, null_yield) >= 0)" in target_auth
for marker in (
    "rgw_apply_default_bucket_quota",
    "rgw_apply_default_user_quota",
    "IMPLICIT_TENANTS_SWIFT",
):
    assert marker in base_auth and marker in target_auth

base_swift = show("v16.2.15", "src/rgw/rgw_swift_auth.cc")
target_swift = show("v17.2.7", "src/rgw/rgw_swift_auth.cc")
assert "const rgw_user tenanted_uid(uid.id, uid.id);" in base_swift
assert "rgw_user tenanted_uid(uid.id, uid.id);" in target_swift
assert "ctl->user->get_info_by_uid(dpp, tenanted_uid, &uinfo, s->yield)" in base_swift
assert "user = store->get_user(tenanted_uid);" in target_swift
assert "bucket_tenant = uinfo.user_id.tenant;" in base_swift
assert "bucket_tenant = user->get_tenant();" in target_swift
assert "owner_info = user->get_info();" in target_swift

base_filters = show("v16.2.15", "src/rgw/rgw_auth_filters.h")
target_filters = show("v17.2.7", "src/rgw/rgw_auth_filters.h")
assert "ctl->user->get_info_by_uid(dpp, effective_uid, &euser_info, null_yield)" in base_filters
assert "std::unique_ptr<rgw::sal::User> user = store->get_user(effective_uid);" in target_filters
assert "user_info = user->get_info();" in target_filters

# JSON/dencoder helpers were moved from aggregate translation units to their
# owning sources. The cache invalidation body and its wire opcode ordinal are
# unchanged despite clearer names.
base_json = show("v16.2.15", "src/rgw/rgw_json_enc.cc")
base_dencoder = show("v16.2.15", "src/rgw/rgw_dencoder.cc")
target_basic = show("v17.2.7", "src/rgw/rgw_basic_types.cc")
for symbol, source in (
    ("void rgw_data_placement_target::dump", base_json),
    ("void rgw_bucket::dump", base_json),
    ("void rgw_user::generate_test_instances", base_dencoder),
):
    assert symbol in source and symbol in target_basic

base_cache_cc = show("v16.2.15", "src/rgw/rgw_cache.cc")
target_cache_cc = show("v17.2.7", "src/rgw/rgw_cache.cc")
base_cache_h = show("v16.2.15", "src/rgw/rgw_cache.h")
target_cache_h = show("v17.2.7", "src/rgw/rgw_cache.h")
base_body = base_cache_cc.split("bool ObjectCache::remove", 1)[1].split("void ObjectCache::touch_lru", 1)[0]
target_body = target_cache_cc.split("bool ObjectCache::invalidate_remove", 1)[1].split("void ObjectCache::touch_lru", 1)[0]
assert base_body[base_body.index("{"):] == target_body[target_body.index("{"):]
assert "UPDATE_OBJ,\n  REMOVE_OBJ," in base_cache_h
assert "UPDATE_OBJ,\n  INVALIDATE_OBJ," in target_cache_h
for marker in ("ENCODE_START(5, 3, bl)", "ENCODE_START(2, 2, obl)"):
    assert marker in base_cache_h and marker in target_cache_h

target_compression = show("v17.2.7", "src/rgw/rgw_compression.cc")
for symbol in ("void compression_block::dump", "void RGWCompressionInfo::dump"):
    assert symbol in base_json and symbol in target_compression

# Keystone's token parsing/request serialization was relocated from
# rgw_json_enc.cc. The FIPS allowance for the non-cryptographic PKI-token MD5
# is already present at both endpoints; the remaining delta is DPP/std cleanup.
base_keystone = show("v16.2.15", "src/rgw/rgw_keystone.cc")
target_keystone = show("v17.2.7", "src/rgw/rgw_keystone.cc")
for symbol in (
    "void rgw::keystone::TokenEnvelope::decode_v3",
    "void rgw::keystone::AdminTokenRequestVer3::dump",
):
    assert symbol in base_json and symbol in target_keystone
assert "EVP_MD_CTX_FLAG_NON_FIPS_ALLOW" in base_keystone
assert "EVP_MD_CTX_FLAG_NON_FIPS_ALLOW" in target_keystone

# The ES query row is namespace qualification only, and the HTTP-manager row
# adds a unit test for the separately unclassified runtime transport hunk.
base_es = show("v16.2.15", "src/rgw/rgw_es_query.h")
target_es = show("v17.2.7", "src/rgw/rgw_es_query.h")
assert "list<string> l;" in base_es
assert "std::list<std::string> l;" in target_es
base_http_test = show("v16.2.15", "src/test/rgw/test_http_manager.cc")
target_http_test = show("v17.2.7", "src/test/rgw/test_http_manager.cc")
assert "TEST(HTTPManager, Head)" not in base_http_test
assert "TEST(HTTPManager, Head)" in target_http_test


reasons = {
    "src/rgw/rgw_auth.cc": "RGW-AUTH-SAL-01: Replaces RGWUserCtl account creation/lookups with equivalent SAL User operations and std::optional while retaining implicit-tenant order, quotas, account type and exclusive creation.",
    "src/rgw/rgw_auth.h": "RGW-AUTH-SAL-01: Updates authentication applier declarations from RGWCtl/boost::optional to SAL Store/std::optional and qualifies STL types; no auth decision or persisted contract changes in this header row.",
    "src/rgw/rgw_auth_filters.h": "RGW-AUTH-SAL-02: Routes third-party and system-user uid lookups through SAL, copying the same RGWUserInfo and preserving the same anonymous, owner and failure branches.",
    "src/rgw/rgw_swift_auth.cc": "RGW-AUTH-SAL-03: Converts Swift TempURL, signed/external token and auth-user lookups to SAL while preserving tenant fallback, bucket-owner selection, keys and permission inputs at the two endpoints.",
    "src/rgw/rgw_swift_auth.h": "RGW-AUTH-SAL-03: Changes Swift auth engine/factory declarations from RGWCtl/RadosStore to SAL Store and boost::none to std::nullopt without changing the authentication interface or strategy order.",
    "src/rgw/rgw_basic_types.cc": "RGW-HELPER-MOVE-01: Moves existing rgw_user, placement and bucket dump/test helpers from aggregate encoder sources into the owning translation unit; runtime encodings and parsing remain unchanged.",
    "src/rgw/rgw_basic_types.h": "RGW-HELPER-MOVE-01: Adds a convenience bucket constructor/forward declarations and qualifies standard-library types; existing bucket/user wire encodings and comparison semantics are unchanged.",
    "src/rgw/rgw_cache.cc": "RGW-CACHE-NAME-01: Renames ObjectCache::remove to invalidate_remove with an identical invalidation body and relocates dump/test helpers; it does not introduce negative caching.",
    "src/rgw/rgw_cache.h": "RGW-CACHE-NAME-01: Renames REMOVE_OBJ to INVALIDATE_OBJ at the same enum ordinal and qualifies container types while retaining ObjectCacheInfo/RGWCacheNotifyInfo encoding versions.",
    "src/rgw/rgw_compression.cc": "RGW-HELPER-MOVE-02: Relocates compression dump helpers, clarifies logs and casts the chunk-size comparison to off_t; decompression blocks, range math and downstream data are unchanged.",
    "src/rgw/rgw_keystone.cc": "RGW-KEYSTONE-MECH-01: Adds DPP to the same Keystone token/cache paths and relocates unchanged JSON serializers; both endpoints already allow the non-cryptographic PKI-token MD5 in FIPS mode.",
    "src/rgw/rgw_keystone.h": "RGW-KEYSTONE-MECH-01: Threads DPP and std-qualified types through Keystone declarations without changing token fields, role matching, expiry rules or cache contract.",
    "src/rgw/rgw_es_query.h": "RGW-STD-ES-01: Qualifies STL types and reformats the Elasticsearch query declarations; parser/compiler fields and operations are unchanged.",
    "src/test/rgw/test_http_manager.cc": "RGW-HTTP-TEST-01: Adds a unit test that a HEAD response with Content-Length and no body completes, plus argv/namespace cleanup; this test row does not itself alter deployed RGW behavior.",
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
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)
    else:
        assert row["upgrade_impact"] == "trivial", path
        assert row["finding_id"] == "", path
        assert row["impact_reason"] == reason, path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified fourteen auth/cache/helper rows trivial")
