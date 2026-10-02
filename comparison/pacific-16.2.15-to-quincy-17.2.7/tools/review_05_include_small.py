"""Classify inspected common include changes with explicit source context."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/include/compat.h": ("MSG-052", "Missing F_OFD_SETLK now falls back to F_SETLK in KernelDevice::_lock; lock lifetime semantics can differ on affected Unix toolchains."),
    "src/include/intarith.h": ("MSG-027", "New popcount helper is used by bloom_filter::density in OSD HitSet/BlueStore filter paths; removed round_down_to is an unused in-tree API."),
    "src/include/rados.h": ("MSG-053", "Defines Quincy release and new noautoscale plus SUPPORTSPOOLEIO flags consumed by MON/OSD/Objecter compatibility paths."),
    "src/include/utime_fmt.h": ("MSG-054", "New fmt utime_t formatter uses UTC whereas ostream localtime uses host timezone, affecting scrub scheduling diagnostics."),
}
trivial = {
    "src/include/Distribution.h": "T05-include-namespace: Qualifies std::vector member types only; Distribution storage and algorithms are unchanged.",
    "src/include/ceph_fs.h": "T05-ceph-fs-comment: Corrects CRUSH rule wording in a comment; packed layout bytes are identical.",
    "src/include/denc.h": "T05-denc-lba: Initializes shift to zero, but every 3-bit switch value (0..7) assigns shift before use; decoded bytes are unchanged.",
    "src/include/mempool.h": "T05-mempool-comment: Expands cacheline alignment explanation; shard fields, padding and aligned(128) are unchanged.",
    "src/include/object.h": "T05-object-namespace: Removes global using namespace std; object_t and encoding declarations are unchanged.",
    "src/include/object_fmt.h": "T05-snap-fmt: New fmt snapid formatter emits head, snapdir or hex exactly as existing ostream formatter; no encoded snap ID change.",
    "src/include/types_fmt.h": "T05-map-fmt: New fmt map formatter emits braces and comma-separated key=value pairs matching existing ostream formatter; diagnostic support only.",
    "src/include/uuid.h": "T05-uuid-compare: Adds lexicographic operator> matching existing operator< reversal; no in-tree use of new operator found.",
}
selected = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name not in selected:
        continue
    assert not row["upgrade_impact"], name
    if name in affect:
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
