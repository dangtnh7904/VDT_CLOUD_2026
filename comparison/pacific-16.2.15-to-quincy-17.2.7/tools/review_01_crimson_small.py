"""Record reviewed small Crimson source and QA endpoint hunks."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
trivial = {
    "qa/suites/crimson-rados/basic/deploy/ceph.yaml": "Rename-aware diff of basic/ceph.yaml: rehomes Crimson test deployment, moves flavor into install override and adds debug monc; this QA suite is not a production or upgrade gate.",
    "qa/suites/crimson-rados/rbd/deploy/ceph.yaml": "Rename-aware diff of rbd/ceph.yaml: rehomes Crimson test deployment, moves flavor into install override and adds debug monc; this QA suite is not a production or upgrade gate.",
    "qa/suites/crimson-rados/basic/deploy/cephadm.yaml.disabled": "New disabled Crimson cephadm test recipe; not selected by this suite or an upgrade procedure.",
    "qa/suites/crimson-rados/rbd/deploy/cephadm.yaml.disabled": "New disabled Crimson cephadm test recipe; not selected by this suite or an upgrade procedure.",
    "qa/suites/crimson-rados/basic/tasks/rados_api_tests.yaml": "Crimson RADOS API test enables all OSD classes within its QA override; no runtime default or upgrade command changes.",
    "src/crimson/os/cyanstore/cyan_collection.cc": "Only adds std::make_pair using declaration; no changed expression or store operation.",
    "src/crimson/osd/osdmap_gate.cc": "Qualifies existing make_pair call with std::; same pair and epoch gate are used.",
    "src/crimson/osd/pg_map.cc": "Only adds std::make_pair using declaration; no changed expression or PG map operation.",
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in trivial} == set(trivial)
for row in rows:
    name = row["path"]
    if name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-crimson: {trivial[name]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
