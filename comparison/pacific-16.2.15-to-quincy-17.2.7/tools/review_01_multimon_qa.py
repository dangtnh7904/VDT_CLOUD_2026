"""Review four multimon QA recipe setup and log-filter changes."""

import csv
from pathlib import Path


suite = Path(__file__).resolve().parents[1]
path = suite / "01-osd-pg-recovery.csv"
prefix = "qa/suites/rados/multimon/"
pool_setup = prefix + "no_pools.yaml"
log_filters = {
    prefix + "tasks/mon_clock_no_skews.yaml",
    prefix + "tasks/mon_clock_with_skews.yaml",
    prefix + "tasks/mon_recovery.yaml",
}
targets = log_filters | {pool_setup}

with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in targets} == targets
for row in rows:
    if row["path"] not in targets:
        continue
    assert not row["upgrade_impact"], row["path"]
    row["upgrade_impact"] = "affect"
    if row["path"] == pool_setup:
        row["finding_id"] = "OSD-063"
        row["impact_reason"] = (
            "OSD-063/T01-multimon-no-pools: endpoint replaces devicehealth "
            "monitoring disable with mgr_pool false in overrides.ceph.pre-mgr-commands; "
            "Quincy MGR DB uses this option to guard .mgr creation."
        )
    else:
        row["finding_id"] = "OSD-055"
        row["impact_reason"] = (
            "OSD-055/T01-multimon-pool-app-filter: endpoint adds "
            "POOL_APP_NOT_ENABLED to ceph.log-ignorelist; qa/tasks/ceph.py "
            "excludes matching warning from cluster-log QA failure."
        )
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
print("Reviewed 4 multimon recipes")
