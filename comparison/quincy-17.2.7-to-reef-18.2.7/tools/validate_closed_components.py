#!/usr/bin/env python3
"""Strictly validate only component CSVs whose binary gate is already complete."""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"affect", "trivial"}
FINDING_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b")


def markdown_finding_ids() -> set[str]:
    result: set[str] = set()
    for path in ROOT.glob("[0-1][0-9]-*.md"):
        text = path.read_text(encoding="utf-8-sig")
        result.update(
            re.findall(r"^### ([A-Z][A-Z0-9]{1,15}-\d{3})\b", text, re.MULTILINE)
        )
    return result


def main() -> None:
    documented = markdown_finding_ids()
    closed: list[str] = []
    totals: Counter[str] = Counter()

    for csv_path in sorted(ROOT.glob("[0-1][0-9]-*.csv")):
        if csv_path.name == "00-file-inventory.csv":
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        values = [row.get("upgrade_impact", "") for row in rows]
        if not values or any(not value for value in values):
            continue

        for line_number, row in enumerate(rows, start=2):
            impact = row.get("upgrade_impact", "")
            reason = row.get("impact_reason", "").strip()
            if impact not in ALLOWED:
                raise RuntimeError(
                    f"{csv_path.name}:{line_number}: invalid impact {impact!r}"
                )
            if not reason:
                raise RuntimeError(
                    f"{csv_path.name}:{line_number}: impact_reason is blank"
                )
            if impact == "affect":
                ids = set(FINDING_RE.findall(row.get("finding_id", "")))
                if not ids:
                    raise RuntimeError(
                        f"{csv_path.name}:{line_number}: affect row has no finding ID"
                    )
                missing = ids - documented
                if missing:
                    raise RuntimeError(
                        f"{csv_path.name}:{line_number}: undocumented IDs {sorted(missing)!r}"
                    )
            totals[impact] += 1
        closed.append(csv_path.stem)

    if not closed:
        raise RuntimeError("no fully classified component CSV found")
    print(
        f"Validated closed components={closed!r}; "
        f"affect={totals['affect']} trivial={totals['trivial']}"
    )


if __name__ == "__main__":
    main()
