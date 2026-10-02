"""Screen rados-thrash workload QA filter and class-loading changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
prefix = "qa/suites/rados/thrash/workloads/"
log_filter = {
    "admin_socket_objecter_requests.yaml",
    "cache-agent-big.yaml",
    "cache-agent-small.yaml",
    "cache-pool-snaps-readproxy.yaml",
    "cache-pool-snaps.yaml",
    "cache-snaps-balanced.yaml",
    "cache-snaps.yaml",
    "cache.yaml",
    "radosbench-high-concurrency.yaml",
    "radosbench.yaml",
    "redirect.yaml",
    "redirect_promote_tests.yaml",
    "redirect_set_object.yaml",
    "small-objects-balanced.yaml",
    "small-objects-localized.yaml",
    "small-objects.yaml",
    "snaps-few-objects-balanced.yaml",
    "snaps-few-objects-localized.yaml",
    "snaps-few-objects.yaml",
    "write_fadvise_dontneed.yaml",
}
class_recipe = prefix + "rados_api_tests.yaml"
targets = {prefix + name for name in log_filter} | {class_recipe}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in targets} == targets
for row in rows:
    if row["path"] in targets:
        assert not row["upgrade_impact"], row["path"]
        row["upgrade_impact"] = "affect"
        if row["path"] == class_recipe:
            row["finding_id"] = "OSD-062"
            row["impact_reason"] = (
                "OSD-062: rados/test.sh recipe now sets OSD class load/default lists "
                "to wildcard, changing which object classes can load during API QA."
            )
        else:
            row["finding_id"] = "OSD-055"
            row["impact_reason"] = (
                "OSD-055/T01-thrash-pool-app-filter: endpoint hunk adds "
                "POOL_APP_NOT_ENABLED to overrides.ceph.log-ignorelist; "
                "qa/tasks/ceph.py filters matching cluster-log warnings before "
                "marking this workload failed."
            )
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
