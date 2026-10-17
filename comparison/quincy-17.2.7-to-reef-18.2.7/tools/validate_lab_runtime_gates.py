"""Validate finding references and status shape in LAB-RUNTIME-GATES.md."""

import re
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
matrix_path = root / "LAB-RUNTIME-GATES.md"
allowed_status = {"NOT_RUN", "PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}

finding_ids = set()
for report in sorted(root.glob("[0-1][0-9]-*.md")):
    text = report.read_text(encoding="utf-8-sig")
    for heading in re.findall(r"^### .+$", text, re.MULTILINE):
        finding_ids.update(re.findall(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b", heading))

text = matrix_path.read_text(encoding="utf-8-sig")
rows = [line for line in text.splitlines() if line.startswith("| LAB-")]
assert len(rows) == 52, len(rows)

scenario_ids = []
referenced_findings = set()
for line in rows:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    assert len(cells) == 8, (len(cells), line)
    scenario_id, tier, findings, precondition, action, passed, failed, status = cells
    assert re.fullmatch(r"LAB-\d{3}", scenario_id), scenario_id
    assert tier in {"P0", "P1"}, tier
    ids = set(re.findall(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b", findings))
    assert ids, scenario_id
    missing = ids - finding_ids
    assert not missing, (scenario_id, missing)
    assert len(precondition) >= 12, scenario_id
    assert len(action) >= 12, scenario_id
    assert len(passed) >= 20, scenario_id
    assert len(failed) >= 20, scenario_id
    assert status in allowed_status, (scenario_id, status)
    scenario_ids.append(scenario_id)
    referenced_findings.update(ids)

assert len(scenario_ids) == len(set(scenario_ids))
assert scenario_ids == sorted(scenario_ids)
assert referenced_findings == finding_ids, sorted(finding_ids - referenced_findings)

status_counts = Counter(
    line.strip().strip("|").split("|")[-1].strip() for line in rows
)

print(
    f"Validated {len(rows)} lab/runtime gates referencing "
    f"{len(referenced_findings)} existing findings; "
    f"status_counts={dict(sorted(status_counts.items()))}"
)
