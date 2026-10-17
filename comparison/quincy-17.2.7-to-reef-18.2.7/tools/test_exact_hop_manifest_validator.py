"""Self-test for validate_exact_hop_manifest.py using synthetic evidence only."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


root = Path(__file__).resolve().parents[1]
validator = Path(__file__).with_name("validate_exact_hop_manifest.py")
template = root / "EXACT-HOP-PIN-MANIFEST.template.json"


def run(manifest: Path, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(validator), "--manifest", str(manifest), "--mode", mode],
        text=True,
        capture_output=True,
        check=False,
    )


template_result = run(template, "template")
assert template_result.returncode == 0, template_result.stderr or template_result.stdout
negative_result = run(template, "locked")
assert negative_result.returncode != 0, "template unexpectedly passed locked mode"

data = json.loads(template.read_text(encoding="utf-8-sig"))
data["validation_label"] = "EXACT_HOP_VALID"
for name, digit in (("base", "1"), ("target", "2")):
    block = data[name]
    block["package_nevra_or_versions"] = [f"ceph-{block['ref'][1:]}-1"]
    block["image_reference"] = f"registry.example/ceph@sha256:{digit * 64}"
    block["image_digest"] = f"sha256:{digit * 64}"
    block["image_inspect_sha256"] = ("3" if name == "base" else "4") * 64
    block["cephadm_sha256"] = ("5" if name == "base" else "6") * 64
    block["cephadm_provenance"] = f"archive/{name}-cephadm.txt"

data["job"].update(
    {
        "run_id": "synthetic-validator-test",
        "packs": ["TP-03"],
        "expanded_job_config_sha256": "7" * 64,
        "workload_seed": "seed-1",
        "started_utc": "2026-10-12T00:00:00Z",
        "ended_utc": "2026-10-12T01:00:00Z",
        "topology_evidence": "archive/topology.json",
    }
)
data["delivery"].update(
    {
        "registry": "registry.example",
        "mirror": "mirror.example",
        "pull_by_digest_verified": True,
        "pull_test_evidence": "archive/pull-test.txt",
        "use_repo_digest": {"parallel": True, "stress_split": False, "telemetry": True},
        "effective_setting_evidence": ["archive/effective-config.json"],
    }
)
data["distro_lanes"] = [
    {
        "id": "lane-1",
        "os_release": "Example 1",
        "kernel": "1.0",
        "architecture": "x86_64",
        "container_runtime": "podman 1",
        "storage_driver": "overlay",
        "network_driver": "bridge",
        "host_image_digest": f"sha256:{'8' * 64}",
    }
]
data["harness"].update(
    {
        "teuthology_sha": "9" * 40,
        "task_plugin_disposition": "NONE",
        "expanded_yaml_evidence": "archive/expanded.yaml",
    }
)
data["completion_oracle"].update(
    {
        "passed": True,
        "ceph_versions_sha256": "a" * 64,
        "orch_ps_sha256": "b" * 64,
        "image_inspect_sha256s": ["c" * 64, "d" * 64],
        "expected_daemon_counts": {"mon": 3, "osd": 3},
        "observed_daemon_counts": {"mon": 3, "osd": 3},
        "role_inventory_evidence": "archive/roles.json",
    }
)
data["client_matrix"].update(
    {
        "disposition": "NOT_APPLICABLE",
        "reason": "Synthetic job excludes client lanes.",
        "evidence": ["archive/client-disposition.txt"],
    }
)
data["release_floor_guard"].update(
    {
        "disposition": "NOT_APPLICABLE",
        "reason": "Synthetic job does not load the floor fixture.",
        "fixture_quarantined": True,
        "evidence": ["archive/floor-guard.txt"],
    }
)
data["archive"].update(
    {
        "uri": "archive://synthetic-validator-test",
        "manifest_sha256": "e" * 64,
        "owner": "validator-test",
        "failure_triage": "No failures in synthetic validator fixture.",
    }
)
for pin in data["pins"]:
    pin["status"] = "LOCKED"
    pin["evidence"] = [f"archive/{pin['id']}.txt"]
for index, section in ((9, "client_matrix"), (10, "release_floor_guard")):
    data["pins"][index]["status"] = "NOT_APPLICABLE"
    data["pins"][index]["reason"] = data[section]["reason"]

with tempfile.TemporaryDirectory(prefix="h3-exact-hop-validator-") as temp_dir:
    locked_manifest = Path(temp_dir) / "locked.json"
    locked_manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    positive_result = run(locked_manifest, "locked")
    assert positive_result.returncode == 0, positive_result.stderr or positive_result.stdout

print("exact-hop manifest validator self-test: PASS")
