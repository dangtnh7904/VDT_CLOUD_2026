"""Record reviewed Crimson PG and replicated backend endpoint hunks."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/crimson/osd/pg_backend.cc": (
        "OSD-043;OSD-044",
        "Crimson OI_ATTR writes sentinel OID and restores it on load; PGBackend also adds delta_stats, OMAPRMKEYS, cmpxattr and EIO-to-object_corrupted paths."
    ),
    "src/crimson/osd/pg_backend.h": (
        "OSD-044;OSD-045",
        "PG backend API carries interruptible futures, delta_stats and separate submit/completion futures for replica commit."
    ),
    "src/crimson/osd/replicated_backend.cc": (
        "OSD-045",
        "Replicated transaction returns submitted/completed futures; pending version and shared commit promise support duplicate-request ACK after commit."
    ),
    "src/crimson/osd/replicated_backend.h": (
        "OSD-045",
        "Pending transaction stores at_version and shared_promise; request_committed waits for earlier in-flight commit."
    ),
    "src/crimson/osd/replicated_recovery_backend.cc": (
        "OSD-043;OSD-046",
        "Recovery decodes sentinel-OID object_info, discards stale pull/push messages, uses dirty-region subsets without old feature gate and refactors push-target preparation."
    ),
    "src/crimson/osd/replicated_recovery_backend.h": (
        "OSD-046",
        "Recovery API changes to interruptible futures and separates push-target preparation for partial/complete recovery."
    ),
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in affect} == set(affect)
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
