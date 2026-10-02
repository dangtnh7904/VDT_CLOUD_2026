"""Record Crimson admin-socket observability and fault-injection changes."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
findings = {
    "src/crimson/admin/admin_socket.cc": (
        "OSD-085",
        "Crimson admin socket adds config help and changes command registration/accept gate lifecycle; asok command availability during startup/shutdown can differ.",
    ),
    "src/crimson/admin/admin_socket.h": (
        "OSD-085",
        "Crimson admin socket API removes async registration/shared lock and exposes synchronous hook registration used at OSD asok startup.",
    ),
    "src/crimson/admin/osd_admin.cc": (
        "OSD-086",
        "Crimson OSD admin hooks add metric/perfcounter dump and injectdataerr/injectmdataerr backed by store error injection, changing diagnostic and fault-validation commands.",
    ),
    "src/crimson/admin/osd_admin.h": (
        "OSD-086",
        "Crimson OSD admin hook declarations expose metrics/perfcounter and data/metadata error injection commands registered by OSD::start_asok_admin.",
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
