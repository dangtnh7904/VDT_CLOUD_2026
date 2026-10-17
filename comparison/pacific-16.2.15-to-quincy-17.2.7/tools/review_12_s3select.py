"""Verify and classify RGW S3 Select and adjacent structural changes."""

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


# Pacific already routes POST ?select-type to a CSV S3 Select operation. Quincy
# keeps that activation point but moves the implementation behind a factory.
base_rest = show("v16.2.15", "src/rgw/rgw_rest_s3.cc")
target_rest = show("v17.2.7", "src/rgw/rgw_rest_s3.cc")
base_rest_h = show("v16.2.15", "src/rgw/rgw_rest_s3.h")
target_rest_h = show("v17.2.7", "src/rgw/rgw_rest_s3.h")
assert 'return s->info.args.exists("select-type");' in base_rest_h
assert 'return s->info.args.exists("select-type");' in target_rest_h
assert "return new RGWSelectObj_ObjStore_S3;" in base_rest
assert "return rgw::s3select::create_s3select_op();" in target_rest

base_select_start = base_rest.index("using namespace s3selectEngine;")
base_select = base_rest[base_select_start:]
target_select = show("v17.2.7", "src/rgw/rgw_s3select.cc")
target_select_h = show("v17.2.7", "src/rgw/rgw_s3select.h")
target_private_h = show("v17.2.7", "src/rgw/rgw_s3select_private.h")
assert "RGWOp* create_s3select_op()" in target_select_h + target_select

# CSV event-stream behavior changes independently of the source-file move.
for token in (
    "create_header_continuation",
    "create_header_progress",
    "create_header_stats",
    "create_header_end",
    "send_error_response",
    'std::string output_tag{"OutputSerialization"}',
    'extract_by_tag(m_s3select_query, "Enabled", m_enable_progress)',
    "if (s->obj_size == 0)",
):
    assert token not in base_select
    assert token in target_select

# Parquet is selected from the object key and compiled only when Arrow support
# is enabled. The option defaults on, but packaging/build flags can override it.
for token in (
    'find(".parquet")',
    "m_parquet_type = true;",
    "run_s3select_on_parquet",
    "parquet_magic1",
    "range_request(0, 4, parquet_magic, y)",
):
    assert token in target_select
assert "#ifdef _ARROW_EXIST" in target_select + target_private_h

target_top_cmake = show("v17.2.7", "CMakeLists.txt")
target_src_cmake = show("v17.2.7", "src/CMakeLists.txt")
target_rgw_cmake = show("v17.2.7", "src/rgw/CMakeLists.txt")
target_spec = show("v17.2.7", "ceph.spec.in")
assert 'option(WITH_RADOSGW_SELECT_PARQUET "Support for s3 select on parquet objects" ON)' in target_top_cmake
assert "if(WITH_RADOSGW_SELECT_PARQUET)" in target_src_cmake
assert "build_arrow()" in target_src_cmake
assert "add_definitions(-D_ARROW_EXIST)" in target_rgw_cmake
assert "rgw_s3select.cc" in target_rgw_cmake
assert "-DWITH_RADOSGW_SELECT_PARQUET:BOOL=OFF" in target_spec

# The quota comparisons and cache timing are unchanged at the endpoints. The
# target changes ownership/API calls through SAL and moves JSON methods locally.
base_quota = show("v16.2.15", "src/rgw/rgw_quota.cc")
target_quota = show("v17.2.7", "src/rgw/rgw_quota.cc")
for token in (
    "cur_size + new_size > static_cast<uint64_t>(qinfo.max_size)",
    "cur_size + size > static_cast<uint64_t>(qinfo.max_size)",
    "stats.num_objects + num_objs > static_cast<uint64_t>(qinfo.max_objects)",
    "rgw_bucket_quota_ttl / 2",
):
    assert token in base_quota
    assert token in target_quota
base_json = show("v16.2.15", "src/rgw/rgw_json_enc.cc")
target_json = show("v17.2.7", "src/rgw/rgw_json_enc.cc")
base_xml = show("v16.2.15", "src/rgw/rgw_xml_enc.cc")
target_xml = show("v17.2.7", "src/rgw/rgw_xml_enc.cc")
assert "void RGWQuotaInfo::dump" in base_json
assert "void RGWQuotaInfo::dump" not in target_json
assert "void RGWQuotaInfo::dump" in target_quota

# Website JSON/XML methods moved out of the monolithic encoder files. The
# bounds guard from the Pacific crash fix exists at both endpoints.
base_website = show("v16.2.15", "src/rgw/rgw_website.cc")
target_website = show("v17.2.7", "src/rgw/rgw_website.cc")
guard = "if (key.size() > condition.key_prefix_equals.size())"
assert guard in base_website and guard in target_website
for token in (
    "void RGWRedirectInfo::dump",
    "void RGWBucketWebsiteConf::dump",
):
    assert token in base_json
    assert token in target_website
for token in (
    "void RGWBWRedirectInfo::dump_xml",
    "void RGWBucketWebsiteConf::decode_xml",
):
    assert token in base_xml
    assert token in target_website
    assert token not in target_xml

# The website suite now runs both RGWs under Memcheck when this suite is chosen.
base_website_qa = show("v16.2.15", "qa/suites/rgw/website/overrides.yaml")
target_website_qa = show("v17.2.7", "qa/suites/rgw/website/overrides.yaml")
valgrind_line = "valgrind: [--tool=memcheck, --max-threads=1024]"
assert base_website_qa.count("#        " + valgrind_line) == 2
assert target_website_qa.count("        " + valgrind_line) == 2


new_rows = {
    "src/rgw/rgw_s3select.cc": (
        "affect",
        "RGW-039",
        "RGW-039: Quincy moves S3 Select into a dedicated implementation, changes CSV event-stream/error/output behavior, handles empty objects, and adds the build-conditional Parquet range-read path.",
    ),
    "src/rgw/rgw_s3select.h": (
        "affect",
        "RGW-039",
        "RGW-039: Adds the S3 Select operation factory used by the existing POST select-type activation path.",
    ),
    "src/rgw/rgw_s3select_private.h": (
        "affect",
        "RGW-039",
        "RGW-039: Defines the revised CSV event-stream handler and Arrow-gated Parquet state/range callback used by Quincy S3 Select.",
    ),
    "doc/radosgw/s3select.rst": (
        "trivial",
        "",
        "RGW-S3SELECT-DOC-01: Expands and edits S3 Select documentation; executable CSV/Parquet behavior and artifact conditions are tracked by RGW-039.",
    ),
    "src/rgw/rgw_quota.cc": (
        "trivial",
        "",
        "RGW-QUOTA-SAL-01: Keeps quota comparisons, rounding, cache TTL, refresh, and shard checks while routing equivalent reads/sync through SAL, adding DPP logging, and relocating JSON methods.",
    ),
    "src/rgw/rgw_quota.h": (
        "trivial",
        "",
        "RGW-QUOTA-SAL-01: Updates quota handler declarations for SAL Store and DPP without changing quota fields or limit semantics.",
    ),
    "src/rgw/rgw_website.cc": (
        "trivial",
        "",
        "RGW-ENCODER-MOVE-01: Receives website JSON/XML methods from the monolithic encoder files; redirect matching is unchanged and both endpoints contain the key-length crash guard.",
    ),
    "src/rgw/rgw_json_enc.cc": (
        "trivial",
        "",
        "RGW-ENCODER-MOVE-01: Removes monolithic JSON method definitions after they move to their associated class source files; the remaining placement-rule decoder is unchanged in role.",
    ),
    "src/rgw/rgw_xml_enc.cc": (
        "trivial",
        "",
        "RGW-ENCODER-MOVE-01: Removes monolithic XML method definitions after they move to associated class sources; website methods are present in rgw_website.cc.",
    ),
    "qa/suites/rgw/website/overrides.yaml": (
        "affect",
        "RGW-019",
        "RGW-019: The rgw/website suite now launches both RGW roles under Memcheck, changing validation runtime and pass/fail evidence when this suite is selected.",
    ),
}

existing_additions = {
    "src/rgw/rgw_rest_s3.cc": (
        "RGW-039",
        "RGW-039: Keeps the select-type route but replaces direct construction with the dedicated S3 Select factory; the implementation now provides the revised CSV/Parquet behavior.",
    ),
    "src/rgw/rgw_rest_s3.h": (
        "RGW-039",
        "RGW-039: The select-type activation remains, while the S3 Select operation class moves to the new private implementation header.",
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
    reasons = row["impact_reason"].split(" ") if row["impact_reason"] else []
    if finding not in findings:
        row["finding_id"] = ",".join(findings + [finding])
        row["impact_reason"] = (row["impact_reason"] + " " + reason).strip()
    else:
        assert reason in row["impact_reason"], path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified S3 Select/adjacent rows: 4 affect, 6 trivial; extended 2 existing affect rows")
