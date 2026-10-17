"""Classify the object-expirer precondition loss and exact SAL adapter rows."""

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


base_core = show("v16.2.15", "src/rgw/rgw_object_expirer_core.cc")
target_core = show("v17.2.7", "src/rgw/rgw_object_expirer_core.cc")
assert ".exp_time = delete_at" in base_core and ".exp_time = delete_at" in target_core
assert "cls_timeindex_add(op, utime_t(delete_at), keyext, hebl)" in base_core
assert "cls_timeindex_add(op, utime_t(delete_at), keyext, hebl)" in target_core
assert "bucket_info.versioning_status(), 0, hint.exp_time" in base_core
assert "bucket_info.versioning_status(), 0, hint.exp_time" not in target_core
assert "ret = obj->delete_object(dpp, &rctx, null_yield)" in target_core
assert "if (ret == -ERR_PRECONDITION_FAILED)" in base_core
assert "if (ret == -ERR_PRECONDITION_FAILED)" in target_core

base_rados = show("v16.2.15", "src/rgw/rgw_rados.cc")
target_rados = show("v17.2.7", "src/rgw/rgw_rados.cc")
for source in (base_rados, target_rados):
    assert "if (!real_clock::is_zero(params.expiration_time))" in source
    assert "if (params.expiration_time != delete_at)" in source
    assert "return -ERR_PRECONDITION_FAILED" in source

target_sal = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")
shortcut = target_sal.split("int RadosObject::delete_object", 1)[1].split("int RadosObject::delete_obj_aio", 1)[0]
assert "versioning_status" in shortcut
assert "expiration_time" not in shortcut

target_reloader = show("v17.2.7", "src/rgw/rgw_realm_reloader.cc")
target_sal_rados = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")
assert 'StoreManager::get_storage(&dp, cct,\n\t\t\t\t   "rados"' in target_reloader
assert 'store->register_to_service_map(&dp, "rgw", service_map_meta)' in target_reloader
assert "return rados->register_to_service_map(dpp, daemon_type, meta)" in target_sal_rados
assert "rgw_rest_init(cct, store->get_zone()->get_zonegroup())" in target_reloader
assert "rgw_log_usage_init(cct, store)" in target_reloader

base_auth = show("v16.2.15", "src/rgw/rgw_auth_registry.h")
target_auth = show("v17.2.7", "src/rgw/rgw_auth_registry.h")
for source in (base_auth, target_auth):
    assert "add_engine(Strategy::Control::SUFFICIENT, s3_main_strategy_plain)" in source
    assert "add_engine(Strategy::Control::FALLBACK, s3_main_strategy_boto2)" in source
    assert "swift_strategy" in source and "sts_strategy" in source

updates = {
    "src/rgw/rgw_object_expirer_core.cc": (
        "affect",
        "RGW-027",
        "RGW-027: Quincy object expiration uses the SAL shortcut delete without propagating hint.exp_time, so the delete path no longer checks that RGW_ATTR_DELETE_AT still matches the queued hint.",
    ),
    "src/rgw/rgw_object_expirer.cc": (
        "trivial",
        "",
        "RGW-OBJEXP-DECL-01: Standalone expirer main only follows StoreManager/Store and argv API changes while explicitly selecting the same RADOS backend; loop and activation remain unchanged.",
    ),
    "src/rgw/rgw_object_expirer_core.h": (
        "trivial",
        "",
        "RGW-OBJEXP-DECL-02: Header follows SAL Store/Zone types and removes the inlined-away bucket-info helper declaration; expiration behavior is classified from the core implementation in RGW-027.",
    ),
    "src/rgw/rgw_realm_reloader.cc": (
        "trivial",
        "",
        "RGW-SAL-REALM-01: Realm reload keeps the same pause, close, RADOS reopen, retry, service-map registration, REST/usage init and resume sequence through equivalent SAL adapters.",
    ),
    "src/rgw/rgw_realm_reloader.h": (
        "trivial",
        "",
        "RGW-SAL-REALM-02: Declaration-only RGWRadosStore-to-Store rename for the same reloader and Pauser interfaces; no scheduling or reload logic changes here.",
    ),
    "src/rgw/rgw_auth_registry.h": (
        "trivial",
        "",
        "RGW-AUTH-DECL-01: Registry constructors pass Store instead of RGWCtl while preserving the same S3 plain/boto fallback ordering and Swift/STS strategy composition; engine behavior is owned by other files.",
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

print("Classified one object-expirer row affect and five exact adapter/declaration rows trivial")
