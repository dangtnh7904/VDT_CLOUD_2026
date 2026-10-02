"""Review endpoint changes in rados/singleton/all QA recipes."""

import csv
import subprocess
from pathlib import Path


suite = Path(__file__).resolve().parents[1]
repo = suite.parents[1] / "ceph16.2.15" / "ceph"
csv_path = suite / "01-osd-pg-recovery.csv"
prefix = "qa/suites/rados/singleton/all/"
disabled = prefix + "mon-memory-target-compliance.yaml.disabled"

diff = subprocess.run(
    ["git", "diff", "--unified=0", "v16.2.15", "v17.2.7", "--", prefix],
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
targets = {row["path"] for row in rows if row["path"].startswith(prefix)}
assert len(targets) == 38 and targets == set(changes)

for row in rows:
    path = row["path"]
    if path not in targets or path == disabled:
        continue
    assert not row["upgrade_impact"], path
    added = changes[path]["added"]
    removed = changes[path]["removed"]
    mgr = "- sudo ceph config set mgr mgr_pool false --force" in added
    pool_filter = r"- \(POOL_APP_NOT_ENABLED\)" in added
    fallback = any(" || dump_metrics memory:" in item for item in added)
    key_rotation = "- mon/auth_key_rotation.sh" in added
    assert mgr or pool_filter or fallback or key_rotation, path

    allowed_add = {
        "- sudo ceph config set mgr mgr_pool false --force",
        "log-ignorelist:",
        r"- \(POOL_APP_NOT_ENABLED\)",
        "get_heap_property tcmalloc.max_total_thread_cache_byte || dump_metrics memory:",
        "set_heap_property tcmalloc.max_total_thread_cache_bytes 67108864 || dump_metrics memory:",
        "set_heap_property tcmalloc.max_total_thread_cache_bytes 33554432 || dump_metrics memory:",
        "- mon/auth_key_rotation.sh",
    }
    allowed_remove = {
        "- sudo ceph config set mgr mgr/devicehealth/enable_monitoring false --force",
        "get_heap_property tcmalloc.max_total_thread_cache_byte:",
        "set_heap_property tcmalloc.max_total_thread_cache_bytes 67108864:",
        "set_heap_property tcmalloc.max_total_thread_cache_bytes 33554432:",
    }
    assert set(added) <= allowed_add, (path, set(added) - allowed_add)
    assert set(removed) <= allowed_remove, (path, set(removed) - allowed_remove)
    assert mgr == ("- sudo ceph config set mgr mgr/devicehealth/enable_monitoring false --force" in removed)
    assert fallback == ("get_heap_property tcmalloc.max_total_thread_cache_byte:" in removed)

    ids = []
    reasons = []
    if mgr:
        ids.append("OSD-063")
        reasons.append("OSD-063/T01-singleton-mgr-pool: pre-mgr command now disables mgr_pool instead of devicehealth monitoring; Quincy mgr DB checks mgr_pool and may create .mgr, changing the QA pool baseline")
    if pool_filter:
        ids.append("OSD-055")
        reasons.append("OSD-055/T01-singleton-pool-app-filter: recipe adds POOL_APP_NOT_ENABLED to ceph log-ignorelist; qa/tasks/ceph.py excludes matching warnings from test failure")
    if fallback:
        ids.append("OSD-064")
        reasons.append("OSD-064: admin socket QA falls back to dump_metrics memory when a tcmalloc heap command fails; qa/tasks/admin_socket.py runs alternatives split by ||")
    if key_rotation:
        ids.append("OSD-065")
        reasons.append("OSD-065: recipe adds mon/auth_key_rotation.sh to the executed workunit list, exercising pending-key commit and authentication")
    row["upgrade_impact"] = "affect"
    row["finding_id"] = ";".join(ids)
    row["impact_reason"] = "; ".join(reasons)

with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Reviewed {len(targets)-1} active recipes; left one .disabled recipe open")
