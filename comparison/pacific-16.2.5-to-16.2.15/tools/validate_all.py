"""Run every offline validator for the Pacific 16.2.5 to 16.2.15 suite."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
shared_tools = root.parent / "tools"
comparison_validator = (
    root.parent / "pacific-16.2.15-to-quincy-17.2.7" / "tools" / "validate_comparison.py"
)
default_repo = root.parents[1] / "ceph16.2.15" / "ceph"

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=default_repo)
args = parser.parse_args()

common = [
    "--comparison", "pacific-16.2.5-to-16.2.15",
    "--base-ref", "v16.2.5",
    "--base-sha", "0883bdea7337b95e4b611c768c0279868462204a",
    "--target-ref", "v16.2.15",
    "--target-sha", "618f440892089921c3e944a991122ddc44e60516",
]
runtime = [
    "--source", str(root / "UPGRADE-CHECKLIST(1).md"),
    "--id-pattern", r"G\d{2}",
    "--id-pattern", r"T\d{2}[A-D]?",
]

commands = [
    [
        sys.executable, str(comparison_validator),
        "--root", str(root),
        "--mode", "complete",
        "--plan", str(root / "PLAN-pacific-16.2.5-to-16.2.15.md"),
        "--require-impact", "binary",
    ],
    [sys.executable, str(root / "tools" / "migrate_binary_impact.py"), "--check-only"],
    [
        sys.executable, str(shared_tools / "audit_native_suite_graph.py"),
        "--repo", str(args.repo.resolve()),
        "--target", "v16.2.15",
        "--expected-target-sha", "618f440892089921c3e944a991122ddc44e60516",
        "--scope", "qa/suites/upgrade/pacific-p2p",
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
        "--runtime-source", str(root / "UPGRADE-CHECKLIST(1).md"),
        "--gate-pattern", r"G\d{2}",
        "--gate-pattern", r"T\d{2}[A-D]?",
        "--repo", str(args.repo.resolve()),
        "--target", "v16.2.15",
        "--expected-target-sha", "618f440892089921c3e944a991122ddc44e60516",
        "--expected-count", "16",
    ],
    [
        sys.executable, str(shared_tools / "validate_as_is_register.py"),
        "--root", str(root),
        "--runtime-source", str(root / "UPGRADE-CHECKLIST(1).md"),
        "--gate-pattern", r"G\d{2}",
        "--gate-pattern", r"T\d{2}[A-D]?",
        "--expected-count", "20",
    ],
    [
        sys.executable, str(shared_tools / "validate_action_register.py"),
        "--root", str(root),
        "--runtime-source", str(root / "UPGRADE-CHECKLIST(1).md"),
        "--gate-pattern", r"G\d{2}",
        "--gate-pattern", r"T\d{2}[A-D]?",
        "--action-prefix", "H1",
        "--expected-count", "20",
    ],
    [
        sys.executable, str(shared_tools / "validate_go_no_go_register.py"),
        "--root", str(root),
    ],
    [
        sys.executable, str(shared_tools / "audit_finding_quality.py"),
        "--root", str(root),
        "--expected-count", "127",
        "--strict",
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
