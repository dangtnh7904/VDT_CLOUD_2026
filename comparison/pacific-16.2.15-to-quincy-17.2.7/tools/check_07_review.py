"""Check owner-07 reviewed rows and CSV wire format while gate is partial."""

import csv
import re
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
blob = (root / "07-mgr-modules-monitoring.csv").read_bytes()
assert blob.startswith(b"\xef\xbb\xbf")
assert blob.count(b"\r\n") == 727
assert blob.count(b"\n") == blob.count(b"\r\n")
with (root / "07-mgr-modules-monitoring.csv").open(encoding="utf-8-sig", newline="") as stream:
    rows = list(csv.DictReader(stream, delimiter=";"))
counts = Counter(row["upgrade_impact"] for row in rows)
assert len(rows) == 726
assert all(row["impact_reason"] for row in rows if row["upgrade_impact"])
assert all(row["finding_id"] for row in rows if row["upgrade_impact"] == "affect")
assert all(not row["finding_id"] for row in rows if row["upgrade_impact"] == "trivial")
ids = set(re.findall(r"^### (MGR-\d+) ", (root / "07-mgr-modules-monitoring.md").read_text(encoding="utf-8"), re.M))
used = {part for row in rows for part in row["finding_id"].split(";") if part}
assert used <= ids, sorted(used - ids)
print(f"owner 07 reviewed: {counts['affect']} affect, {counts['trivial']} trivial, {counts['']} blank; {len(ids)} findings; BOM/CRLF OK")
