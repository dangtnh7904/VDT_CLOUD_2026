"""Audit required evidence dimensions for every stable finding in a suite."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


FINDING_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b")
HEADING_RE = re.compile(r"^#{3,4} .+$", re.MULTILINE)
SECTION_BOUNDARY_RE = re.compile(r"^#{1,4} .+$", re.MULTILINE)
DIMENSIONS = {
    "evidence_anchor": re.compile(
        r"\b(?:CSV|Evidence|Bằng chứng|commit|symbol|caller|callee|hunk|source)\b|"
        r"`[^`]*(?:/|\.(?:cc|h|py|yaml|yml|sh|cmake|rst|json))[^`]*`",
        re.IGNORECASE,
    ),
    "endpoint_behavior": re.compile(
        r"\b(?:Base|Target|Before|After|Pacific|Quincy|Reef|endpoint|source|target)\b|"
        r"(?:trước|sau) (?:đổi|nâng|target|restart|full)",
        re.IGNORECASE,
    ),
    "activation_applicability": re.compile(
        r"\b(?:Điều kiện|applicability|applicable|conditional|khi|chỉ khi|nếu|phụ thuộc|áp dụng)\b",
        re.IGNORECASE,
    ),
    "mixed_full": re.compile(
        r"\b(?:mixed-version|mixed|rolling|rollout|full Pacific|full Quincy|full Reef|full-version|cohort)\b|"
        r"sau khi (?:toàn bộ|full)|nâng tuần tự",
        re.IGNORECASE,
    ),
    "rollback_boundary": re.compile(
        r"\b(?:rollback|failback|downgrade|reversible|irreversible|khôi phục|quay lại|hạ binary|hạ phiên bản)\b",
        re.IGNORECASE,
    ),
    "impact": re.compile(
        r"\b(?:tác động|impact|correctness|availability|security|performance|compatibility|durability|observability|capacity)\b",
        re.IGNORECASE,
    ),
    "confidence": re.compile(r"\b(?:confidence|độ tin cậy)\b", re.IGNORECASE),
    "validation": re.compile(
        r"\b(?:Kiểm chứng|validation|validate|test|lab|scenario|workload|fixture)\b",
        re.IGNORECASE,
    ),
    "activation_mode": re.compile(
        r"\b(?:tự động|automatic|explicit|opt-in|restart|replay|migration|migrate|repair|feature gate|config)\b",
        re.IGNORECASE,
    ),
    "unresolved": re.compile(
        r"\b(?:chưa|unknown|unresolved|cần|thiếu|evidence gap|không suy|không biết)\b",
        re.IGNORECASE,
    ),
}


def finding_sections(text: str) -> list[tuple[str, str]]:
    """Stop finding evidence at every peer, child, or parent heading."""
    boundaries = list(SECTION_BOUNDARY_RE.finditer(text))
    sections = []
    for index, match in enumerate(boundaries):
        if not HEADING_RE.fullmatch(match.group(0)):
            continue
        ids = FINDING_RE.findall(match.group(0))
        if not ids:
            continue
        end = boundaries[index + 1].start() if index + 1 < len(boundaries) else len(text)
        section = text[match.start():end]
        sections.extend((finding_id, section) for finding_id in ids)
    return sections


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--max-incomplete", type=int)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--show", type=int, default=40)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    sections_by_id: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for report in sorted(root.glob("[0-1][0-9]-*.md")):
        text = report.read_text(encoding="utf-8-sig")
        for finding_id, section in finding_sections(text):
            sections_by_id[finding_id].append((report.name, section))

    if args.expected_count is not None:
        assert len(sections_by_id) == args.expected_count, len(sections_by_id)
    assert sections_by_id, "no stable finding headings found"

    results = []
    for finding_id in sorted(sections_by_id):
        entries = sections_by_id[finding_id]
        combined = "\n".join(section for _, section in entries)
        present = {
            dimension: bool(pattern.search(combined))
            for dimension, pattern in DIMENSIONS.items()
        }
        present["substantive_length"] = len(combined) >= 500
        missing = sorted(name for name, value in present.items() if not value)
        results.append(
            {
                "finding_id": finding_id,
                "reports": sorted({name for name, _ in entries}),
                "characters": len(combined),
                "missing": missing,
            }
        )

    missing_counts = Counter(dimension for result in results for dimension in result["missing"])
    complete = [result for result in results if not result["missing"]]
    incomplete = [result for result in results if result["missing"]]
    per_report = defaultdict(lambda: {"findings": 0, "complete": 0})
    for result in results:
        for report in result["reports"]:
            per_report[report]["findings"] += 1
            if not result["missing"]:
                per_report[report]["complete"] += 1

    summary = {
        "unique_findings": len(results),
        "complete_findings": len(complete),
        "incomplete_findings": len(incomplete),
        "missing_dimension_counts": dict(sorted(missing_counts.items())),
        "per_report": dict(sorted(per_report.items())),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for result in incomplete[: args.show]:
        print(
            f"{result['finding_id']}\t{','.join(result['reports'])}\t"
            f"chars={result['characters']}\tmissing={','.join(result['missing'])}"
        )
    if args.strict and incomplete:
        raise SystemExit(1)
    if args.max_incomplete is not None and len(incomplete) > args.max_incomplete:
        raise SystemExit(
            f"finding quality regressed: incomplete={len(incomplete)} "
            f"> max_incomplete={args.max_incomplete}"
        )


if __name__ == "__main__":
    main()
