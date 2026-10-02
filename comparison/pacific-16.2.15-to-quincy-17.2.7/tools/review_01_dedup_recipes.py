"""Record dedup QA recipes and log acceptance filter changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "qa/suites/rados/thrash/workloads/dedup-io-mixed.yaml": (
        "OSD-054;OSD-055",
        "New recipe enables dedup fastcdc and weighted set_chunk/tier ops; log-ignorelist also excludes POOL_APP_NOT_ENABLED from the QA log failure gate.",
    ),
    "qa/suites/rados/thrash/workloads/dedup-io-snaps.yaml": (
        "OSD-054;OSD-055",
        "New recipe adds snapshot/rollback to dedup fastcdc and tier operations; log-ignorelist excludes POOL_APP_NOT_ENABLED from the QA log failure gate.",
    ),
    "qa/suites/rados/thrash/workloads/set-chunks-read.yaml": (
        "OSD-055",
        "Existing set-chunks-read recipe now excludes POOL_APP_NOT_ENABLED from the cluster-log warning/error check, changing QA acceptance.",
    ),
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
        ids, reason = affect[row["path"]]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = ids
        row["impact_reason"] = f"{ids}: {reason}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
