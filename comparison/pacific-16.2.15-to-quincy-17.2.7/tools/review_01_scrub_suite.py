"""Record reviewed standalone scrub validation expansion."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "qa/standalone/scrub/osd-recovery-scrub.sh": (
        "OSD-059",
        "Recovery-scrub QA now requires concurrent recovering PGs and at least one scrub observed while recovering; object count and OSD recovery sleep also change.",
    ),
    "qa/standalone/scrub/osd-mapper.sh": (
        "OSD-060",
        "New standalone QA corrupts SnapMapper SNA_ keys on stopped lab OSDs, restarts, deep-scrubs twice and checks repair/error count and key restoration.",
    ),
    "qa/standalone/scrub/osd-scrub-test.sh": (
        "OSD-061",
        "Scrub QA moves setup/teardown into runner, forces wpq for selected cases and adds noscrub/deep-scrub schedule, PG dump duration and objects_scrubbed checks.",
    ),
    "qa/standalone/scrub/scrub-helpers.sh": (
        "OSD-060;OSD-061",
        "New helper creates deterministic scrub lab clusters, enables scrubdebug and extracts schedule/duration from pg query/dump; wait_any_cond returns on any matching predicate.",
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
