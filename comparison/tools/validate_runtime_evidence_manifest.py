"""Validate a runtime evidence index against scenario IDs in a Markdown source."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


ALLOWED_STATUS = {"NOT_RUN", "PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}
ALLOWED_EVIDENCE_KIND = {
    "raw_output", "oracle", "timeline", "failure_signal", "as_is",
    "approval", "recovery", "metrics", "log",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def need_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(f"{field} must be non-empty text")
    return value.strip()


def need_sha256(value: object, field: str) -> str:
    text = need_text(value, field)
    if not SHA256_RE.fullmatch(text):
        raise AssertionError(f"{field} must be a lowercase SHA-256")
    return text


def parse_utc(value: object, field: str) -> datetime:
    text = need_text(value, field)
    if not text.endswith("Z"):
        raise AssertionError(f"{field} must use UTC Z notation")
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise AssertionError(f"{field} is not ISO-8601") from exc


parser = argparse.ArgumentParser()
parser.add_argument("--manifest", type=Path, required=True)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--id-pattern", action="append", required=True)
parser.add_argument("--comparison", required=True)
parser.add_argument("--base-ref", required=True)
parser.add_argument("--base-sha", required=True)
parser.add_argument("--target-ref", required=True)
parser.add_argument("--target-sha", required=True)
parser.add_argument("--mode", choices=("template", "complete"), default="template")
args = parser.parse_args()

source_text = args.source.read_text(encoding="utf-8-sig")
combined = "|".join(f"(?:{pattern})" for pattern in args.id_pattern)
row_pattern = re.compile(rf"^\|\s*(?:\*\*)?({combined})(?=\s|\*|\|)", re.MULTILINE)
expected_ids: list[str] = []
for match in row_pattern.finditer(source_text):
    scenario_id = match.group(1)
    if scenario_id not in expected_ids:
        expected_ids.append(scenario_id)
if not expected_ids:
    raise AssertionError("no scenario IDs found in source")

data = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
assert data.get("schema_version") == 1
assert data.get("comparison") == args.comparison
for side, expected_ref, expected_sha in (
    ("base", args.base_ref, args.base_sha),
    ("target", args.target_ref, args.target_sha),
):
    section = data.get(side)
    assert isinstance(section, dict), side
    assert section.get("ref") == expected_ref, side
    assert section.get("source_sha") == expected_sha, side

results = data.get("gate_results")
assert isinstance(results, list), "gate_results"
ids = [item.get("gate_id") for item in results if isinstance(item, dict)]
assert len(ids) == len(results), "every result must be an object"
assert ids == expected_ids, "gate_results must match source IDs once, in source order"

counts: Counter[str] = Counter()
for item in results:
    gate_id = item["gate_id"]
    status = item.get("status")
    assert status in ALLOWED_STATUS, (gate_id, status)
    counts[status] += 1
    for field in ("owner", "result_summary", "blocker_id"):
        assert isinstance(item.get(field), str), (gate_id, field)
    run_ids = item.get("run_ids")
    evidence = item.get("evidence")
    assert isinstance(run_ids, list) and all(isinstance(value, str) for value in run_ids), gate_id
    assert isinstance(evidence, list), gate_id
    kinds = set()
    for index, artifact in enumerate(evidence):
        assert isinstance(artifact, dict), (gate_id, index)
        kind = artifact.get("kind")
        assert kind in ALLOWED_EVIDENCE_KIND, (gate_id, kind)
        kinds.add(kind)
        need_text(artifact.get("uri"), f"{gate_id}.evidence[{index}].uri")
        need_sha256(artifact.get("sha256"), f"{gate_id}.evidence[{index}].sha256")
    if args.mode == "template":
        assert status == "NOT_RUN", (gate_id, status)
        assert not item["owner"] and not item["result_summary"]
        assert not run_ids and not item["blocker_id"] and not evidence
        continue
    assert status != "NOT_RUN", gate_id
    need_text(item["owner"], f"{gate_id}.owner")
    need_text(item["result_summary"], f"{gate_id}.result_summary")
    if status == "PASS":
        assert run_ids and all(value.strip() for value in run_ids), gate_id
        assert {"raw_output", "oracle", "timeline"} <= kinds, gate_id
        assert not item["blocker_id"], gate_id
    elif status == "FAIL":
        assert run_ids and all(value.strip() for value in run_ids), gate_id
        assert {"raw_output", "failure_signal"} <= kinds, gate_id
        need_text(item["blocker_id"], f"{gate_id}.blocker_id")
    elif status == "BLOCKED":
        need_text(item["blocker_id"], f"{gate_id}.blocker_id")
    elif status == "NOT_APPLICABLE":
        assert {"as_is", "approval"} <= kinds, gate_id
        assert not item["blocker_id"], gate_id

summary = data.get("summary")
assert isinstance(summary, dict), "summary"
assert summary.get("status_counts") == dict(sorted(counts.items()))
if args.mode == "template":
    assert data.get("validation_label") == "NOT_RUNTIME_EVIDENCE_COMPLETE"
    assert summary.get("overall_outcome") == "NOT_RUN"
else:
    assert data.get("validation_label") == "RUNTIME_EVIDENCE_COMPLETE"
    exact = data.get("exact_hop_manifest")
    assert isinstance(exact, dict)
    need_text(exact.get("uri"), "exact_hop_manifest.uri")
    need_sha256(exact.get("sha256"), "exact_hop_manifest.sha256")
    assert exact.get("validation_label") == "EXACT_HOP_VALID"
    run_set = data.get("run_set")
    assert isinstance(run_set, dict)
    for field in ("run_set_id", "operator", "environment", "topology_evidence"):
        need_text(run_set.get(field), f"run_set.{field}")
    started = parse_utc(run_set.get("started_utc"), "run_set.started_utc")
    ended = parse_utc(run_set.get("ended_utc"), "run_set.ended_utc")
    assert ended >= started
    work_items = run_set.get("work_items")
    assert isinstance(work_items, list) and work_items
    assert all(isinstance(value, str) and value.strip() for value in work_items)
    archive = data.get("archive")
    assert isinstance(archive, dict)
    need_text(archive.get("uri"), "archive.uri")
    need_sha256(archive.get("manifest_sha256"), "archive.manifest_sha256")
    need_text(archive.get("owner"), "archive.owner")
    expected_outcome = "FAIL" if counts["FAIL"] else "BLOCKED" if counts["BLOCKED"] else "PASS"
    assert summary.get("overall_outcome") == expected_outcome

print(json.dumps({
    "valid": True,
    "mode": args.mode,
    "manifest": str(args.manifest.resolve()),
    "source": str(args.source.resolve()),
    "gates": len(results),
    "status_counts": dict(sorted(counts.items())),
    "overall_outcome": summary.get("overall_outcome"),
}, indent=2))
