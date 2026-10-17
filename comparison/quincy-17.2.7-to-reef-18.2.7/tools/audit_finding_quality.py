"""Audit whether each unique finding documents the required evidence dimensions."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--strict", action="store_true")
parser.add_argument("--show", type=int, default=40)
args = parser.parse_args()

finding_re = re.compile(r"\b[A-Z][A-Z0-9]{1,15}-\d{3}\b")
# A report may keep concise operational-closure addenda under level-4 headings.
# Combine those with the primary level-3 finding rather than forcing duplicate
# top-level finding headings.
heading_re = re.compile(r"^#{3,4} .+$", re.MULTILINE)

dimensions = {
    "evidence_anchor": re.compile(
        r"\b(?:CSV|Evidence|Bằng chứng|commit|symbol|caller|callee|hunk|source)\b|"
        r"`[^`]*(?:/|\.(?:cc|h|py|yaml|yml|sh|cmake|rst|json))[^`]*`",
        re.IGNORECASE,
    ),
    "endpoint_behavior": re.compile(
        r"\b(?:Base|Target|Before|After|Quincy|Reef|endpoint|source|target)\b|"
        r"(?:trước|sau) (?:đổi|nâng|target|restart|full)",
        re.IGNORECASE,
    ),
    "activation_applicability": re.compile(
        r"\b(?:Điều kiện|applicability|applicable|conditional|khi|chỉ khi|nếu|phụ thuộc|áp dụng)\b",
        re.IGNORECASE,
    ),
    "mixed_full": re.compile(
        r"\b(?:mixed-version|mixed|rolling|rollout|full Reef|full-version|cohort)\b|"
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

sections_by_id: dict[str, list[tuple[str, str]]] = defaultdict(list)
for report in sorted(root.glob("[0-1][0-9]-*.md")):
    text = report.read_text(encoding="utf-8-sig")
    matches = list(heading_re.finditer(text))
    for index, match in enumerate(matches):
        ids = finding_re.findall(match.group(0))
        if not ids:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[match.start():end]
        for finding_id in ids:
            sections_by_id[finding_id].append((report.name, section))

assert len(sections_by_id) == 188, len(sections_by_id)

results = []
for finding_id in sorted(sections_by_id):
    entries = sections_by_id[finding_id]
    combined = "\n".join(section for _, section in entries)
    present = {
        dimension: bool(pattern.search(combined))
        for dimension, pattern in dimensions.items()
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

missing_counts = Counter(
    dimension for result in results for dimension in result["missing"]
)
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
