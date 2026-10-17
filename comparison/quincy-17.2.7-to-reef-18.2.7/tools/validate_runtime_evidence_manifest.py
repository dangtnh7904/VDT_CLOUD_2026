"""Validate the machine-readable evidence index for all LAB runtime gates."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "comparison": "quincy-17.2.7-to-reef-18.2.7",
    "base_ref": "v17.2.7",
    "base_sha": "b12291d110049b2f35e32e0de30d70e9a4c060d2",
    "target_ref": "v18.2.7",
    "target_sha": "6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad",
}
ALLOWED_STATUS = {"NOT_RUN", "PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}
ALLOWED_EVIDENCE_KIND = {
    "raw_output",
    "oracle",
    "timeline",
    "failure_signal",
    "as_is",
    "approval",
    "recovery",
    "metrics",
    "log",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(f"{field} must be non-empty text")
    return value.strip()


def require_sha256(value: object, field: str) -> str:
    text = require_text(value, field)
    if not SHA256_RE.fullmatch(text):
        raise AssertionError(f"{field} must be a lowercase SHA-256")
    return text


def parse_utc(value: object, field: str) -> datetime:
    text = require_text(value, field)
    if not text.endswith("Z"):
        raise AssertionError(f"{field} must use UTC Z notation")
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise AssertionError(f"{field} is not an ISO-8601 timestamp") from exc


def expected_gate_ids() -> list[str]:
    text = (ROOT / "LAB-RUNTIME-GATES.md").read_text(encoding="utf-8-sig")
    ids = re.findall(r"^\| (LAB-\d{3}) \|", text, re.MULTILINE)
    if len(ids) != 52 or len(ids) != len(set(ids)):
        raise AssertionError(f"runtime matrix gate set is invalid: {len(ids)}")
    return ids


parser = argparse.ArgumentParser()
parser.add_argument("--manifest", type=Path, required=True)
parser.add_argument("--mode", choices=("template", "complete"), default="template")
args = parser.parse_args()

data = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
assert data.get("schema_version") == 1, data.get("schema_version")
assert data.get("comparison") == EXPECTED["comparison"], data.get("comparison")
for side in ("base", "target"):
    section = data.get(side)
    assert isinstance(section, dict), side
    assert section.get("ref") == EXPECTED[f"{side}_ref"], section.get("ref")
    assert section.get("source_sha") == EXPECTED[f"{side}_sha"], section.get("source_sha")

expected_ids = expected_gate_ids()
results = data.get("gate_results")
assert isinstance(results, list), "gate_results"
ids = [item.get("gate_id") for item in results if isinstance(item, dict)]
assert len(ids) == len(results), "every gate result must be an object"
assert ids == expected_ids, "gate_results must contain the 52 matrix gates once, in matrix order"

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
        require_text(artifact.get("uri"), f"{gate_id}.evidence[{index}].uri")
        require_sha256(artifact.get("sha256"), f"{gate_id}.evidence[{index}].sha256")

    if args.mode == "template":
        assert status == "NOT_RUN", (gate_id, status)
        assert not item["owner"] and not item["result_summary"], gate_id
        assert not run_ids and not item["blocker_id"] and not evidence, gate_id
        continue

    assert status != "NOT_RUN", gate_id
    require_text(item["owner"], f"{gate_id}.owner")
    require_text(item["result_summary"], f"{gate_id}.result_summary")
    if status == "PASS":
        assert run_ids and all(value.strip() for value in run_ids), gate_id
        assert {"raw_output", "oracle", "timeline"} <= kinds, gate_id
        assert not item["blocker_id"], gate_id
    elif status == "FAIL":
        assert run_ids and all(value.strip() for value in run_ids), gate_id
        assert {"raw_output", "failure_signal"} <= kinds, gate_id
        require_text(item["blocker_id"], f"{gate_id}.blocker_id")
    elif status == "BLOCKED":
        require_text(item["blocker_id"], f"{gate_id}.blocker_id")
    elif status == "NOT_APPLICABLE":
        assert {"as_is", "approval"} <= kinds, gate_id
        assert not item["blocker_id"], gate_id

summary = data.get("summary")
assert isinstance(summary, dict), "summary"
assert summary.get("status_counts") == dict(sorted(counts.items())), (
    summary.get("status_counts"),
    dict(sorted(counts.items())),
)

if args.mode == "template":
    assert data.get("validation_label") == "NOT_RUNTIME_EVIDENCE_COMPLETE"
    assert summary.get("overall_outcome") == "NOT_RUN"
else:
    assert data.get("validation_label") == "RUNTIME_EVIDENCE_COMPLETE"
    exact = data.get("exact_hop_manifest")
    assert isinstance(exact, dict), "exact_hop_manifest"
    require_text(exact.get("uri"), "exact_hop_manifest.uri")
    require_sha256(exact.get("sha256"), "exact_hop_manifest.sha256")
    assert exact.get("validation_label") == "EXACT_HOP_VALID"

    run_set = data.get("run_set")
    assert isinstance(run_set, dict), "run_set"
    for field in ("run_set_id", "operator", "environment", "topology_evidence"):
        require_text(run_set.get(field), f"run_set.{field}")
    started = parse_utc(run_set.get("started_utc"), "run_set.started_utc")
    ended = parse_utc(run_set.get("ended_utc"), "run_set.ended_utc")
    assert ended >= started, "run_set ended before it started"
    pack_ids = run_set.get("pack_ids")
    assert isinstance(pack_ids, list) and pack_ids, "run_set.pack_ids"
    assert all(re.fullmatch(r"TP-\d{2}", value or "") for value in pack_ids), pack_ids
    assert len(pack_ids) == len(set(pack_ids)), pack_ids

    archive = data.get("archive")
    assert isinstance(archive, dict), "archive"
    require_text(archive.get("uri"), "archive.uri")
    require_sha256(archive.get("manifest_sha256"), "archive.manifest_sha256")
    require_text(archive.get("owner"), "archive.owner")

    expected_outcome = "FAIL" if counts["FAIL"] else "BLOCKED" if counts["BLOCKED"] else "PASS"
    assert summary.get("overall_outcome") == expected_outcome, (
        summary.get("overall_outcome"),
        expected_outcome,
    )

print(
    json.dumps(
        {
            "valid": True,
            "mode": args.mode,
            "manifest": str(args.manifest.resolve()),
            "validation_label": data.get("validation_label"),
            "gates": len(results),
            "status_counts": dict(sorted(counts.items())),
            "overall_outcome": summary.get("overall_outcome"),
        },
        indent=2,
    )
)
