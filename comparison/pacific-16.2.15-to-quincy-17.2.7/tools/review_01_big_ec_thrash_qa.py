"""Record endpoint-screened big-cluster and EC thrash QA recipe changes."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
big_prefix = "qa/suites/big/rados-thrash/"
ec_prefix = "qa/suites/rados/thrash-erasure-code"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = [row for row in rows if not row["upgrade_impact"] and (row["path"].startswith(big_prefix) or (row["path"].startswith(ec_prefix) and "/thrashers/" in row["path"]))]
assert len(selected) == 21
for row in selected:
    path = row["path"]
    row["upgrade_impact"] = "affect"
    if path.startswith(big_prefix):
        row["finding_id"] = "OSD-076"
        if "/clusters/" in path:
            detail = "Big/medium/small QA cluster recipes replace explicit OSD/MON/MGR roles with host/client roles for cephadm deployment, changing test topology."
        elif "/ceph/" in path:
            detail = "Big RADOS thrash QA replaces classic ceph task selection with roleless cephadm, nvme_loop and HWE kernel override."
        elif "/thrashers/" in path:
            detail = "Big RADOS thrash suite deletes its default thrashosds recipe, changing which failure workload the suite can compose."
        else:
            detail = "Big RADOS thrash suite adds a 300-second radosbench workload, changing the selectable QA load."
        row["impact_reason"] = f"OSD-076 big-rados-thrash: {detail}"
    else:
        if path.endswith("/minsize_recovery.yaml"):
            row["finding_id"] = "OSD-055;OSD-063"
            row["impact_reason"] = "OSD-055/063 EC-thrash QA: adds POOL_APP_NOT_ENABLED log filter and changes pre-MGR command from disabling devicehealth monitoring to mgr_pool false, altering pass/fail and pool setup."
        else:
            row["finding_id"] = "OSD-055"
            row["impact_reason"] = "OSD-055 EC-thrash QA: the only endpoint hunk adds POOL_APP_NOT_ENABLED to ceph log-ignorelist, so a selected test can pass despite this warning."

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
