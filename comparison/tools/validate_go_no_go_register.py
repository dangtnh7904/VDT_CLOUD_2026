"""Validate a GO/NO-GO register without inferring runtime success."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path


ALLOWED_STATUS = {"COMPLETE", "OPEN", "BLOCKED", "FAILED", "NOT_APPLICABLE"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=14)
    args = parser.parse_args()

    text = (args.root.resolve() / "GO-NO-GO-REGISTER.md").read_text(encoding="utf-8-sig")
    rows = [line for line in text.splitlines() if line.startswith("| GNG-")]
    assert len(rows) == args.expected_count, len(rows)

    ids: list[str] = []
    statuses: list[str] = []
    for line in rows:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 7, (len(cells), line)
        criterion_id, criterion, close_condition, evidence, status, owner, next_step = cells
        assert re.fullmatch(r"GNG-\d{2}", criterion_id), criterion_id
        assert len(criterion) >= 5, criterion_id
        assert len(close_condition) >= 20, criterion_id
        assert len(evidence) >= 20, criterion_id
        assert status in ALLOWED_STATUS, (criterion_id, status)
        assert owner, criterion_id
        assert len(next_step) >= 20, criterion_id
        ids.append(criterion_id)
        statuses.append(status)

    assert ids == [f"GNG-{number:02d}" for number in range(1, args.expected_count + 1)]
    counts = Counter(statuses)
    summary_counts = {
        status: int(count)
        for status, count in re.findall(
            r"^\| (COMPLETE|OPEN|BLOCKED|FAILED|NOT_APPLICABLE) \| (\d+) \|",
            text,
            re.MULTILINE,
        )
    }
    assert set(summary_counts) == ALLOWED_STATUS, summary_counts
    assert summary_counts == {status: counts.get(status, 0) for status in ALLOWED_STATUS}

    if counts["FAILED"]:
        decision = "NO_GO"
    elif counts["OPEN"] or counts["BLOCKED"]:
        decision = "NOT_READY_FOR_DECISION"
    else:
        decision = "READY_FOR_APPROVAL"
    decision_match = re.search(
        r"^\*\*Kết luận hiện tại ngày [^:]+: `([A-Z_]+)`\.\*\*",
        text,
        re.MULTILINE,
    )
    assert decision_match, "missing current decision"
    assert decision_match.group(1) == decision, (decision_match.group(1), decision)

    print(
        f"Validated {len(rows)} GO/NO-GO criteria; "
        f"status_counts={dict(sorted(counts.items()))}; decision={decision}"
    )


if __name__ == "__main__":
    main()
