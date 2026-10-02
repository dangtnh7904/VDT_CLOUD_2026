"""Verify owner-08 binary gate, finding references, and CSV wire format."""

import csv
import re
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
blob = (root / "08-cephadm-orchestrator.csv").read_bytes()
assert blob.startswith(b"\xef\xbb\xbf")
assert blob.count(b"\r\n") == 135
assert blob.count(b"\n") == blob.count(b"\r\n")
with (root / "08-cephadm-orchestrator.csv").open(encoding="utf-8-sig", newline="") as stream:
    rows = list(csv.DictReader(stream, delimiter=";"))
counts = Counter(row["upgrade_impact"] for row in rows)
assert len(rows) == 134 and counts == Counter({"affect": 95, "trivial": 39})
assert all(row["impact_reason"] for row in rows)
assert all(row["finding_id"] for row in rows if row["upgrade_impact"] == "affect")
assert all(not row["finding_id"] for row in rows if row["upgrade_impact"] == "trivial")
ids = set(re.findall(r"^### (ADM-\d+) ", (root / "08-cephadm-orchestrator.md").read_text(encoding="utf-8"), re.M))
used = {part for row in rows for part in row["finding_id"].split(";") if part}
assert used <= ids, sorted(used - ids)
print(f"owner 08 OK: {len(rows)} rows, {counts['affect']} affect, {counts['trivial']} trivial, {len(ids)} findings, BOM/CRLF")
