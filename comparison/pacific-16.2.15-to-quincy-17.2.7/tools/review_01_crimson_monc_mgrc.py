"""Record endpoint-screened Crimson MON/MGR client behavior."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
findings = {
    "src/crimson/mon/MonClient.cc": (
        "OSD-077",
        "Crimson MON client removes ProtocolV1 authentication, selects msgr2 MON addresses only, and reopens sessions with queued-message, subscription and command resend handling.",
    ),
    "src/crimson/mon/MonClient.h": (
        "OSD-077",
        "Crimson MON client state/API now tracks send readiness, pending MON commands and config/log callbacks used when reconnecting or starting the OSD.",
    ),
    "src/crimson/mgr/client.cc": (
        "OSD-078",
        "Crimson MGR reporting skips the report when its connection is absent instead of asserting, changing behavior across MGR disconnect/restart.",
    ),
    "src/crimson/mgr/client.h": (
        "OSD-078",
        "Crimson MGR stats interface returns move-only MessageURef matching the report/send path; this accompanies the connection handling change.",
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
