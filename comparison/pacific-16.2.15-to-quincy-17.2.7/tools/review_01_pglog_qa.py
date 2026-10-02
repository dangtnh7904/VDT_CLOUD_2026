"""Record reviewed PG divergence and log trimming QA changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "qa/standalone/osd/divergent-priors.sh": (
        "OSD-056",
        "TEST_divergent_3 retries PG stats/clean wait until first PG up_primary is nonnegative, with a 300-second failure deadline; divergent primary selection and QA outcome differ.",
    ),
    "qa/standalone/osd/repro_long_log.sh": (
        "OSD-057",
        "Long-log QA now checks log_dups_size, changes duplicate tracking/trim inputs and adds duplicate-aware trim case, altering log validation and expected results.",
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
        fid, reason = affect[row["path"]]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
