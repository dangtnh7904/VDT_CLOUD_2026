"""Self-test template and complete modes of the runtime evidence validator."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_runtime_evidence_manifest.py"
TEMPLATE = ROOT / "RUNTIME-EVIDENCE-MANIFEST.template.json"
HASH = "a" * 64


def run(path: Path, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--manifest", str(path), "--mode", mode],
        text=True,
        capture_output=True,
        check=False,
    )


template = json.loads(TEMPLATE.read_text(encoding="utf-8-sig"))
assert run(TEMPLATE, "template").returncode == 0
assert run(TEMPLATE, "complete").returncode != 0

complete = copy.deepcopy(template)
complete["validation_label"] = "RUNTIME_EVIDENCE_COMPLETE"
complete["exact_hop_manifest"] = {
    "uri": "archive://exact-hop.json",
    "sha256": HASH,
    "validation_label": "EXACT_HOP_VALID",
}
complete["run_set"] = {
    "run_set_id": "RUNSET-SYNTHETIC",
    "operator": "validator-self-test",
    "environment": "disposable-synthetic-lab",
    "topology_evidence": "archive://topology.json",
    "started_utc": "2026-10-12T00:00:00Z",
    "ended_utc": "2026-10-12T01:00:00Z",
    "pack_ids": ["TP-01"],
}
complete["archive"] = {
    "uri": "archive://runtime-evidence",
    "manifest_sha256": HASH,
    "owner": "validator-self-test",
}
for result in complete["gate_results"]:
    gate_id = result["gate_id"]
    result.update(
        {
            "status": "PASS",
            "owner": "validator-self-test",
            "result_summary": "Synthetic validator fixture only; no Ceph test was executed.",
            "run_ids": [f"SYNTHETIC-{gate_id}"],
            "blocker_id": "",
            "evidence": [
                {"kind": "raw_output", "uri": f"archive://{gate_id}/raw", "sha256": HASH},
                {"kind": "oracle", "uri": f"archive://{gate_id}/oracle", "sha256": HASH},
                {"kind": "timeline", "uri": f"archive://{gate_id}/timeline", "sha256": HASH},
            ],
        }
    )
complete["summary"] = {"overall_outcome": "PASS", "status_counts": {"PASS": 52}}

with tempfile.TemporaryDirectory(prefix="runtime-evidence-validator-") as temp_dir:
    path = Path(temp_dir) / "complete.json"
    path.write_text(json.dumps(complete, indent=2) + "\n", encoding="utf-8")
    completed = run(path, "complete")
    assert completed.returncode == 0, completed.stderr or completed.stdout

    broken = copy.deepcopy(complete)
    broken["gate_results"][0]["evidence"] = broken["gate_results"][0]["evidence"][:1]
    path.write_text(json.dumps(broken, indent=2) + "\n", encoding="utf-8")
    rejected = run(path, "complete")
    assert rejected.returncode != 0, "complete mode accepted PASS without oracle/timeline"

print("runtime evidence manifest validator self-test: PASS")
