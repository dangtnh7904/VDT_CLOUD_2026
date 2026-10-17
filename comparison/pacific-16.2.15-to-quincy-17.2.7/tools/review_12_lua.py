"""Classify the RGW Lua error, request API, and package-version changes."""

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


base_utils = show("v16.2.15", "src/rgw/rgw_lua_utils.h")
target_utils = show("v17.2.7", "src/rgw/rgw_lua_utils.h")
assert 'throw std::runtime_error("trying to write to readonly field")' in base_utils
assert 'throw std::runtime_error("trying to iterate over non-iterable field")' in base_utils
assert 'throw std::runtime_error("trying to get length of non-iterable field")' in base_utils
assert "static void throw_unknown_field" in base_utils
assert 'return luaL_error(L, "trying to write to readonly field")' in target_utils
assert 'return luaL_error(L, "trying to iterate over non-iterable field")' in target_utils
assert 'return luaL_error(L, "trying to get length of non-iterable field")' in target_utils
assert "static int error_unknown_field" in target_utils

base_request = show("v16.2.15", "src/rgw/rgw_lua_request.cc")
target_request = show("v17.2.7", "src/rgw/rgw_lua_request.cc")
assert "throw_unknown_field(index, TableName())" in base_request
assert "return error_unknown_field(L, index, TableName())" in target_request
assert base_request.count('strcasecmp(index, "StorageClass")') == 1
assert target_request.count('strcasecmp(index, "StorageClass")') == 3
assert "info->storage_class = luaL_checkstring(L, 3)" in target_request
assert base_request.count('strcasecmp(index, "User")') == 3
assert target_request.count('strcasecmp(index, "User")') == 4
assert "s->init_state.url_bucket = luaL_checkstring(L, 3)" not in base_request
assert "s->init_state.url_bucket = luaL_checkstring(L, 3)" in target_request
assert "if (luaL_dostring(L, script.c_str()) != LUA_OK)" in base_request
assert "if (luaL_dostring(L, script.c_str()) != LUA_OK)" in target_request

base_test = show("v16.2.15", "src/test/rgw/test_rgw_lua.cc")
target_test = show("v17.2.7", "src/test/rgw/test_rgw_lua.cc")
assert "TEST(TestRGWLua, InvalidField)" in base_test
assert "TEST(TestRGWLua, InvalidField)" in target_test
assert "TEST(TestRGWLua, WriteBucket)" not in base_test
assert "TEST(TestRGWLua, WriteBucket)" in target_test
assert "TEST(TestRGWLua, WriteBucketFail)" in target_test
assert "TEST(TestRGWLua, User)" not in base_test
assert "TEST(TestRGWLua, User)" in target_test

base_lua = show("v16.2.15", "src/rgw/rgw_lua.cc")
target_lua = show("v17.2.7", "src/rgw/rgw_lua.cc")
assert "package_name_no_version" not in base_lua
assert "package_name_no_version" in target_lua
assert "remove any existing versions of the package" in target_lua
assert "auto lua_script = store->get_lua_script_manager()" in target_lua

# The RADOS SAL manager preserves the Pacific pool/OID encoding and idempotent delete.
target_rados = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")
target_rados_h = show("v17.2.7", "src/rgw/rgw_sal_rados.h")
assert "pool = store->get_zone()->get_params().log_pool" in target_rados_h
assert "ceph::decode(script, iter)" in target_rados
assert "ceph::encode(script, bl)" in target_rados
assert "if (r < 0 && r != -ENOENT)" in target_rados

updates = {
    "src/rgw/rgw_lua_utils.h": (
        "affect",
        "RGW-024",
        "RGW-024: Lua metatable errors now use luaL_error instead of throwing C++ exceptions across Lua callbacks, avoiding the documented aarch64 std::terminate path.",
    ),
    "src/rgw/rgw_lua_request.cc": (
        "affect",
        "RGW-025",
        "RGW-025: Quincy Lua request scripts can read the authenticated User, read/write HTTP StorageClass, and rewrite Bucket.Name before bucket resolution; unknown-field errors also use Lua errors.",
    ),
    "src/test/rgw/test_rgw_lua.cc": (
        "affect",
        "RGW-025",
        "RGW-025: Target unit coverage adds successful pre-request bucket rewrite, rejection after bucket resolution, and authenticated User field checks used to validate the new Lua request API.",
    ),
    "src/rgw/rgw_lua.cc": (
        "affect",
        "RGW-026",
        "RGW-026: LuaRocks allowlist entries may include a version; adding replaces every stored version of the same package name and unversioned removal deletes all versions.",
    ),
    "src/rgw/rgw_lua.h": (
        "trivial",
        "",
        "RGW-LUA-DECL-01: Endpoint hunk only follows the SAL Store/RadosStore type split and adds a logging-context parameter to declarations; processing remains in implementation files.",
    ),
    "src/rgw/rgw_lua_request.h": (
        "trivial",
        "",
        "RGW-LUA-DECL-02: Declaration-only SAL RGWRadosStore-to-Store rename plus namespace comment; no request processing body changes in this header.",
    ),
    "doc/radosgw/lua-scripting.rst": (
        "trivial",
        "",
        "RGW-LUA-DOC-01: Documentation describes Lua request fields and package-version commands; executable behavior and validation coverage are classified in RGW-025/RGW-026.",
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
for path, (impact, finding, reason) in updates.items():
    row = by_path[path]
    assert row["status"] == "M", path
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], path
    row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified four RGW Lua rows affect and three rows trivial")
