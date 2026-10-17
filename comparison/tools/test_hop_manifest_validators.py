"""Synthetic positive/negative self-test for shared exact-hop and runtime validators."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
EXACT_VALIDATOR = TOOLS / "validate_exact_hop_manifest.py"
RUNTIME_VALIDATOR = TOOLS / "validate_runtime_evidence_manifest.py"
HASH = "a" * 64
SHA1 = "b" * 40
DIGEST = "sha256:" + "c" * 64

parser = argparse.ArgumentParser()
parser.add_argument("--exact-template", type=Path, required=True)
parser.add_argument("--runtime-template", type=Path, required=True)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--id-pattern", action="append", required=True)
parser.add_argument("--comparison", required=True)
parser.add_argument("--base-ref", required=True)
parser.add_argument("--base-sha", required=True)
parser.add_argument("--target-ref", required=True)
parser.add_argument("--target-sha", required=True)
args = parser.parse_args()


def exact_command(path: Path, mode: str) -> list[str]:
    return [
        sys.executable, str(EXACT_VALIDATOR), "--manifest", str(path),
        "--comparison", args.comparison,
        "--base-ref", args.base_ref, "--base-sha", args.base_sha,
        "--target-ref", args.target_ref, "--target-sha", args.target_sha,
        "--mode", mode,
    ]


def runtime_command(path: Path, mode: str) -> list[str]:
    command = [
        sys.executable, str(RUNTIME_VALIDATOR), "--manifest", str(path),
        "--source", str(args.source), "--comparison", args.comparison,
        "--base-ref", args.base_ref, "--base-sha", args.base_sha,
        "--target-ref", args.target_ref, "--target-sha", args.target_sha,
        "--mode", mode,
    ]
    for pattern in args.id_pattern:
        command.extend(("--id-pattern", pattern))
    return command


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


assert run(exact_command(args.exact_template, "template")).returncode == 0
assert run(exact_command(args.exact_template, "locked")).returncode != 0
assert run(runtime_command(args.runtime_template, "template")).returncode == 0
assert run(runtime_command(args.runtime_template, "complete")).returncode != 0

exact = json.loads(args.exact_template.read_text(encoding="utf-8-sig"))
exact["validation_label"] = "EXACT_HOP_VALID"
for side in ("base", "target"):
    exact[side].update({
        "package_identities": [f"synthetic-{side}-package"],
        "image_reference": f"registry.invalid/{side}@{DIGEST}",
        "image_digest": DIGEST,
        "image_inspect_sha256": HASH,
        "cephadm_sha256": HASH,
        "cephadm_provenance": "synthetic self-test only",
    })
exact["job"].update({
    "run_id": "SYNTHETIC-RUN",
    "work_items": ["SYNTHETIC-WORK-ITEM"],
    "expanded_job_config_sha256": HASH,
    "workload_seed": "synthetic-seed",
    "started_utc": "2026-10-12T00:00:00Z",
    "ended_utc": "2026-10-12T01:00:00Z",
    "topology_evidence": "archive://synthetic/topology",
})
exact["delivery"].update({
    "registry": "registry.invalid",
    "mirror": "mirror.invalid",
    "pull_by_digest_verified": True,
    "evidence": ["archive://synthetic/pull-test"],
})
exact["distro_lanes"] = [{
    "id": "synthetic-lane", "os_release": "synthetic-os", "kernel": "synthetic-kernel",
    "architecture": "x86_64", "container_runtime": "synthetic-runtime",
}]
exact["harness"].update({
    "teuthology_sha": SHA1,
    "expanded_yaml_evidence": "archive://synthetic/expanded.yaml",
})
exact["completion_oracle"].update({
    "passed": True,
    "versions_sha256": HASH,
    "orchestrator_state_sha256": HASH,
    "image_inspect_sha256s": [HASH],
    "expected_daemon_counts": {"mon": 3},
    "observed_daemon_counts": {"mon": 3},
    "role_inventory_evidence": "archive://synthetic/roles",
})
exact["client_matrix"].update({
    "disposition": "LOCKED", "reason": "", "evidence": ["archive://synthetic/clients"],
    "old_client_new_daemon": ["synthetic-pass"], "new_client_old_daemon": ["synthetic-pass"],
})
exact["release_floor_guard"].update({
    "disposition": "NOT_APPLICABLE", "reason": "synthetic run excludes floor mutation",
    "fixture_quarantined": True, "evidence": ["archive://synthetic/floor-guard"],
})
exact["archive"].update({
    "uri": "archive://synthetic/exact-hop", "manifest_sha256": HASH,
    "owner": "validator-self-test", "failure_triage": "synthetic fixture",
})
for pin in exact["pins"]:
    pin.update({"status": "LOCKED", "reason": "", "evidence": [f"archive://synthetic/{pin['id']}"]})
exact["pins"][10].update({
    "status": "NOT_APPLICABLE", "reason": "synthetic run excludes floor mutation",
})

runtime = json.loads(args.runtime_template.read_text(encoding="utf-8-sig"))
runtime["validation_label"] = "RUNTIME_EVIDENCE_COMPLETE"
runtime["exact_hop_manifest"] = {
    "uri": "archive://synthetic/exact-hop.json", "sha256": HASH,
    "validation_label": "EXACT_HOP_VALID",
}
runtime["run_set"].update({
    "run_set_id": "SYNTHETIC-RUNSET", "operator": "validator-self-test",
    "environment": "disposable-synthetic-lab", "topology_evidence": "archive://synthetic/topology",
    "started_utc": "2026-10-12T00:00:00Z", "ended_utc": "2026-10-12T01:00:00Z",
    "work_items": ["SYNTHETIC-WORK-ITEM"],
})
runtime["archive"] = {
    "uri": "archive://synthetic/runtime", "manifest_sha256": HASH,
    "owner": "validator-self-test",
}
for result in runtime["gate_results"]:
    gate_id = result["gate_id"]
    result.update({
        "status": "PASS", "owner": "validator-self-test",
        "result_summary": "Synthetic validator fixture only; no Ceph test was executed.",
        "run_ids": [f"SYNTHETIC-{gate_id}"], "blocker_id": "",
        "evidence": [
            {"kind": "raw_output", "uri": f"archive://synthetic/{gate_id}/raw", "sha256": HASH},
            {"kind": "oracle", "uri": f"archive://synthetic/{gate_id}/oracle", "sha256": HASH},
            {"kind": "timeline", "uri": f"archive://synthetic/{gate_id}/timeline", "sha256": HASH},
        ],
    })
runtime["summary"] = {"overall_outcome": "PASS", "status_counts": {"PASS": len(runtime["gate_results"])}}

with tempfile.TemporaryDirectory(prefix="hop-validator-self-test-") as temp_dir:
    temp = Path(temp_dir)
    exact_path = temp / "exact.json"
    runtime_path = temp / "runtime.json"
    exact_path.write_text(json.dumps(exact, indent=2) + "\n", encoding="utf-8")
    runtime_path.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    exact_result = run(exact_command(exact_path, "locked"))
    assert exact_result.returncode == 0, exact_result.stderr or exact_result.stdout
    runtime_result = run(runtime_command(runtime_path, "complete"))
    assert runtime_result.returncode == 0, runtime_result.stderr or runtime_result.stdout

    broken_exact = copy.deepcopy(exact)
    broken_exact["target"]["image_digest"] = ""
    exact_path.write_text(json.dumps(broken_exact, indent=2) + "\n", encoding="utf-8")
    assert run(exact_command(exact_path, "locked")).returncode != 0

    broken_runtime = copy.deepcopy(runtime)
    broken_runtime["gate_results"][0]["evidence"] = broken_runtime["gate_results"][0]["evidence"][:1]
    runtime_path.write_text(json.dumps(broken_runtime, indent=2) + "\n", encoding="utf-8")
    assert run(runtime_command(runtime_path, "complete")).returncode != 0

print(f"shared manifest validator self-test: PASS ({args.comparison})")
