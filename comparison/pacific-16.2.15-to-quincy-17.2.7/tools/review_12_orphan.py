"""Classify the RGW radoslist SLO regression and exact orphan support rows."""

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


# Pacific selects the SLO attribute in the second manifest branch. The Quincy
# endpoint repeats the DLO attribute, so the SLO decode/traversal body is dead.
base_orphan = show("v16.2.15", "src/rgw/rgw_orphan.cc")
target_orphan = show("v17.2.7", "src/rgw/rgw_orphan.cc")
assert base_orphan.count("result.attrs.find(RGW_ATTR_USER_MANIFEST)") == 1
assert base_orphan.count("result.attrs.find(RGW_ATTR_SLO_MANIFEST)") == 1
assert target_orphan.count("result.attrs.find(RGW_ATTR_USER_MANIFEST)") == 2
assert target_orphan.count("result.attrs.find(RGW_ATTR_SLO_MANIFEST)") == 0
for source in (base_orphan, target_orphan):
    assert "RGWSLOInfo slo_info" in source
    assert "::decode(slo_info, bliter)" in source
    assert "add_bucket_filter(bucket_name, obj_key)" in source

# The wrapper remains a read-only candidate generator. Its endpoint change only
# forwards an optional ceph.conf selector; an unset selector preserves commands.
base_script = show("v16.2.15", "src/rgw/rgw-orphan-list")
target_script = show("v17.2.7", "src/rgw/rgw-orphan-list")
assert "CEPH_CONF" not in base_script
assert 'set CEPH_CONF="-c /path/to/ceph.conf"' in target_script
assert "rados ${CEPH_CONF} lspools" in target_script
assert "rados ${CEPH_CONF} ls --pool=" in target_script
assert "radosgw-admin ${CEPH_CONF} bucket radoslist" in target_script
for source in (base_script, target_script):
    assert 'ceph-diff-sorted "$rados_out" "$rgwadmin_out"' in source
    assert "potential orphans found" in source
    assert "only with CAUTION" in source

# Documentation only changes literal command blocks to sphinx-prompt markup.
base_doc = show("v16.2.15", "doc/radosgw/orphans.rst")
target_doc = show("v17.2.7", "doc/radosgw/orphans.rst")
for command in (
    "radosgw-admin orphans find ...",
    "radosgw-admin orphans finish ...",
    "radosgw-admin orphans list-jobs ...",
    "radosgw-admin bucket radoslist [--bucket={bucket-name}]",
):
    assert command in base_doc and command in target_doc
assert ".. prompt:: bash #" not in base_doc
assert target_doc.count(".. prompt:: bash #") == 2

# Manifest runtime behavior in this .cc is unchanged apart from the equivalent
# Zone adapter. Dump/test helpers moved out of the header into this source file.
base_manifest_cc = show("v16.2.15", "src/rgw/rgw_obj_manifest.cc")
target_manifest_cc = show("v17.2.7", "src/rgw/rgw_obj_manifest.cc")
base_dencoder = show("v16.2.15", "src/rgw/rgw_dencoder.cc")
base_json = show("v16.2.15", "src/rgw/rgw_json_enc.cc")
assert "RGWObjManifest::generate_test_instances" not in base_manifest_cc
assert "RGWObjManifest::generate_test_instances" in base_dencoder
assert "RGWObjManifest::generate_test_instances" in target_manifest_cc
assert "RGWObjManifest::dump" in base_json
assert "RGWObjManifest::dump" in target_manifest_cc
assert "zone_svc->get_zone_params()" in base_manifest_cc
assert "zone_svc->get_params()" in target_manifest_cc
for source in (base_manifest_cc, target_manifest_cc):
    assert "explicit_iter == manifest->objs.end()" in source

# The header retains the same persistent orphan record versions/fields and only
# follows namespace/SAL declaration changes; executable behavior is in the .cc.
base_orphan_h = show("v16.2.15", "src/rgw/rgw_orphan.h")
target_orphan_h = show("v17.2.7", "src/rgw/rgw_orphan.h")
for source in (base_orphan_h, target_orphan_h):
    assert "ENCODE_START(1, 1, bl)" in source
    assert "ENCODE_START(2, 1, bl)" in source
    assert "class RGWRadosList" in source
assert "rgw::sal::RGWRadosStore" in base_orphan_h
assert "rgw::sal::RadosStore" in target_orphan_h


updates = {
    "src/rgw/rgw_orphan.cc": (
        "affect",
        "RGW-029",
        "RGW-029: Quincy repeats the DLO attribute test in the SLO branch, making SLO manifest decoding unreachable and changing bucket radoslist dependency enumeration.",
    ),
    "doc/radosgw/orphans.rst": (
        "trivial",
        "",
        "RGW-ORPHAN-DOC-01: Converts existing orphan and bucket-radoslist command examples to sphinx-prompt markup; commands and cautions are unchanged.",
    ),
    "src/rgw/rgw-orphan-list": (
        "trivial",
        "",
        "RGW-ORPHAN-WRAPPER-01: Forwards an optional CEPH_CONF selector to the same read-only rados and bucket-radoslist candidate workflow; the unset default preserves behavior.",
    ),
    "src/rgw/rgw_obj_manifest.cc": (
        "trivial",
        "",
        "RGW-MANIFEST-CLEANUP-01: Moves dump/test-instance helpers from the header and follows the equivalent SAL Zone params accessor; persistent cloud-tier fields are classified in RGW-028's header row.",
    ),
    "src/rgw/rgw_orphan.h": (
        "trivial",
        "",
        "RGW-ORPHAN-DECL-01: Keeps orphan record encoding and interfaces while qualifying STL names and following RGWRadosStore-to-RadosStore/Bucket declaration changes; RGW-029 is in the implementation.",
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
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], path
    row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified the radoslist SLO regression affect and four exact support rows trivial")
