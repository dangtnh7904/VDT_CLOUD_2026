"""Record reviewed ceph_test_rados dedup coverage changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/test/osd/Object.h": "ObjectDesc adds initialized flushed state consumed by tier flush/evict model checks in RadosModel, changing expected state for dedup QA.",
    "src/test/osd/RadosModel.h": "Rados model adds dedup pool options, randomized set_chunk/snapshot cases, TierEvictOp, flush-state checks and chunk reference-count validation.",
    "src/test/osd/TestRados.cc": "ceph_test_rados exposes dedup chunk algorithm/size and new set_chunk/tier_evict weighted operations, and fails at end when chunk reference-count check fails; target QA recipes exercise them.",
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in affect} == set(affect)
for row in rows:
    if row["path"] in affect:
        assert not row["upgrade_impact"], row["path"]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "OSD-054"
        row["impact_reason"] = f"OSD-054: {affect[row['path']]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
