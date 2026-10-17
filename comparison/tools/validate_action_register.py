"""Validate upgrade-action references, coverage, ownership and status shape."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path


ALLOWED_STATUS = {
    "PENDING_INPUT", "READY", "IN_PROGRESS", "DONE", "BLOCKED", "NOT_APPLICABLE"
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-source", type=Path, required=True)
    parser.add_argument("--gate-pattern", action="append", required=True)
    parser.add_argument("--action-prefix", required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    return parser.parse_args()


def collect_ids(text: str, patterns: list[str]) -> set[str]:
    ids: set[str] = set()
    for pattern in patterns:
        ids.update(re.findall(rf"(?<![A-Z0-9_-])(?:{pattern})(?![A-Z0-9_-])", text))
    return ids


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    gate_ids = collect_ids(
        args.runtime_source.resolve().read_text(encoding="utf-8-sig"),
        args.gate_pattern,
    )
    assert gate_ids, "runtime source contains no gate IDs"

    finding_ids: set[str] = set()
    for report in sorted(root.glob("[0-1][0-9]-*.md")):
        report_text = report.read_text(encoding="utf-8-sig")
        for heading in re.findall(r"^### .+$", report_text, re.MULTILINE):
            finding_ids.update(re.findall(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b", heading))
    assert finding_ids, "component reports contain no stable finding IDs"

    text = (root / "UPGRADE-ACTION-REGISTER.md").read_text(encoding="utf-8-sig")
    row_prefix = f"| {args.action_prefix}-"
    rows = [line for line in text.splitlines() if line.startswith(row_prefix)]
    assert len(rows) == args.expected_count, len(rows)

    action_pattern = re.compile(rf"{re.escape(args.action_prefix)}-([BMAR])(\d{{2}})")
    action_ids: list[str] = []
    phase_numbers: dict[str, list[int]] = {phase: [] for phase in "BMAR"}
    referenced_gates: set[str] = set()
    statuses: list[str] = []
    for line in rows:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 8, (len(cells), line)
        action_id, findings, decision, evidence, gates, owner, stop, status = cells
        match = action_pattern.fullmatch(action_id)
        assert match, action_id
        ids = set(re.findall(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b", findings))
        assert ids, action_id
        assert not ids - finding_ids, (action_id, sorted(ids - finding_ids))
        refs = collect_ids(gates, args.gate_pattern)
        assert refs, action_id
        assert not refs - gate_ids, (action_id, sorted(refs - gate_ids))
        assert len(decision) >= 20, action_id
        assert len(evidence) >= 20, action_id
        assert owner, action_id
        assert len(stop) >= 20, action_id
        assert status in ALLOWED_STATUS, (action_id, status)
        action_ids.append(action_id)
        phase_numbers[match.group(1)].append(int(match.group(2)))
        referenced_gates.update(refs)
        statuses.append(status)

    assert len(action_ids) == len(set(action_ids))
    assert referenced_gates == gate_ids, sorted(gate_ids - referenced_gates)
    for phase, numbers in phase_numbers.items():
        assert numbers == list(range(1, len(numbers) + 1)), (phase, numbers)

    print(
        f"Validated {len(rows)} upgrade actions covering {len(referenced_gates)} runtime gates; "
        f"status_counts={dict(sorted(Counter(statuses).items()))}"
    )


if __name__ == "__main__":
    main()
