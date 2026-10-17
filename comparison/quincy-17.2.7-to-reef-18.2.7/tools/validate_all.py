"""Run every offline validator for the Quincy 17.2.7 to Reef 18.2.7 suite."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
tools = root / "tools"
default_repo = root.parents[1] / "ceph17.2.7"
default_plan = root.parent / "PLAN-quincy-17.2.7-to-reef-18.2.7.md"

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=default_repo)
parser.add_argument("--plan", type=Path, default=default_plan)
args = parser.parse_args()

commands = [
    [
        sys.executable,
        str(tools / "validate_comparison.py"),
        "--root",
        str(root),
        "--mode",
        "complete",
        "--plan",
        str(args.plan.resolve()),
        "--require-impact",
        "binary",
    ],
    [sys.executable, str(tools / "validate_closed_components.py")],
    [sys.executable, str(tools / "validate_as_is_evidence.py")],
    [sys.executable, str(tools / "validate_lab_runtime_gates.py")],
    [
        sys.executable,
        str(tools / "validate_runtime_test_selection.py"),
        "--repo",
        str(args.repo.resolve()),
        "--target",
        "v18.2.7",
    ],
    [
        sys.executable,
        str(tools / "validate_exact_hop_pins.py"),
        "--repo",
        str(args.repo.resolve()),
        "--target",
        "v18.2.7",
    ],
    [
        sys.executable,
        str(tools / "audit_native_suite_graph.py"),
        "--repo",
        str(args.repo.resolve()),
        "--target",
        "v18.2.7",
        "--strict",
    ],
    [
        sys.executable,
        str(tools / "validate_exact_hop_manifest.py"),
        "--manifest",
        str(root / "EXACT-HOP-PIN-MANIFEST.template.json"),
        "--mode",
        "template",
    ],
    [sys.executable, str(tools / "test_exact_hop_manifest_validator.py")],
    [
        sys.executable,
        str(tools / "validate_runtime_evidence_manifest.py"),
        "--manifest",
        str(root / "RUNTIME-EVIDENCE-MANIFEST.template.json"),
        "--mode",
        "template",
    ],
    [sys.executable, str(tools / "test_runtime_evidence_manifest_validator.py")],
    [sys.executable, str(tools / "validate_action_register.py")],
    [sys.executable, str(tools / "validate_go_no_go_register.py")],
    [sys.executable, str(tools / "audit_finding_quality.py"), "--strict", "--show", "0"],
]

for index, command in enumerate(commands, start=1):
    script = Path(command[1]).name
    print(f"[{index:02d}/{len(commands):02d}] {script}", flush=True)
    completed = subprocess.run(command, cwd=root, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"FAILED: {script} exited {completed.returncode}")

print(f"ALL {len(commands)} OFFLINE VALIDATORS PASSED")
