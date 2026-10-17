"""Run every offline validator for the Pacific 16.2.15 to Quincy 17.2.7 suite."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
tools = root / "tools"
shared_tools = root.parent / "tools"
default_repo = root.parents[1] / "ceph16.2.15" / "ceph"

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=default_repo)
args = parser.parse_args()

common = [
    "--comparison", "pacific-16.2.15-to-quincy-17.2.7",
    "--base-ref", "v16.2.15",
    "--base-sha", "618f440892089921c3e944a991122ddc44e60516",
    "--target-ref", "v17.2.7",
    "--target-sha", "b12291d110049b2f35e32e0de30d70e9a4c060d2",
]
runtime = [
    "--source", str(root / "LAB-RUNTIME-GATES.md"),
    "--id-pattern", r"LAB-\d{3}",
]

commands = [
    [
        sys.executable, str(tools / "validate_comparison.py"),
        "--root", str(root),
        "--mode", "complete",
        "--plan", str(root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"),
        "--require-impact", "binary",
    ],
    [sys.executable, str(tools / "validate_lab_runtime_gates.py")],
    [
        sys.executable, str(shared_tools / "audit_native_suite_graph.py"),
        "--repo", str(args.repo.resolve()),
        "--target", "v17.2.7",
        "--expected-target-sha", "b12291d110049b2f35e32e0de30d70e9a4c060d2",
        "--scope", "qa/suites/upgrade/pacific-x",
        "--base-series", "pacific",
        "--strict",
    ],
    [
        sys.executable, str(shared_tools / "validate_exact_hop_manifest.py"),
        "--manifest", str(root / "EXACT-HOP-PIN-MANIFEST.template.json"),
        *common,
        "--mode", "template",
    ],
    [
        sys.executable, str(shared_tools / "validate_runtime_evidence_manifest.py"),
        "--manifest", str(root / "RUNTIME-EVIDENCE-MANIFEST.template.json"),
        *runtime, *common,
        "--mode", "template",
    ],
    [
        sys.executable, str(shared_tools / "validate_runtime_test_selection.py"),
        "--root", str(root),
        "--runtime-source", str(root / "LAB-RUNTIME-GATES.md"),
        "--gate-pattern", r"LAB-\d{3}",
        "--repo", str(args.repo.resolve()),
        "--target", "v17.2.7",
        "--expected-target-sha", "b12291d110049b2f35e32e0de30d70e9a4c060d2",
        "--expected-count", "15",
    ],
    [
        sys.executable, str(shared_tools / "validate_as_is_register.py"),
        "--root", str(root),
        "--runtime-source", str(root / "LAB-RUNTIME-GATES.md"),
        "--gate-pattern", r"LAB-\d{3}",
        "--expected-count", "20",
    ],
    [
        sys.executable, str(shared_tools / "validate_action_register.py"),
        "--root", str(root),
        "--runtime-source", str(root / "LAB-RUNTIME-GATES.md"),
        "--gate-pattern", r"LAB-\d{3}",
        "--action-prefix", "H2",
        "--expected-count", "20",
    ],
    [
        sys.executable, str(shared_tools / "validate_go_no_go_register.py"),
        "--root", str(root),
    ],
    [
        sys.executable, str(shared_tools / "audit_finding_quality.py"),
        "--root", str(root),
        "--expected-count", "441",
        "--max-incomplete", "397",
        "--show", "0",
    ],
    [
        sys.executable, str(shared_tools / "test_hop_manifest_validators.py"),
        "--exact-template", str(root / "EXACT-HOP-PIN-MANIFEST.template.json"),
        "--runtime-template", str(root / "RUNTIME-EVIDENCE-MANIFEST.template.json"),
        *runtime, *common,
    ],
]

for index, command in enumerate(commands, start=1):
    script = Path(command[1]).name
    print(f"[{index:02d}/{len(commands):02d}] {script}", flush=True)
    completed = subprocess.run(command, cwd=root, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"FAILED: {script} exited {completed.returncode}")

print(f"ALL {len(commands)} OFFLINE VALIDATORS PASSED")
