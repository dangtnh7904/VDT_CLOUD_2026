"""Classify RGW cloud-transition runtime/QA rows and exact CLS cleanups."""

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


# Endpoint evidence for the mixed-version cloud-transition path.
base_zone = show("v16.2.15", "src/rgw/rgw_zone.h")
target_zone = show("v17.2.7", "src/rgw/rgw_zone.h")
assert "struct RGWZoneGroupPlacementTier" not in base_zone
assert "struct RGWZoneGroupPlacementTier" in target_zone
assert "ENCODE_START(2, 1, bl);" in base_zone
assert "ENCODE_START(3, 1, bl);" in target_zone
assert "encode(tier_targets, bl);" in target_zone
assert "if (struct_v >= 3)" in target_zone and "decode(tier_targets, bl);" in target_zone

base_manifest = show("v16.2.15", "src/rgw/rgw_obj_manifest.h")
target_manifest = show("v17.2.7", "src/rgw/rgw_obj_manifest.h")
assert "ENCODE_START(7, 6, bl);" in base_manifest
assert "ENCODE_START(8, 6, bl);" in target_manifest
assert "encode(tier_type, bl);" not in base_manifest
assert "encode(tier_type, bl);" in target_manifest
assert 'if (tier_type != "cloud-s3")' in target_manifest

base_lc = show("v16.2.15", "src/rgw/rgw_lc.cc")
target_lc = show("v17.2.7", "src/rgw/rgw_lc.cc")
assert 'oc.tier.tier_type == "cloud-s3"' not in base_lc
assert 'oc.tier.tier_type == "cloud-s3"' in target_lc
assert "valid_placement(target_placement)" in base_lc
assert "RGWObjCategory::CloudTiered" in target_lc
assert 'pmanifest->set_tier_type("cloud-s3")' in target_lc
assert "pmanifest->set_obj_size(0)" in target_lc
assert "!oc.tier.retain_head_object" in target_lc

base_op = show("v16.2.15", "src/rgw/rgw_op.cc")
target_op = show("v17.2.7", "src/rgw/rgw_op.cc")
assert 'm.get_tier_type() == "cloud-s3"' not in base_op
assert target_op.count('m.get_tier_type() == "cloud-s3"') == 3
assert target_op.count("ERR_INVALID_OBJECT_STATE") >= 3

target_cls_types = show("v17.2.7", "src/cls/rgw/cls_rgw_types.h")
assert "CloudTiered = 4" in target_cls_types
target_lc_h = show("v17.2.7", "src/rgw/rgw_lc.h")
assert "cloud_targets" in target_lc_h and "get_cloud_targets" in target_lc_h
target_qa = show(
    "v17.2.7",
    "qa/suites/rgw/cloud-transition/tasks/cloud_transition_s3tests.yaml",
)
assert "force-branch: ceph-quincy" in target_qa
assert "cloudtier_tests: True" in target_qa

# The four rgw_gc headers keep the same class/method names and encoding payload;
# their endpoint hunks only replace include guards with pragma once/style lines.
for path in (
    "src/cls/rgw_gc/cls_rgw_gc_client.h",
    "src/cls/rgw_gc/cls_rgw_gc_const.h",
    "src/cls/rgw_gc/cls_rgw_gc_ops.h",
    "src/cls/rgw_gc/cls_rgw_gc_types.h",
):
    base = show("v16.2.15", path)
    target = show("v17.2.7", path)
    assert "#pragma once" not in base and "#pragma once" in target
for symbol in (
    "RGW_GC_CLASS",
    "RGW_GC_QUEUE_INIT",
    "RGW_GC_QUEUE_ENQUEUE",
    "RGW_GC_QUEUE_LIST_ENTRIES",
    "RGW_GC_QUEUE_REMOVE_ENTRIES",
    "RGW_GC_QUEUE_UPDATE_ENTRY",
):
    assert symbol in show("v16.2.15", "src/cls/rgw_gc/cls_rgw_gc_const.h")
    assert symbol in show("v17.2.7", "src/cls/rgw_gc/cls_rgw_gc_const.h")

# cls_rgw.cc's endpoint delta is logging spelling/whitespace only.
base_cls = show("v16.2.15", "src/cls/rgw/cls_rgw.cc")
target_cls = show("v17.2.7", "src/cls/rgw/cls_rgw.cc")


def normalize_cls(source: str) -> str:
    source = source.replace('"entered %s()\\n"', '"entered %s"')
    return "\n".join(line.rstrip() for line in source.splitlines() if line.strip())


assert normalize_cls(base_cls) == normalize_cls(target_cls)


affect = {
    "qa/suites/rgw/cloud-transition/+": "RGW-028: Adds the cloud-transition suite marker to the runnable QA matrix used to select feature validation.",
    "qa/suites/rgw/cloud-transition/.qa": "RGW-028: Connects the new cloud-transition suite to shared QA fragments, affecting how the validation job resolves its tasks.",
    "qa/suites/rgw/cloud-transition/cluster.yaml": "RGW-028: Defines the RGW/cloud endpoint test roles used by the new cloud-transition acceptance path.",
    "qa/suites/rgw/cloud-transition/overrides.yaml": "RGW-028: Sets lifecycle timing, frontend, storage classes and test-only crypto options for cloud-transition validation.",
    "qa/suites/rgw/cloud-transition/supported-random-distro$": "RGW-028: Adds the distro selector needed to schedule the cloud-transition QA suite.",
    "qa/suites/rgw/cloud-transition/tasks/cloud_transition_s3tests.yaml": "RGW-028: Runs the cloud-tier configurator and cloud-transition S3 tests from the ceph-quincy external branch, changing available validation coverage.",
    "qa/tasks/rgw_cloudtier.py": "RGW-028: New QA task creates a cloud-s3 placement tier, credentials and endpoint, then restarts RGW before cloud-transition tests.",
    "qa/tasks/s3tests.py": "RGW-028: Passes cloud endpoint credentials and selects the cloud-transition subset when cloudtier_tests is enabled.",
    "src/cls/rgw/cls_rgw_types.h": "RGW-028: Adds persistent bucket-index category value CloudTiered=4 used to mark retained cloud-tier heads.",
    "src/rgw/rgw_lc.cc": "RGW-028: Lifecycle recognizes cloud-s3 tier targets, transfers objects externally, then deletes the source or writes a zero-size cloud-tier manifest/category.",
    "src/rgw/rgw_lc.h": "RGW-028: Lifecycle worker state tracks cloud targets used by the new cloud-transfer path and exposes the set to the transfer helper.",
    "src/rgw/rgw_lc_tier.cc": "RGW-028: Implements plain/multipart transfer, remote bucket/object checks, headers and resumable upload state for cloud-s3 lifecycle transitions.",
    "src/rgw/rgw_lc_tier.h": "RGW-028: Defines the cloud-transfer context and callable interface consumed by lifecycle processing.",
    "src/rgw/rgw_obj_manifest.h": "RGW-028: Advances object manifest to v8/compat6 and persists cloud-s3 tier type/config; Pacific decodes only the older fields.",
}

trivial = {
    "doc/radosgw/cloud-transition.rst": "RGW-CLOUD-DOC-01: New operator documentation describes RGW-028 configuration and limitations but does not itself change runtime or an executed gate.",
    "src/cls/rgw/cls_rgw_types.cc": "RGW-CLS-TEXT-01: Centralizes existing modify-op JSON strings, adds the CloudTiered display name and test-value spelling; persistent enum/manifest behavior is classified in RGW-028.",
    "src/cls/rgw_gc/cls_rgw_gc_client.h": "RGW-CLS-GC-GUARD-01: Header only replaces the include guard with pragma once; GC client signatures are unchanged.",
    "src/cls/rgw_gc/cls_rgw_gc_const.h": "RGW-CLS-GC-GUARD-01: Header only replaces the include guard/adds style lines; every CLS class and method string is unchanged.",
    "src/cls/rgw_gc/cls_rgw_gc_ops.h": "RGW-CLS-GC-GUARD-01: Header only replaces the include guard with pragma once; encoded queue operation fields and versions are unchanged.",
    "src/cls/rgw_gc/cls_rgw_gc_types.h": "RGW-CLS-GC-GUARD-01: Header only replaces the include guard with pragma once; urgent-data fields and encoding remain unchanged.",
    "src/cls/rgw/cls_rgw.cc": "RGW-CLS-LOG-01: Endpoint delta only removes redundant parentheses/newlines from CLS entry logs plus whitespace; object-class logic and wire payloads are unchanged.",
    "src/cls/rgw/cls_rgw_client.cc": "RGW-CLS-CONST-01: Client helpers add const input qualifiers and use bufferlist.to_str() for the same OLH tag bytes; encoded calls/method names are unchanged.",
    "src/cls/rgw/cls_rgw_client.h": "RGW-CLS-CONST-01: Declarations follow the same const-correctness and std namespace cleanup as the unchanged client helper calls.",
    "src/cls/rgw/cls_rgw_const.h": "RGW-CLS-GUARD-01: Replaces the include guard with pragma once without changing RGW CLS method/error constants.",
    "src/cls/rgw/cls_rgw_ops.h": "RGW-CLS-NS-01: Replaces the include guard and qualifies vector/map/string names; lifecycle op encoding versions and field order are unchanged.",
}

assert set(affect).isdisjoint(trivial)
selected = set(affect) | set(trivial)

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
assert selected <= set(by_path)

for path in selected:
    row = by_path[path]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], path
    if path in affect:
        row.update(upgrade_impact="affect", finding_id="RGW-028", impact_reason=affect[path])
    else:
        row.update(upgrade_impact="trivial", finding_id="", impact_reason=trivial[path])

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(affect)} affect and {len(trivial)} trivial RGW rows")
