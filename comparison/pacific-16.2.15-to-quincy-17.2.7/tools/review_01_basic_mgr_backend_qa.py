"""Review RADOS basic, MGR and ObjectStore recipe acceptance changes."""

import csv
import subprocess
from pathlib import Path


suite = Path(__file__).resolve().parents[1]
repo = suite.parents[1] / "ceph16.2.15" / "ceph"
csv_path = suite / "01-osd-pg-recovery.csv"
basic = "qa/suites/rados/basic/tasks/"
mgr = "qa/suites/rados/mgr/tasks/"
backend = "qa/suites/rados/objectstore/backends/"
backend_names = {
    "alloc-hint.yaml",
    "ceph_objectstore_tool.yaml",
    "filejournal.yaml",
    "objectcacher-stress.yaml",
}

diff = subprocess.run(
    ["git", "diff", "--unified=0", "v16.2.15", "v17.2.7", "--", basic, mgr, backend],
    cwd=repo,
    check=True,
    capture_output=True,
    text=True,
).stdout
changes = {}
path = None
for line in diff.splitlines():
    if line.startswith("diff --git a/"):
        path = line.split(" b/", 1)[1]
        changes[path] = {"added": [], "removed": []}
    elif line.startswith("+") and not line.startswith("+++"):
        changes[path]["added"].append(line[1:].strip())
    elif line.startswith("-") and not line.startswith("---"):
        changes[path]["removed"].append(line[1:].strip())

with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
targets = {
    row["path"]
    for row in rows
    if row["path"].startswith((basic, mgr))
    or row["path"] in {backend + name for name in backend_names}
}
assert len(targets) == 19 and targets <= set(changes)

allowed_removed = {
    "",
    r"- \(MON_DOWN\)",
    r"- \(CEPHADM_STRAY_DAEMON\)",
    "- missing hit_sets",
    "- do not have an application enabled",
    "- application not enabled on pool",
    "- pool application",
    "- mons down",
    "- out of quorum",
    "- needs hit_set_type to be set but it is not",
    "min: 1",
}
allowed_added = {
    "",
    "overrides:",
    "ceph:",
    "conf:",
    "osd:",
    "log-ignorelist:",
    r"- \(POOL_APP_NOT_ENABLED\)",
    'osd class load list: "*"',
    'osd class default list: "*"',
    r"- 1 mgr modules have recently crashed \(RECENT_MGR_MODULE_CRASH\)",
    "min: 2",
    "osd mclock profile: high_recovery_ops",
    "osd op queue: wpq",
}
for row in rows:
    path = row["path"]
    if path not in targets:
        continue
    assert not row["upgrade_impact"], path
    added = set(changes[path]["added"])
    removed = set(changes[path]["removed"])
    assert added <= allowed_added, (path, added - allowed_added)
    assert removed <= allowed_removed, (path, removed - allowed_removed)
    add_filter = r"- \(POOL_APP_NOT_ENABLED\)" in added
    remove_filters = bool(removed - {"", "min: 1"})
    wildcard = 'osd class load list: "*"' in added
    crash_filter = r"- 1 mgr modules have recently crashed \(RECENT_MGR_MODULE_CRASH\)" in added
    counter = "min: 2" in added
    mclock = "osd mclock profile: high_recovery_ops" in added
    wpq = "osd op queue: wpq" in added
    assert add_filter or remove_filters or wildcard or crash_filter or counter or mclock or wpq, path
    assert counter == ("min: 1" in removed), path
    assert wildcard == ('osd class default list: "*"' in added), path
    if remove_filters:
        assert path in {basic + "rados_api_tests.yaml", basic + "rados_python.yaml"}, path
    if crash_filter:
        assert path == mgr + "module_selftest.yaml"
    if counter:
        assert path == mgr + "per_module_finisher_stats.yaml"
    if mclock:
        assert path == mgr + "progress.yaml"
    if wpq:
        assert path in {backend + "alloc-hint.yaml", backend + "ceph_objectstore_tool.yaml"}

    ids = []
    reasons = []
    if add_filter:
        ids.append("OSD-055")
        reasons.append("OSD-055/T01-rados-task-pool-app: adds POOL_APP_NOT_ENABLED to ceph.log-ignorelist, excluding matching cluster-log warning from QA failure")
    if remove_filters:
        ids.append("OSD-067")
        reasons.append("OSD-067: removes broad MON/quorum/pool warning filters, so those cluster-log errors can now fail this QA recipe")
    if wildcard:
        ids.append("OSD-062")
        reasons.append("OSD-062: sets OSD class load/default lists to wildcard for rados/test.sh remote-read class coverage")
    if crash_filter:
        ids.append("OSD-070")
        reasons.append("OSD-070: filters RECENT_MGR_MODULE_CRASH during module selftest, changing its cluster-log acceptance condition")
    if counter:
        ids.append("OSD-068")
        reasons.append("OSD-068: raises finisher-telemetry.complete_latency.avgcount minimum from 1 to 2 in check-counter QA")
    if mclock:
        ids.append("OSD-069")
        reasons.append("OSD-069: progress QA forces OSD mClock high_recovery_ops profile, changing recovery timing/config tested")
    if wpq:
        ids.append("OSD-003")
        reasons.append("OSD-003: FileStore QA recipe now explicitly sets osd op queue to wpq, changing the scheduler selected for this test")
    row["upgrade_impact"] = "affect"
    row["finding_id"] = ";".join(ids)
    row["impact_reason"] = "; ".join(reasons)

with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Reviewed {len(targets)} basic/MGR/ObjectStore QA recipes")
