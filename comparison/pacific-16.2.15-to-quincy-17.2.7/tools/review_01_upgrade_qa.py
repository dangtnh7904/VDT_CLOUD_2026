"""Record endpoint-screened RADOS upgrade and health QA rows."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
findings = {
    "qa/config/rados.yaml": (
        "OSD-072",
        "QA rados config adds BlueStore zero-block detection and mClock recovery override/high_recovery_ops profile; selected tests run with different OSD settings than the Pacific endpoint.",
    ),
    "qa/suites/rados/upgrade/nautilus-x-singleton": (
        "OSD-073",
        "Endpoint removes the rados/upgrade link to the Nautilus singleton upgrade suite, so that suite is no longer selected through this RADOS path.",
    ),
    "qa/suites/rados/upgrade/parallel": (
        "OSD-073",
        "Endpoint adds the rados/upgrade link to pacific-x/parallel, whose sequence installs Pacific then runs cephadm upgrade alongside workloads and checks one final version.",
    ),
    "qa/tasks/thrashosds-health.yaml": (
        "OSD-074",
        "QA health override drops ignore patterns for MON_DOWN, quorum, OSD-down and PG/backfill conditions; these alerts can now fail a selected thrash test instead of being filtered.",
    ),
}

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in findings} == set(findings)
for row in rows:
    if row["path"] in findings:
        assert not row["upgrade_impact"], row["path"]
        finding_id, reason = findings[row["path"]]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding_id
        row["impact_reason"] = f"{finding_id}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
