"""Screen remaining small RADOS QA recipe and suite-selector changes."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
dashboard = {
    "qa/suites/rados/dashboard/0-single-container-host.yaml",
    "qa/suites/rados/dashboard/centos_8.stream_container_tools.yaml",
    "qa/suites/rados/dashboard/clusters/2-node-mgr.yaml",
    "qa/suites/rados/dashboard/tasks/dashboard.yaml",
    "qa/suites/rados/dashboard/tasks/e2e.yaml",
}
mgr = {
    "qa/suites/rados/mgr/objectstore",
    "qa/suites/rados/mgr/random-objectstore$",
}
backfill = "qa/suites/rados/standalone/workloads/osd-backfill.yaml"
trivial = {
    "qa/suites/rados/singleton/all/mon-memory-target-compliance.yaml.disabled": "Disabled QA recipe changes pre-MGR command but remains disabled; no executable upgrade/acceptance path is established.",
    "qa/suites/rados/standalone/workloads/c2c.yaml": "New x86_64 perf c2c sampling workunit studies cacheline behavior; it has no pass/fail assertion tied to upgrade continuity or acceptance.",
}
selected = dashboard | mgr | {backfill} | set(trivial)
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
    if path in dashboard:
        fid = "OSD-087"
        reason = "Dashboard QA changes selected host/distro topology, OSD mClock recovery override and adds cephadm e2e OSD creation workunit; test environment and validation coverage differ."
    elif path in mgr:
        fid = "OSD-088"
        reason = "RADOS MGR suite selector changes from all objectstores to random-objectstore$ with identical symlink target, reducing per-run backend coverage."
    elif path == backfill:
        fid = "OSD-089"
        reason = "RADOS standalone suite adds a distinct osd-backfill workunit after the four backfill scripts move into qa/standalone/osd-backfill; selected recovery QA coverage changes."
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-remaining-qa: {trivial[path]}"
        continue
    row["upgrade_impact"] = "affect"
    row["finding_id"] = fid
    row["impact_reason"] = f"{fid}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
