"""Validate the As-Is evidence register and references to runtime gates."""

import re
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
register_path = root / "AS-IS-EVIDENCE.md"
matrix_path = root / "LAB-RUNTIME-GATES.md"
allowed_status = {"NOT_CAPTURED", "CAPTURED", "BLOCKED", "NOT_APPLICABLE"}

matrix_text = matrix_path.read_text(encoding="utf-8-sig")
gate_ids = set(re.findall(r"^\| (LAB-\d{3}) \|", matrix_text, re.MULTILINE))

text = register_path.read_text(encoding="utf-8-sig")
rows = [line for line in text.splitlines() if line.startswith("| AS-")]
assert len(rows) == 24, len(rows)

evidence_ids = []
referenced_gates = set()
statuses = []
for line in rows:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    assert len(cells) == 6, (len(cells), line)
    evidence_id, scope, collection, artifact, gates, status = cells
    assert re.fullmatch(r"AS-\d{3}", evidence_id), evidence_id
    assert len(scope) >= 3, evidence_id
    assert len(collection) >= 20, evidence_id
    assert len(artifact) >= 20, evidence_id
    ids = set(re.findall(r"LAB-\d{3}", gates))
    assert ids, evidence_id
    missing = ids - gate_ids
    assert not missing, (evidence_id, missing)
    assert status in allowed_status, (evidence_id, status)
    evidence_ids.append(evidence_id)
    referenced_gates.update(ids)
    statuses.append(status)

assert len(evidence_ids) == len(set(evidence_ids))
assert evidence_ids == sorted(evidence_ids)
assert referenced_gates == gate_ids, sorted(gate_ids - referenced_gates)

print(
    f"Validated {len(rows)} As-Is evidence groups referencing "
    f"{len(referenced_gates)} runtime gates; "
    f"status_counts={dict(sorted(Counter(statuses).items()))}"
)
