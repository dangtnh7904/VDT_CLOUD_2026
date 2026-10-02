"""Classify inspected small common-runtime hunks for owner 05."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
trivial = {
    "src/common/CDC.cc": "T05-common: Replaces init_le64(engine()) with ceph_le64(engine()) for the same generated buffer bytes; target byteorder constructor performs the same little-endian conversion.",
    "src/common/Cycles.h": "T05-common: Adds cstdint include for existing integer types; no timer/cycle implementation change.",
    "src/common/Graylog.h": "T05-common: Moves m_log_dst_valid=false from both old constructors to a member initializer; target delegated constructor preserves initialization.",
    "src/common/MemoryModel.cc": "T05-common: Adds std namespace directive only; no function body or memory target change.",
    "src/common/TrackedOp.cc": "T05-common: Adds braces around existing else branch; num_ops dump field remains under the same condition.",
    "src/common/deleter.h": "T05-common: Adds utility include for existing template usage; no deleter behavior change.",
    "src/common/strescape.h": "T05-common: Replaces string-literal suffix with equivalent concatenation and adds algorithm include; same truncation characters and predicate.",
    "src/common/subsys_types.h": "T05-common: Adds cstdint include for existing type declarations; no subsystem values change.",
    "src/common/weighted_shuffle.h": "T05-common: Removes all-zero early return, but only production caller MonClient checks all-zero weights first and uses std::shuffle; other direct caller is a test.",
    "src/common/win32/dns_resolve.cc": "T05-common: Adds std namespace directive; DNS resolution code is unchanged in this hunk.",
}
affect = {
    "src/common/pick_address.h": ("MSG-005", "New CEPH_PICK_ADDRESS_PUBLIC_BIND flag is selected by OSD address setup to separate public bind and advertised addresses."),
}
selected = set(trivial) | set(affect)
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
    if path in trivial:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[path]
    else:
        fid, reason = affect[path]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
