"""Classify endpoint Civetweb frontend removal and supporting curl hunk."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

reasons = {
    "src/rgw/rgw_civetweb.cc": "RGW-004: Deletes Civetweb HTTP request I/O implementation used by Pacific's configured civetweb/mongoose frontend.",
    "src/rgw/rgw_civetweb.h": "RGW-004: Deletes Civetweb request transport declarations; target has no replacement for configured civetweb frontend.",
    "src/rgw/rgw_civetweb_frontend.cc": "RGW-004: Deletes Civetweb listener and request callback implementation; target frontend dispatch only constructs Beast/loadgen.",
    "src/rgw/rgw_civetweb_log.cc": "RGW-004: Deletes Civetweb request logging implementation together with the listener path.",
    "src/rgw/rgw_civetweb_log.h": "RGW-004: Deletes Civetweb request logging declaration together with the listener path.",
}
for source, reason in reasons.items():
    matches = [row for row in rows if row["path"] == source]
    assert len(matches) == 1, source
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "RGW-004"
    row["impact_reason"] = reason

for source, suffix in {
    "src/rgw/rgw_main.cc": " RGW-004: Same file drops civetweb/mongoose selection and falls back to Beast only when rgw_frontends list is empty; unsupported configured frontend is skipped before service-map registration.",
    "src/rgw/rgw_frontend.h": " RGW-004: Same file removes RGWCivetWebFrontend and RGWMongooseEnv classes.",
}.items():
    matches = [row for row in rows if row["path"] == source]
    assert len(matches) == 1, source
    row = matches[0]
    assert row["upgrade_impact"] == "affect" and row["finding_id"] == "CFG-008", source
    assert "RGW-004" not in row["impact_reason"], source
    row["impact_reason"] += suffix

matches = [row for row in rows if row["path"] == "src/rgw/rgw_http_client_curl.cc"]
assert len(matches) == 1
row = matches[0]
assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
row["upgrade_impact"] = "trivial"
row["finding_id"] = "RGW-004"
row["impact_reason"] = "RGW-004 support: Old OpenSSL compatibility helper stops checking SSL certificate for removed Civetweb frontend; active Beast branch and curl behavior for supported frontends are unchanged."

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified 5 Civetweb source rows as affect, 1 curl support row as trivial")
