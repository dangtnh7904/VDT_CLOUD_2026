"""Validate a generic exact-hop template or locked execution manifest."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PIN_IDS = [f"PIN-{index:02d}" for index in range(1, 13)]


def need_text(value: object, label: str, locked: bool) -> str:
    if not isinstance(value, str) or (locked and not value.strip()):
        raise AssertionError(f"{label} must be {'non-empty ' if locked else ''}text")
    return value


def need_sha(value: object, label: str, locked: bool) -> str:
    text = need_text(value, label, locked)
    if text and not SHA256_RE.fullmatch(text):
        raise AssertionError(f"{label} must be a lowercase SHA-256")
    return text


parser = argparse.ArgumentParser()
parser.add_argument("--manifest", type=Path, required=True)
parser.add_argument("--comparison", required=True)
parser.add_argument("--base-ref", required=True)
parser.add_argument("--base-sha", required=True)
parser.add_argument("--target-ref", required=True)
parser.add_argument("--target-sha", required=True)
parser.add_argument("--mode", choices=("template", "locked"), default="template")
args = parser.parse_args()
locked = args.mode == "locked"
data = json.loads(args.manifest.read_text(encoding="utf-8-sig"))

assert data.get("schema_version") == 1
assert data.get("comparison") == args.comparison
assert data.get("validation_label") == ("EXACT_HOP_VALID" if locked else "NOT_EXACT_HOP_VALID")
for side, expected_ref, expected_sha in (
    ("base", args.base_ref, args.base_sha),
    ("target", args.target_ref, args.target_sha),
):
    section = data.get(side)
    assert isinstance(section, dict), side
    assert section.get("ref") == expected_ref and section.get("source_sha") == expected_sha
    packages = section.get("package_identities")
    assert isinstance(packages, list)
    if locked:
        assert packages and all(isinstance(value, str) and value.strip() for value in packages)
    need_text(section.get("image_reference"), f"{side}.image_reference", locked)
    digest = need_text(section.get("image_digest"), f"{side}.image_digest", locked)
    if digest:
        assert DIGEST_RE.fullmatch(digest), (side, digest)
    need_sha(section.get("image_inspect_sha256"), f"{side}.image_inspect_sha256", locked)
    need_sha(section.get("cephadm_sha256"), f"{side}.cephadm_sha256", locked)
    need_text(section.get("cephadm_provenance"), f"{side}.cephadm_provenance", locked)

job = data.get("job")
assert isinstance(job, dict)
need_text(job.get("run_id"), "job.run_id", locked)
work_items = job.get("work_items")
assert isinstance(work_items, list)
if locked:
    assert work_items and all(isinstance(value, str) and value.strip() for value in work_items)
need_sha(job.get("expanded_job_config_sha256"), "job.expanded_job_config_sha256", locked)
need_text(job.get("workload_seed"), "job.workload_seed", locked)
need_text(job.get("topology_evidence"), "job.topology_evidence", locked)
for field in ("started_utc", "ended_utc"):
    value = need_text(job.get(field), f"job.{field}", locked)
    if value:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
if locked:
    assert datetime.fromisoformat(job["ended_utc"].replace("Z", "+00:00")) >= datetime.fromisoformat(job["started_utc"].replace("Z", "+00:00"))

delivery = data.get("delivery")
assert isinstance(delivery, dict)
need_text(delivery.get("registry"), "delivery.registry", locked)
need_text(delivery.get("mirror"), "delivery.mirror", locked)
assert isinstance(delivery.get("pull_by_digest_verified"), bool)
if locked:
    assert delivery["pull_by_digest_verified"]
evidence = delivery.get("evidence")
assert isinstance(evidence, list)
if locked:
    assert evidence and all(isinstance(value, str) and value.strip() for value in evidence)

lanes = data.get("distro_lanes")
assert isinstance(lanes, list)
if locked:
    assert lanes
for lane in lanes:
    assert isinstance(lane, dict)
    for field in ("id", "os_release", "kernel", "architecture", "container_runtime"):
        need_text(lane.get(field), f"distro_lanes.{field}", locked)

harness = data.get("harness")
assert isinstance(harness, dict)
assert harness.get("ceph_suite_sha") == args.target_sha
teuthology_sha = need_text(harness.get("teuthology_sha"), "harness.teuthology_sha", locked)
if teuthology_sha:
    assert SHA1_RE.fullmatch(teuthology_sha)
need_text(harness.get("expanded_yaml_evidence"), "harness.expanded_yaml_evidence", locked)
patches = harness.get("local_patches")
assert isinstance(patches, list)
for patch in patches:
    assert isinstance(patch, dict)
    need_text(patch.get("description"), "local_patch.description", True)
    need_sha(patch.get("sha256"), "local_patch.sha256", True)

oracle = data.get("completion_oracle")
assert isinstance(oracle, dict)
assert isinstance(oracle.get("passed"), bool)
if locked:
    assert oracle["passed"]
for field in ("versions_sha256", "orchestrator_state_sha256"):
    need_sha(oracle.get(field), f"completion_oracle.{field}", locked)
inspect_hashes = oracle.get("image_inspect_sha256s")
assert isinstance(inspect_hashes, list)
if locked:
    assert inspect_hashes and all(isinstance(value, str) and SHA256_RE.fullmatch(value) for value in inspect_hashes)
expected_counts = oracle.get("expected_daemon_counts")
observed_counts = oracle.get("observed_daemon_counts")
assert isinstance(expected_counts, dict) and isinstance(observed_counts, dict)
if locked:
    assert expected_counts and expected_counts == observed_counts
need_text(oracle.get("role_inventory_evidence"), "completion_oracle.role_inventory_evidence", locked)

for section_name in ("client_matrix", "release_floor_guard"):
    section = data.get(section_name)
    assert isinstance(section, dict)
    assert section.get("disposition") in {"PENDING_INPUT", "LOCKED", "NOT_APPLICABLE"}
    evidence = section.get("evidence")
    assert isinstance(evidence, list)
    if locked:
        assert section["disposition"] != "PENDING_INPUT"
        if section["disposition"] == "NOT_APPLICABLE":
            need_text(section.get("reason"), f"{section_name}.reason", True)
            assert evidence
client = data["client_matrix"]
if locked and client["disposition"] == "LOCKED":
    assert client.get("old_client_new_daemon") and client.get("new_client_old_daemon") and client.get("evidence")
floor = data["release_floor_guard"]
assert isinstance(floor.get("fixture_quarantined"), bool)
if locked:
    assert floor["fixture_quarantined"]
    if floor["disposition"] == "LOCKED":
        need_text(floor.get("approval_evidence"), "release_floor_guard.approval_evidence", True)

archive = data.get("archive")
assert isinstance(archive, dict)
need_text(archive.get("uri"), "archive.uri", locked)
need_sha(archive.get("manifest_sha256"), "archive.manifest_sha256", locked)
need_text(archive.get("owner"), "archive.owner", locked)
need_text(archive.get("failure_triage"), "archive.failure_triage", locked)

pins = data.get("pins")
assert isinstance(pins, list)
assert [pin.get("id") for pin in pins if isinstance(pin, dict)] == PIN_IDS
pin_status_counts: Counter[str] = Counter()
for pin in pins:
    assert isinstance(pin, dict)
    status = pin.get("status")
    assert status in {"PENDING_INPUT", "LOCKED", "NOT_APPLICABLE"}
    pin_status_counts[status] += 1
    evidence = pin.get("evidence")
    assert isinstance(evidence, list)
    assert isinstance(pin.get("reason"), str)
    if locked:
        if pin["id"] in {"PIN-10", "PIN-11"}:
            assert status in {"LOCKED", "NOT_APPLICABLE"}
        else:
            assert status == "LOCKED"
        assert evidence
        if status == "NOT_APPLICABLE":
            need_text(pin.get("reason"), f"{pin['id']}.reason", True)
if locked:
    by_id = {pin["id"]: pin for pin in pins}
    assert by_id["PIN-10"]["status"] == client["disposition"]
    assert by_id["PIN-11"]["status"] == floor["disposition"]

print(json.dumps({
    "valid": True,
    "mode": args.mode,
    "manifest": str(args.manifest.resolve()),
    "validation_label": data.get("validation_label"),
    "work_items": work_items,
    "distro_lanes": len(lanes),
    "pin_status_counts": dict(sorted(pin_status_counts.items())),
}, indent=2))
