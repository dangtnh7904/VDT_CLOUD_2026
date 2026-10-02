"""Review endpoint changes in rados/singleton-nomsgr/all recipes."""

import csv
import subprocess
from pathlib import Path


suite = Path(__file__).resolve().parents[1]
repo = suite.parents[1] / "ceph16.2.15" / "ceph"
csv_path = suite / "01-osd-pg-recovery.csv"
prefix = "qa/suites/rados/singleton-nomsgr/all/"
crushdiff = prefix + "crushdiff.yaml"

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
assert len(targets) == 17 and targets == set(changes)

for row in rows:
    path = row["path"]
    if path not in targets:
        continue
    assert not row["upgrade_impact"], path
    added = changes[path]["added"]
    removed = changes[path]["removed"]
    mgr = "- sudo ceph config set mgr mgr_pool false --force" in added
    pool_filter = r"- \(POOL_APP_NOT_ENABLED\)" in added
    assert mgr or pool_filter, path

    if path == crushdiff:
        assert row["status"] == "A" and not removed
        assert "- rados/test_crushdiff.sh" in added
        assert r"- \(PG_DEGRADED\)" in added
    else:
        allowed_add = {
            "- sudo ceph config set mgr mgr_pool false --force",
            "log-ignorelist:",
            r"- \(POOL_APP_NOT_ENABLED\)",
        }
        allowed_remove = {
            "- sudo ceph config set mgr mgr/devicehealth/enable_monitoring false --force"
        }
        assert set(added) <= allowed_add, (path, set(added) - allowed_add)
        assert set(removed) <= allowed_remove, (path, set(removed) - allowed_remove)
        assert mgr == bool(removed), path

    ids = []
    reasons = []
    if mgr:
        ids.append("OSD-063")
        reasons.append("OSD-063/T01-nomsgr-mgr-pool: pre-mgr command disables mgr_pool rather than devicehealth monitoring, changing whether Quincy MGR DB can create .mgr during QA")
    if pool_filter:
        ids.append("OSD-055")
        reasons.append("OSD-055/T01-nomsgr-pool-app-filter: recipe adds POOL_APP_NOT_ENABLED to ceph log-ignorelist, excluding matching cluster-log warning from QA failure")
    if path == crushdiff:
        ids.append("OSD-066")
        reasons.append("OSD-066: new recipe runs rados/test_crushdiff.sh against replicated and EC lab pools and filters PG_DEGRADED, adding a CRUSH movement estimate acceptance path")
    row["upgrade_impact"] = "affect"
    row["finding_id"] = ";".join(ids)
    row["impact_reason"] = "; ".join(reasons)

with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Reviewed {len(targets)} singleton-nomsgr recipes")
