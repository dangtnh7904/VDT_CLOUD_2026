"""Validate action register references, coverage, ownership and status shape."""

import re
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
register_path = root / "UPGRADE-ACTION-REGISTER.md"
matrix_path = root / "LAB-RUNTIME-GATES.md"
allowed_status = {
    "PENDING_INPUT",
    "READY",
    "IN_PROGRESS",
    "DONE",
    "BLOCKED",
    "NOT_APPLICABLE",
}
allowed_phase_prefix = {"B": "BEFORE", "M": "MIXED", "A": "AFTER", "R": "ROLLBACK"}

matrix_text = matrix_path.read_text(encoding="utf-8-sig")
gate_ids = set(re.findall(r"^\| (LAB-\d{3}) \|", matrix_text, re.MULTILINE))

finding_ids = set()
for report in sorted(root.glob("[0-1][0-9]-*.md")):
    report_text = report.read_text(encoding="utf-8-sig")
    for heading in re.findall(r"^### .+$", report_text, re.MULTILINE):
        finding_ids.update(re.findall(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b", heading))

text = register_path.read_text(encoding="utf-8-sig")
rows = [line for line in text.splitlines() if line.startswith("| H3-")]
assert len(rows) == 34, len(rows)

action_ids = []
referenced_gates = set()
statuses = []
for line in rows:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    assert len(cells) == 8, (len(cells), line)
    action_id, findings, decision, evidence, gates, owner, stop, status = cells
    match = re.fullmatch(r"H3-([BMAR])\d{2}", action_id)
    assert match, action_id
    ids = set(re.findall(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b", findings))
    assert ids, action_id
    missing_findings = ids - finding_ids
    assert not missing_findings, (action_id, missing_findings)
    refs = set(re.findall(r"LAB-\d{3}", gates))
    assert refs, action_id
    missing_gates = refs - gate_ids
    assert not missing_gates, (action_id, missing_gates)
    assert len(decision) >= 20, action_id
    assert len(evidence) >= 20, action_id
    assert owner, action_id
    assert len(stop) >= 20, action_id
    assert status in allowed_status, (action_id, status)
    action_ids.append(action_id)
    referenced_gates.update(refs)
    statuses.append(status)

assert len(action_ids) == len(set(action_ids))
assert referenced_gates == gate_ids, sorted(gate_ids - referenced_gates)

for prefix in allowed_phase_prefix:
    numbers = [int(action_id[-2:]) for action_id in action_ids if action_id[3] == prefix]
    assert numbers == list(range(1, len(numbers) + 1)), (prefix, numbers)

print(
    f"Validated {len(rows)} upgrade actions covering {len(referenced_gates)} runtime gates; "
    f"status_counts={dict(sorted(Counter(statuses).items()))}"
)
