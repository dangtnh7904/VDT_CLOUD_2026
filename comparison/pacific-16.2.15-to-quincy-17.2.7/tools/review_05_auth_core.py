"""Classify reviewed CephX and KeyRing endpoint deltas for owner 05."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/auth/Auth.h": ("MSG-001", "EntityAuth wire structure grows from v2 to v3 with pending_key, changing persisted/auth state used by pending CephX rotation."),
    "src/auth/Crypto.h": ("MSG-001", "CryptoKey::clear is used by AuthMonitor when committing a pending key, changing pending-key lifecycle."),
    "src/auth/KeyRing.cc": ("MSG-001;MSG-002", "KeyRing prints/exports pending keys; decode no longer first attempts binary map format and instead parses plaintext directly."),
    "src/auth/KeyRing.h": ("MSG-001;MSG-002", "KeyRing can add both active and pending keys and its decoder contract is now plaintext-only."),
    "src/auth/cephx/CephxKeyServer.cc": ("MSG-001", "KeyServer tracks pending keys actually used for MON AuthMonitor to commit rotation."),
    "src/auth/cephx/CephxKeyServer.h": ("MSG-001", "KeyServer stores and exposes used_pending_keys consumed by MON rotation path."),
    "src/auth/cephx/CephxServiceHandler.cc": ("MSG-001", "CephX challenge validation falls back to pending_key and encrypts ticket with the accepted key, permitting overlap during rotation."),
}
trivial = {
    "src/auth/AuthClientHandler.h": "T05-auth: Removes unused MAuthReply forward declaration; no client handler logic or wire format changes.",
    "src/auth/Crypto.cc": "T05-auth: Moves getentropy include under existing conditional and suppresses deprecated API warnings; no cryptographic operation changes in the endpoint hunk.",
    "src/auth/cephx/CephxClientHandler.cc": "T05-auth: Adds explanatory comment for existing msgr1 extra-ticket branch; condition and MonClient behavior are unchanged by this hunk.",
    "src/auth/cephx/CephxSessionHandler.cc": "T05-auth: Replaces init_le32/init_le64 helpers with ceph_le32/ceph_le64 constructors for the same signature fields and order; no change to signature input bytes is shown.",
}
selected = set(affect) | set(trivial)
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    path = row["path"]
    if path not in selected:
        continue
    assert not row["upgrade_impact"], path
    if path in affect:
        fid, reason = affect[path]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[path]
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
