"""Classify exact RGW service DPP/namespace/adapter endpoint changes."""

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


# Sync-module interface changes propagate DoutPrefixProvider and qualify STL
# names. Concrete headers keep the same capability flags and object fields.
base_sync = show("v16.2.15", "src/rgw/rgw_sync_module.h")
target_sync = show("v17.2.7", "src/rgw/rgw_sync_module.h")
assert "virtual RGWCoroutine *init_sync(RGWDataSyncCtx *sc)" in base_sync
assert "virtual RGWCoroutine *init_sync(const DoutPrefixProvider *dpp, RGWDataSyncCtx *sc)" in target_sync
assert "return module.get()->create_instance(cct, config, instance)" in base_sync
assert "return module.get()->create_instance(dpp, cct, config, instance)" in target_sync
for path, capability in (
    ("src/rgw/rgw_sync_module_aws.h", "supports_data_export"),
    ("src/rgw/rgw_sync_module_es.h", "supports_data_export"),
    ("src/rgw/rgw_sync_module_log.h", "supports_data_export"),
    ("src/rgw/rgw_sync_module_pubsub.h", "supports_writes"),
):
    base = show("v16.2.15", path)
    target = show("v17.2.7", path)
    assert capability in base and capability in target
    assert "create_instance(CephContext *cct" in base
    assert "create_instance(const DoutPrefixProvider *dpp, CephContext *cct" in target

base_es_rest = show("v16.2.15", "src/rgw/rgw_sync_module_es_rest.cc")
target_es_rest = show("v17.2.7", "src/rgw/rgw_sync_module_es_rest.cc")
assert 'dump_time(s, "LastModified", &e.meta.mtime)' in base_es_rest
assert 'dump_time(s, "LastModified", e.meta.mtime)' in target_es_rest
assert "store->getRados()->get_sync_module()" in base_es_rest
assert "store->get_sync_module()" in target_es_rest

# Bucket service rows only qualify types, route existing diagnostics through
# DPP, or pass that logging provider into the same policy reflection call.
base_bucket = show("v16.2.15", "src/rgw/services/svc_bucket_sobj.cc")
target_bucket = show("v17.2.7", "src/rgw/services/svc_bucket_sobj.cc")
assert 'lderr(cct) << "WARNING: The bucket info cache is inconsistent.' in base_bucket
assert 'ldpp_dout(dpp, -1) << "WARNING: The bucket info cache is inconsistent.' in target_bucket
assert "binfo_cache->invalidate(cache_key)" in base_bucket
assert "binfo_cache->invalidate(cache_key)" in target_bucket
base_bucket_h = show("v16.2.15", "src/rgw/services/svc_bucket_sobj.h")
target_bucket_h = show("v17.2.7", "src/rgw/services/svc_bucket_sobj.h")
assert "map<string, RGWBucketEnt>& m" in base_bucket_h
assert "std::map<std::string, RGWBucketEnt>& m" in target_bucket_h

base_bucket_sync = show("v16.2.15", "src/rgw/services/svc_bucket_sync_sobj.cc")
target_bucket_sync = show("v17.2.7", "src/rgw/services/svc_bucket_sync_sobj.cc")
assert "zone_policy_handler->reflect(nullptr, nullptr," in base_bucket_sync
assert "zone_policy_handler->reflect(dpp, nullptr, nullptr," in target_bucket_sync
base_bucket_sync_h = show("v16.2.15", "src/rgw/services/svc_bucket_sync_sobj.h")
target_bucket_sync_h = show("v17.2.7", "src/rgw/services/svc_bucket_sync_sobj.h")
assert "optional<rgw_zone_id> zone" in base_bucket_sync_h
assert "std::optional<rgw_zone_id> zone" in target_bucket_sync_h

# Config-key RADOS keeps the same secure-connection result; only DPP is added
# to its diagnostic-capable call and the destructor is defined out of line.
base_config = show("v16.2.15", "src/rgw/services/svc_config_key_rados.cc")
target_config = show("v17.2.7", "src/rgw/services/svc_config_key_rados.cc")
assert "maybe_insecure_mon_conn = !svc.rados->check_secure_mon_conn();" in base_config
assert "maybe_insecure_mon_conn = !svc.rados->check_secure_mon_conn(dpp);" in target_config
assert "RGWSI_ConfigKey_RADOS::~RGWSI_ConfigKey_RADOS(){}" in target_config
base_config_h = show("v16.2.15", "src/rgw/services/svc_config_key_rados.h")
target_config_h = show("v17.2.7", "src/rgw/services/svc_config_key_rados.h")
assert "virtual ~RGWSI_ConfigKey_RADOS() override" not in base_config_h
assert "virtual ~RGWSI_ConfigKey_RADOS() override" in target_config_h

# Sysobj list behavior is unchanged; DPP is threaded to the same iterator and
# used for the error log. Headers otherwise qualify the same STL types.
base_sys = show("v16.2.15", "src/rgw/services/svc_sys_obj.cc")
target_sys = show("v17.2.7", "src/rgw/services/svc_sys_obj.cc")
assert "return source.core_svc->pool_list_objects_next(ctx, max, oids, is_truncated)" in base_sys
assert "return source.core_svc->pool_list_objects_next(dpp, ctx, max, oids, is_truncated)" in target_sys
base_core = show("v16.2.15", "src/rgw/services/svc_sys_obj_core.cc")
target_core = show("v17.2.7", "src/rgw/services/svc_sys_obj_core.cc")
assert "ctx.op.get_next(max, oids, is_truncated)" in base_core
assert "ctx.op.get_next(dpp, max, oids, is_truncated)" in target_core
assert "ldout(cct, 10) << \"failed to list objects" in base_core
assert "ldpp_dout(dpp, 10) << \"failed to list objects" in target_core
base_sys_h = show("v16.2.15", "src/rgw/services/svc_sys_obj.h")
target_sys_h = show("v17.2.7", "src/rgw/services/svc_sys_obj.h")
assert "int get_next(int max, std::vector<string> *oids" in base_sys_h
assert "int get_next(const DoutPrefixProvider *dpp, int max, std::vector<std::string> *oids" in target_sys_h
base_core_h = show("v16.2.15", "src/rgw/services/svc_sys_obj_core.h")
target_core_h = show("v17.2.7", "src/rgw/services/svc_sys_obj_core.h")
assert "virtual int pool_list_objects_next(RGWSI_SysObj::Pool::ListCtx& ctx" in base_core_h
assert "virtual int pool_list_objects_next(const DoutPrefixProvider *dpp" in target_core_h

# Remaining rows are declaration/log-lifetime changes with unchanged entry
# points: notify destructor override, sync-module startup, and multipart filter.
base_notify = show("v16.2.15", "src/rgw/services/svc_notify.h")
target_notify = show("v17.2.7", "src/rgw/services/svc_notify.h")
assert "~RGWSI_Notify();" in base_notify
assert "virtual ~RGWSI_Notify() override;" in target_notify
base_modules = show("v16.2.15", "src/rgw/services/svc_sync_modules.cc")
target_modules = show("v17.2.7", "src/rgw/services/svc_sync_modules.cc")
assert "sync_modules_manager->create_instance(cct" in base_modules
assert "sync_modules_manager->create_instance(dpp, cct" in target_modules
base_tier = show("v16.2.15", "src/rgw/services/svc_tier_rados.cc")
target_tier = show("v17.2.7", "src/rgw/services/svc_tier_rados.cc")
assert "MultipartMetaFilter::~MultipartMetaFilter()" not in base_tier
assert "MultipartMetaFilter::~MultipartMetaFilter() {}" in target_tier
assert "bool MultipartMetaFilter::filter" in base_tier and "bool MultipartMetaFilter::filter" in target_tier


sync_rows = (
    "src/rgw/rgw_sync_module.h",
    "src/rgw/rgw_sync_module_aws.h",
    "src/rgw/rgw_sync_module_es.h",
    "src/rgw/rgw_sync_module_es_rest.cc",
    "src/rgw/rgw_sync_module_log.h",
    "src/rgw/rgw_sync_module_pubsub.h",
)
bucket_rows = (
    "src/rgw/services/svc_bucket_sobj.cc",
    "src/rgw/services/svc_bucket_sobj.h",
    "src/rgw/services/svc_bucket_sync_sobj.cc",
    "src/rgw/services/svc_bucket_sync_sobj.h",
)
config_rows = (
    "src/rgw/services/svc_config_key_rados.cc",
    "src/rgw/services/svc_config_key_rados.h",
)
sysobj_rows = (
    "src/rgw/services/svc_sys_obj.cc",
    "src/rgw/services/svc_sys_obj.h",
    "src/rgw/services/svc_sys_obj_core.cc",
    "src/rgw/services/svc_sys_obj_core.h",
)

updates = {}
for path in sync_rows:
    updates[path] = (
        "trivial",
        "",
        "RGW-SYNC-DPP-01: Threads DoutPrefixProvider through the same sync-module interface, qualifies STL types, or follows equivalent dump-time/SAL accessors; capability flags and processing path are unchanged in this row.",
    )
for path in bucket_rows:
    updates[path] = (
        "trivial",
        "",
        "RGW-SVC-BUCKET-DPP-01: Qualifies existing STL types and routes the same cache warning/policy-reflection path through DoutPrefixProvider; bucket cache and policy decisions are unchanged.",
    )
for path in config_rows:
    updates[path] = (
        "trivial",
        "",
        "RGW-SVC-CONFIG-DPP-01: Adds an out-of-line virtual destructor and passes DoutPrefixProvider to the same secure-monitor-connection check; the stored boolean result is unchanged.",
    )
for path in sysobj_rows:
    updates[path] = (
        "trivial",
        "",
        "RGW-SVC-SYSOBJ-DPP-01: Threads DoutPrefixProvider to the same pool iterator/error log and qualifies STL declarations; object listing inputs, outputs and return handling are unchanged.",
    )
updates.update(
    {
        "src/rgw/services/svc_notify.h": (
            "trivial",
            "",
            "RGW-SVC-NOTIFY-DECL-01: Qualifies existing STL fields and marks the same destructor virtual/override; notification retry, watcher and distribution behavior are unchanged here.",
        ),
        "src/rgw/services/svc_sync_modules.cc": (
            "trivial",
            "",
            "RGW-SVC-SYNC-DPP-01: Passes DoutPrefixProvider into the same sync-module factory and replaces global error logging; module selection and startup error handling are unchanged.",
        ),
        "src/rgw/services/svc_tier_rados.cc": (
            "trivial",
            "",
            "RGW-SVC-TIER-DECL-01: Adds an out-of-line empty MultipartMetaFilter destructor and namespace qualification; multipart meta suffix/filter logic is unchanged.",
        ),
    }
)

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

print(f"Classified {len(updates)} exact RGW service DPP/namespace/adapter rows trivial")
