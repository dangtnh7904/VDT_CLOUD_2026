"""Record reviewed Crimson EC backend API-only stub changes."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
trivial = {
    "src/crimson/osd/ec_backend.cc": "Both endpoint ECBackend::_read and _submit_transaction remain TODO stubs returning ready empty data/acked peers; target only adapts return type to split future API.",
    "src/crimson/osd/ec_backend.h": "ECBackend declarations match new PGBackend interruptible/split-future API; request_committed is a no-op and no EC implementation is added in this endpoint hunk.",
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in trivial} == set(trivial)
for row in rows:
    name = row["path"]
    if name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-crimson-ec-stub: {trivial[name]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
