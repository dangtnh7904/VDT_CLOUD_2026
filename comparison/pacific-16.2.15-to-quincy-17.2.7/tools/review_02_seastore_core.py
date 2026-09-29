"""Record the reviewed SeaStore mount and journal clusters for owner 02."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
csv_path = root / "02-bluestore-bluefs.csv"
review = {
    "src/crimson/os/seastore/seastore.cc": ("SEA-001", "Base SeaStore mount/mkfs were no-op stubs; target mounts devices/transaction manager and persists metadata, changing Crimson SeaStore activation."),
    "src/crimson/os/seastore/seastore.h": ("SEA-001", "Target SeaStore interface/state wires real mount, mkfs, device and metadata handling rather than base stub behavior."),
    "src/crimson/os/seastore/journal.cc": ("SEA-002", "Journal replay changes from per-record scanner to record-group metadata/delta scanner; submit and committed boundary behavior changes."),
    "src/crimson/os/seastore/journal.h": ("SEA-002", "Journal interface adds record submitter/grouped submission and replay state; affects SeaStore persisted journal path."),
    "src/crimson/os/seastore/seastore_types.cc": ("SEA-002", "Target implements grouped record encode/decode, CRC validation and delta extraction in seastore_types; base record encoding lived in journal.cc."),
    "src/crimson/os/seastore/seastore_types.h": ("SEA-002", "Target introduces record_group_header_t and grouped record metadata encoding consumed by journal replay; on-disk compatibility unverified."),
    "src/crimson/os/seastore/transaction_manager.cc": ("SEA-002", "TransactionManager target mount replays journal and submit path tracks record boundaries/journal tail; restart behavior changes."),
    "src/crimson/os/seastore/transaction_manager.h": ("SEA-002", "TransactionManager target interface/state carries journal reference, submit pipeline and root metadata operations used by SeaStore mount."),
}

with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert sum(row["path"] in review for row in rows) == len(review)
for row in rows:
    if row["path"] in review:
        finding, reason = review[row["path"]]
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding
        row["impact_reason"] = f"{finding}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
