"""Validate an As-Is evidence register against its runtime-gate source."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path


ALLOWED_STATUS = {"NOT_CAPTURED", "CAPTURED", "BLOCKED", "NOT_APPLICABLE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-source", type=Path, required=True)
    parser.add_argument("--gate-pattern", action="append", required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    return parser.parse_args()


def collect_ids(text: str, patterns: list[str]) -> set[str]:
    ids: set[str] = set()
    for pattern in patterns:
        ids.update(re.findall(rf"(?<![A-Z0-9_-])(?:{pattern})(?![A-Z0-9_-])", text))
    return ids


def main() -> None:
    args = parse_args()
    register_path = args.root.resolve() / "AS-IS-EVIDENCE.md"
    gate_ids = collect_ids(
        args.runtime_source.resolve().read_text(encoding="utf-8-sig"),
        args.gate_pattern,
    )
    assert gate_ids, "runtime source contains no gate IDs"

    text = register_path.read_text(encoding="utf-8-sig")
    rows = [line for line in text.splitlines() if line.startswith("| AS-")]
    assert len(rows) == args.expected_count, len(rows)

    evidence_ids: list[str] = []
    referenced_gates: set[str] = set()
    statuses: list[str] = []
    for line in rows:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 6, (len(cells), line)
        evidence_id, scope, collection, artifact, gates, status = cells
        assert re.fullmatch(r"AS-\d{3}", evidence_id), evidence_id
        assert len(scope) >= 3, evidence_id
        assert len(collection) >= 20, evidence_id
        assert len(artifact) >= 20, evidence_id
        refs = collect_ids(gates, args.gate_pattern)
        assert refs, evidence_id
        assert not refs - gate_ids, (evidence_id, sorted(refs - gate_ids))
        assert status in ALLOWED_STATUS, (evidence_id, status)
        evidence_ids.append(evidence_id)
        referenced_gates.update(refs)
        statuses.append(status)

    assert len(evidence_ids) == len(set(evidence_ids))
    assert evidence_ids == sorted(evidence_ids)
    assert referenced_gates == gate_ids, sorted(gate_ids - referenced_gates)

    print(
        f"Validated {len(rows)} As-Is evidence groups referencing "
        f"{len(referenced_gates)} runtime gates; "
        f"status_counts={dict(sorted(Counter(statuses).items()))}"
    )


if __name__ == "__main__":
    main()
