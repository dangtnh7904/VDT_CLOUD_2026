"""Classify inspected RGW FastCGI frontend removal rows."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
reasons = {
    "src/rgw/rgw_fcgi.cc": "CFG-008: Deleted FastCGI request I/O implementation RGWFCGX; target no longer has this frontend transport.",
    "src/rgw/rgw_fcgi.h": "CFG-008: Deleted RGWFCGX FastCGI request/response transport declaration and fcgiapp.h dependency.",
    "src/rgw/rgw_fcgi_process.cc": "CFG-008: Deleted RGWFCGXProcess socket bind/accept and request processing path; FastCGI deployments cannot use this RGW target path.",
    "src/rgw/rgw_frontend.h": "CFG-008: Target removes RGWFCGXFrontend construction from the RGW frontend classes; other frontend hunks still need review.",
    "src/rgw/rgw_main.cc": "CFG-008: Target removes the fastcgi/fcgi framework selection and FCGX initialization/shutdown; other startup/frontend hunks still need review.",
    "src/rgw/rgw_process.h": "CFG-008: Target removes RGWFCGXProcess declaration and FastCGI process state; other request-processing hunks still need review.",
    "src/rgw/rgw_request.h": "CFG-008: Target removes RGWFCGXRequest and conditional FastCGI header include; other request hunks still need review.",
}

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for source, reason in reasons.items():
    matches = [row for row in rows if row["path"] == source]
    assert len(matches) == 1, source
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "CFG-008"
    row["impact_reason"] = reason

matches = [row for row in rows if row["path"] == "src/rgw/rgw_frontend.cc"]
assert len(matches) == 1
row = matches[0]
assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
row["upgrade_impact"] = "trivial"
row["impact_reason"] = "Endpoint hunk only adds using namespace std plus whitespace; no frontend selection, socket, request, or restart logic changes in this file."

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified 7 RGW FastCGI rows as affect and 1 frontend row as trivial")
