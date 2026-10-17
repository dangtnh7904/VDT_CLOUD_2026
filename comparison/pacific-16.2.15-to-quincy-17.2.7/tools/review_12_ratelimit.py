"""Classify inspected RGW rate-limit paths for the endpoint comparison."""

import csv
from pathlib import Path


root = Path(__file__).resolve().parents[1]
path = root / "12-rgw.csv"
affect = {
    "src/rgw/rgw_ratelimit.h": "RGW-006: New per-process token buckets enforce configured user/bucket ops and byte debt, with local active-map rotation.",
    "src/rgw/rgw_rest_ratelimit.cc": "RGW-006: New Admin GET/POST ratelimit API reads/writes user/bucket attributes and global period config with ratelimit caps.",
    "src/rgw/rgw_rest_ratelimit.h": "RGW-006: New authenticated Admin ratelimit handler dispatches GET and POST.",
    "src/rgw/rgw_process.cc": "RGW-006: Authenticated request path applies user/bucket limits before execute and returns ERR_RATE_LIMITED; absent at Pacific endpoint.",
    "src/rgw/rgw_rest.cc": "RGW-006: Request/response body transfer now decrements configured per-user/bucket byte tokens after admission.",
    "src/rgw/rgw_zone.h": "RGW-006: Period config encoding advances to v2 with global user/bucket/anonymous rate-limit fields, altering persisted config schema.",
    "src/rgw/rgw_zone.cc": "RGW-006: Period config JSON dump/decode adds global user/bucket/anonymous rate-limit fields.",
    "src/rgw/rgw_sal_rados.cc": "RGW-006: RADOS Store reads global rate-limit configuration from current period for request enforcement.",
    "src/rgw/rgw_sal_rados.h": "RGW-006: RADOS Store interface declares global rate-limit configuration getter.",
    "src/rgw/rgw_sal.h": "RGW-006: SAL Store interface adds global rate-limit getter consumed by RGW request path.",
    "src/rgw/rgw_admin.cc": "RGW-006: radosgw-admin adds user/bucket/global rate-limit management and persists corresponding attributes/config.",
    "src/rgw/rgw_asio_frontend.cc": "RGW-006: Beast frontend passes the active per-process limiter to each RGW request.",
    "src/rgw/rgw_bucket.h": "RGW-006: Bucket admin operation state gains rate-limit fields used by rate-limit CLI workflow.",
    "src/rgw/rgw_user.h": "RGW-006: User admin operation state gains rate-limit fields and specified flags used by CLI workflow.",
}
trivial = {
    "doc/radosgw/admin.rst": "RGW-006 support: Explains the new opt-in rate limit and period commit/restart requirements; prose does not itself change executed upgrade path.",
    "src/test/rgw/test_rgw_ratelimit.cc": "RGW-006 support: New unit tests exercise token rejection/refill/giveback; not an upgrade acceptance recipe.",
    "src/test/rgw/bench_rgw_ratelimit.cc": "RGW-006 support: Standalone token-bucket benchmark, not a production or upgrade execution path.",
    "src/test/rgw/bench_rgw_ratelimit_gc.cc": "RGW-006 support: Standalone active-map GC benchmark, not a production or upgrade execution path.",
}
append = {
    "src/rgw/rgw_common.h": "RGW-006: Adds encoded RGWRateLimitInfo, rate-limit attr and request-state fields.",
    "src/rgw/rgw_common.cc": "RGW-006: Adds rate-limit JSON serialization; existing ERR_RATE_LIMITED S3 mapping remains SlowDown/503.",
    "src/rgw/rgw_main.cc": "RGW-006: Registers Admin ratelimit resource and starts per-process ActiveRateLimiter.",
    "src/rgw/rgw_process.h": "RGW-006: Frontend environment and process_request signature carry active limiter into request path.",
    "qa/tasks/radosgw_admin_rest.py": "RGW-006: Existing Admin REST QA task adds user/bucket/global ratelimit GET/POST checks when selected.",
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for source, reason in affect.items():
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row.update(upgrade_impact="affect", finding_id="RGW-006", impact_reason=reason)
for source, reason in trivial.items():
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row.update(upgrade_impact="trivial", finding_id="RGW-006", impact_reason=reason)
for source, reason in append.items():
    row = by_path[source]
    assert row["upgrade_impact"] == "affect" and "RGW-006:" not in row["impact_reason"], source
    row["impact_reason"] += " " + reason

# The Admin API documentation is supporting evidence for RGW-005/006. It has
# no executable upgrade or acceptance path of its own.
doc = by_path["doc/radosgw/adminops.rst"]
assert doc["upgrade_impact"] == "affect" and doc["finding_id"] == "RGW-005"
doc.update(
    upgrade_impact="trivial",
    finding_id="RGW-005",
    impact_reason="RGW-005/006 support: Documents new Admin info and ratelimit APIs, including a /info JSON nesting mismatch with code/QA; prose is not an executed upgrade recipe.",
)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

build = root / "13-build-packaging-submodules.csv"
with build.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    build_fields = reader.fieldnames
    build_rows = list(reader)
assert build_fields is not None
cmake = [row for row in build_rows if row["path"] == "src/rgw/CMakeLists.txt"]
assert len(cmake) == 1 and cmake[0]["upgrade_impact"] == "affect"
assert "RGW-006:" not in cmake[0]["impact_reason"]
cmake[0]["impact_reason"] += " RGW-006: Adds rgw_rest_ratelimit.cc to RGW build."
with build.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=build_fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(build_rows)

print(f"Classified {len(affect)} affect, {len(trivial)+1} trivial; updated {len(append)+1} cross-evidence rows")
