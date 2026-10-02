"""Classify shared address selection and Quincy feature/release definitions."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
findings = {
    "src/common/pick_address.cc": (
        "MSG-005",
        "Address picker adds public_bind_addr mode with -ENOENT fallback, validates mutually exclusive address flags, and orders IPv4/IPv6 candidates before messenger bind/advertisement.",
    ),
    "src/common/ceph_releases.h": (
        "MSG-006",
        "Adds ceph_release_t::quincy used by MON minimum-release and pending-key gates after quorum upgrade.",
    ),
    "src/common/ceph_strings.cc": (
        "MSG-006",
        "Release-name formatter recognizes CEPH_RELEASE_QUINCY, changing release identification in operator-visible output.",
    ),
    "src/include/ceph_features.h": (
        "MSG-006",
        "Adds SERVER_QUINCY to supported feature mask and retires MON_SINGLE_PAXOS, changing peer feature negotiation and require-osd-release guard inputs.",
    ),
}
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in findings} == set(findings)
for row in rows:
    path = row["path"]
    if path not in findings:
        continue
    assert not row["upgrade_impact"], path
    fid, reason = findings[path]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = fid
    row["impact_reason"] = f"{fid}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
