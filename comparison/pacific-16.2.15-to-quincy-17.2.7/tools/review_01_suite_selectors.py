"""Screen RADOS cephadm and MON-thrash selection/filter changes."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
cephadm = {
    "qa/suites/rados/cephadm",
    "qa/suites/rados/cephadm/.qa",
    "qa/suites/rados/cephadm/osds",
    "qa/suites/rados/cephadm/smoke",
    "qa/suites/rados/cephadm/smoke-singlehost",
    "qa/suites/rados/cephadm/workunits",
}
monthrash_added = {
    "qa/suites/rados/monthrash/thrashers/force-sync-many.yaml",
    "qa/suites/rados/monthrash/thrashers/many.yaml",
    "qa/suites/rados/monthrash/thrashers/one.yaml",
    "qa/suites/rados/monthrash/thrashers/sync-many.yaml",
    "qa/suites/rados/monthrash/thrashers/sync.yaml",
}
monthrash_removed = {
    "qa/suites/rados/monthrash/workloads/pool-create-delete.yaml",
    "qa/suites/rados/monthrash/workloads/rados_5925.yaml",
    "qa/suites/rados/monthrash/workloads/rados_api_tests.yaml",
}
other = {
    "qa/suites/powercycle/osd/tasks/rados_api_tests.yaml",
    "qa/suites/rados/perf/ceph.yaml",
    "qa/suites/rados/rest/mgr-restful.yaml",
    "qa/suites/rados/valgrind-leaks/1-start.yaml",
    "qa/suites/rados/monthrash/ceph.yaml",
}
selected = cephadm | monthrash_added | monthrash_removed | other
assert len(selected) == 19

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    path = row["path"]
    if path not in selected:
        continue
    assert not row["upgrade_impact"], path
    if path in cephadm:
        ids = "OSD-082"
        reason = "RADOS suite replaces broad cephadm symlink with explicit osds/smoke/smoke-singlehost/workunits selectors, reducing selected cephadm QA jobs; marker rename is heuristic."
    elif path in monthrash_added:
        ids = "OSD-055"
        reason = "MON-thrash variant adds POOL_APP_NOT_ENABLED to log-ignorelist, allowing this warning through the selected QA gate."
    elif path in monthrash_removed:
        ids = "OSD-083"
        reason = "MON-thrash workload removes POOL_APP_NOT_ENABLED from log-ignorelist, so the same warning can fail a selected QA run."
        if path.endswith("rados_api_tests.yaml"):
            ids += ";OSD-062"
            reason += " It also opens all OSD object classes for the RADOS API workunit."
    elif path == "qa/suites/powercycle/osd/tasks/rados_api_tests.yaml":
        ids = "OSD-062"
        reason = "Powercycle RADOS API QA opens all OSD object classes, including the remote-read class now invoked by rados/test.sh."
    elif path == "qa/suites/rados/perf/ceph.yaml":
        ids = "OSD-084;OSD-055"
        reason = "Performance QA raises osd_client_message_cap from default 256 to 5000 in its lab config and adds POOL_APP_NOT_ENABLED filtering; load and pass/fail differ."
    elif path in {"qa/suites/rados/rest/mgr-restful.yaml", "qa/suites/rados/valgrind-leaks/1-start.yaml"}:
        ids = "OSD-055"
        reason = "Selected QA recipe adds POOL_APP_NOT_ENABLED to log-ignorelist, changing its warning acceptance without changing daemon runtime."
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T01-monthrash-debug: only increases client debug monc/ms logging in a QA recipe; no changed test assertion, runtime default or upgrade gate established."
        continue
    row["upgrade_impact"] = "affect"
    row["finding_id"] = ids
    row["impact_reason"] = f"{ids}: {reason}"

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
