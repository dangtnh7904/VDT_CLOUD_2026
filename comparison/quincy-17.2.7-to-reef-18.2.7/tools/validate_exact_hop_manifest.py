"""Validate the exact-hop pin manifest template or a locked run manifest."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_REF = "v17.2.7"
BASE_SHA = "b12291d110049b2f35e32e0de30d70e9a4c060d2"
TARGET_REF = "v18.2.7"
TARGET_SHA = "6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad"
COMPARISON = "quincy-17.2.7-to-reef-18.2.7"
PIN_IDS = [f"PIN-{index:02d}" for index in range(1, 13)]
ALWAYS_LOCKED = {f"PIN-{index:02d}" for index in range(1, 10)} | {"PIN-12"}
CONDITIONAL = {"PIN-10", "PIN-11"}
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PACK_RE = re.compile(r"^TP-(?:0[1-9]|1[0-9])$")
PIN_STATUS = {"PENDING_INPUT", "LOCKED", "NOT_APPLICABLE"}


def fail(message: str) -> None:
    raise SystemExit(message)


def need_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def need_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        fail(f"{label} must be an array")
    return value


def need_text(value: Any, label: str, *, locked: bool) -> str:
    if not isinstance(value, str):
        fail(f"{label} must be a string")
    if locked and not value.strip():
        fail(f"{label} must be non-empty in locked mode")
    return value


def need_sha256(value: Any, label: str, *, locked: bool) -> str:
    text = need_text(value, label, locked=locked)
    if text and not SHA256_RE.fullmatch(text):
        fail(f"{label} must be a lowercase SHA-256")
    return text


def need_iso8601(value: Any, label: str, *, locked: bool) -> str:
    text = need_text(value, label, locked=locked)
    if text:
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            fail(f"{label} is not ISO-8601: {text!r}")
    return text


def need_evidence_list(value: Any, label: str, *, locked: bool) -> list[str]:
    items = need_list(value, label)
    if any(not isinstance(item, str) or not item.strip() for item in items):
        fail(f"{label} must contain non-empty string references")
    if locked and not items:
        fail(f"{label} must not be empty in locked mode")
    return items


parser = argparse.ArgumentParser()
parser.add_argument("--manifest", type=Path, required=True)
parser.add_argument("--mode", choices=("template", "locked"), default="template")
args = parser.parse_args()
locked = args.mode == "locked"

manifest_path = args.manifest.resolve()
try:
    data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"Cannot read manifest {manifest_path}: {exc}")

root = need_mapping(data, "manifest")
if root.get("schema_version") != 1:
    fail(f"schema_version must be 1, got {root.get('schema_version')!r}")
if root.get("comparison") != COMPARISON:
    fail(f"comparison must be {COMPARISON!r}")
expected_label = "EXACT_HOP_VALID" if locked else "NOT_EXACT_HOP_VALID"
if root.get("validation_label") != expected_label:
    fail(f"validation_label must be {expected_label!r} in {args.mode} mode")

base = need_mapping(root.get("base"), "base")
target = need_mapping(root.get("target"), "target")
for block, name, expected_ref, expected_sha in (
    (base, "base", BASE_REF, BASE_SHA),
    (target, "target", TARGET_REF, TARGET_SHA),
):
    if block.get("ref") != expected_ref or block.get("source_sha") != expected_sha:
        fail(f"{name} ref/SHA does not match the audited endpoint")
    packages = need_list(block.get("package_nevra_or_versions"), f"{name}.package_nevra_or_versions")
    if locked and (not packages or any(not isinstance(item, str) or not item.strip() for item in packages)):
        fail(f"{name}.package_nevra_or_versions must contain pinned package identities")
    need_text(block.get("image_reference"), f"{name}.image_reference", locked=locked)
    image_digest = need_text(block.get("image_digest"), f"{name}.image_digest", locked=locked)
    if image_digest and not DIGEST_RE.fullmatch(image_digest):
        fail(f"{name}.image_digest must be sha256:<64 lowercase hex>")
    need_sha256(block.get("image_inspect_sha256"), f"{name}.image_inspect_sha256", locked=locked)
    need_sha256(block.get("cephadm_sha256"), f"{name}.cephadm_sha256", locked=locked)
    need_text(block.get("cephadm_provenance"), f"{name}.cephadm_provenance", locked=locked)

job = need_mapping(root.get("job"), "job")
need_text(job.get("run_id"), "job.run_id", locked=locked)
packs = need_list(job.get("packs"), "job.packs")
if any(not isinstance(item, str) or not PACK_RE.fullmatch(item) for item in packs):
    fail("job.packs must contain unique TP-01..TP-19 IDs")
if len(packs) != len(set(packs)):
    fail("job.packs contains duplicates")
if locked and not packs:
    fail("job.packs must not be empty in locked mode")
need_sha256(job.get("expanded_job_config_sha256"), "job.expanded_job_config_sha256", locked=locked)
need_text(job.get("workload_seed"), "job.workload_seed", locked=locked)
started = need_iso8601(job.get("started_utc"), "job.started_utc", locked=locked)
ended = need_iso8601(job.get("ended_utc"), "job.ended_utc", locked=locked)
if locked and started and ended:
    start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    if end_dt < start_dt:
        fail("job.ended_utc precedes job.started_utc")
need_text(job.get("topology_evidence"), "job.topology_evidence", locked=locked)

delivery = need_mapping(root.get("delivery"), "delivery")
need_text(delivery.get("registry"), "delivery.registry", locked=locked)
need_text(delivery.get("mirror"), "delivery.mirror", locked=locked)
if not isinstance(delivery.get("pull_by_digest_verified"), bool):
    fail("delivery.pull_by_digest_verified must be boolean")
if locked and not delivery["pull_by_digest_verified"]:
    fail("delivery.pull_by_digest_verified must be true in locked mode")
need_text(delivery.get("pull_test_evidence"), "delivery.pull_test_evidence", locked=locked)
repo_digest = need_mapping(delivery.get("use_repo_digest"), "delivery.use_repo_digest")
for lane in ("parallel", "stress_split", "telemetry"):
    if repo_digest.get(lane) not in (True, False, None):
        fail(f"delivery.use_repo_digest.{lane} must be true, false, or null")
    if locked and repo_digest.get(lane) is None:
        fail(f"delivery.use_repo_digest.{lane} must be dispositioned in locked mode")
need_evidence_list(
    delivery.get("effective_setting_evidence"),
    "delivery.effective_setting_evidence",
    locked=locked,
)

lanes = need_list(root.get("distro_lanes"), "distro_lanes")
if locked and not lanes:
    fail("distro_lanes must contain at least one host cohort")
lane_ids: set[str] = set()
for index, lane_value in enumerate(lanes):
    lane = need_mapping(lane_value, f"distro_lanes[{index}]")
    lane_id = need_text(lane.get("id"), f"distro_lanes[{index}].id", locked=locked)
    if lane_id in lane_ids:
        fail(f"duplicate distro lane id: {lane_id}")
    lane_ids.add(lane_id)
    for field in ("os_release", "kernel", "architecture", "container_runtime", "storage_driver", "network_driver"):
        need_text(lane.get(field), f"distro_lanes[{index}].{field}", locked=locked)
    digest = need_text(lane.get("host_image_digest"), f"distro_lanes[{index}].host_image_digest", locked=locked)
    if digest and not DIGEST_RE.fullmatch(digest):
        fail(f"distro_lanes[{index}].host_image_digest must be an immutable digest")

harness = need_mapping(root.get("harness"), "harness")
if harness.get("ceph_suite_sha") != TARGET_SHA:
    fail("harness.ceph_suite_sha must equal the audited target SHA")
teuthology_sha = need_text(harness.get("teuthology_sha"), "harness.teuthology_sha", locked=locked)
if teuthology_sha and not SHA1_RE.fullmatch(teuthology_sha):
    fail("harness.teuthology_sha must be a lowercase 40-character SHA")
plugin_disposition = harness.get("task_plugin_disposition")
if plugin_disposition not in {"PENDING_INPUT", "PINNED", "NONE"}:
    fail("harness.task_plugin_disposition must be PENDING_INPUT, PINNED, or NONE")
plugins = need_list(harness.get("task_plugins"), "harness.task_plugins")
if locked and plugin_disposition == "PENDING_INPUT":
    fail("harness.task_plugin_disposition must be PINNED or NONE in locked mode")
if plugin_disposition == "PINNED" and not plugins:
    fail("harness.task_plugins must not be empty when disposition is PINNED")
for index, plugin_value in enumerate(plugins):
    plugin = need_mapping(plugin_value, f"harness.task_plugins[{index}]")
    need_text(plugin.get("name"), f"harness.task_plugins[{index}].name", locked=True)
    sha = need_text(plugin.get("sha"), f"harness.task_plugins[{index}].sha", locked=True)
    if not SHA1_RE.fullmatch(sha):
        fail(f"harness.task_plugins[{index}].sha must be a 40-character SHA")
local_patches = need_list(harness.get("local_patches"), "harness.local_patches")
for index, patch_value in enumerate(local_patches):
    patch = need_mapping(patch_value, f"harness.local_patches[{index}]")
    need_text(patch.get("description"), f"harness.local_patches[{index}].description", locked=True)
    need_sha256(patch.get("sha256"), f"harness.local_patches[{index}].sha256", locked=True)
need_text(harness.get("expanded_yaml_evidence"), "harness.expanded_yaml_evidence", locked=locked)

oracle = need_mapping(root.get("completion_oracle"), "completion_oracle")
if not isinstance(oracle.get("passed"), bool):
    fail("completion_oracle.passed must be boolean")
if locked and not oracle["passed"]:
    fail("completion_oracle.passed must be true in locked mode")
need_sha256(oracle.get("ceph_versions_sha256"), "completion_oracle.ceph_versions_sha256", locked=locked)
need_sha256(oracle.get("orch_ps_sha256"), "completion_oracle.orch_ps_sha256", locked=locked)
inspect_hashes = need_list(oracle.get("image_inspect_sha256s"), "completion_oracle.image_inspect_sha256s")
if locked and (not inspect_hashes or any(not isinstance(item, str) or not SHA256_RE.fullmatch(item) for item in inspect_hashes)):
    fail("completion_oracle.image_inspect_sha256s must contain SHA-256 values")
expected_counts = need_mapping(oracle.get("expected_daemon_counts"), "completion_oracle.expected_daemon_counts")
observed_counts = need_mapping(oracle.get("observed_daemon_counts"), "completion_oracle.observed_daemon_counts")
if locked and (not expected_counts or expected_counts != observed_counts):
    fail("completion_oracle expected and observed daemon counts must be non-empty and equal")
need_text(oracle.get("role_inventory_evidence"), "completion_oracle.role_inventory_evidence", locked=locked)

for section_name in ("client_matrix", "release_floor_guard"):
    section = need_mapping(root.get(section_name), section_name)
    disposition = section.get("disposition")
    if disposition not in {"PENDING_INPUT", "LOCKED", "NOT_APPLICABLE"}:
        fail(f"{section_name}.disposition has invalid value {disposition!r}")
    evidence = need_evidence_list(section.get("evidence"), f"{section_name}.evidence", locked=False)
    reason = need_text(section.get("reason"), f"{section_name}.reason", locked=False)
    if locked and disposition == "PENDING_INPUT":
        fail(f"{section_name}.disposition may not be PENDING_INPUT in locked mode")
    if locked and disposition == "NOT_APPLICABLE" and (not reason.strip() or not evidence):
        fail(f"{section_name} needs reason and evidence when NOT_APPLICABLE")

client = need_mapping(root.get("client_matrix"), "client_matrix")
old_new = need_list(client.get("old_client_new_daemon"), "client_matrix.old_client_new_daemon")
new_old = need_list(client.get("new_client_old_daemon"), "client_matrix.new_client_old_daemon")
if locked and client.get("disposition") == "LOCKED" and (not old_new or not new_old or not client.get("evidence")):
    fail("LOCKED client_matrix needs both directions and evidence")

floor = need_mapping(root.get("release_floor_guard"), "release_floor_guard")
if not isinstance(floor.get("fixture_quarantined"), bool):
    fail("release_floor_guard.fixture_quarantined must be boolean")
if locked and not floor["fixture_quarantined"]:
    fail("release_floor_guard.fixture_quarantined must be true in locked mode")
if locked and floor.get("disposition") == "LOCKED":
    need_text(floor.get("approval_evidence"), "release_floor_guard.approval_evidence", locked=True)
    need_text(floor.get("old_client_negative_result"), "release_floor_guard.old_client_negative_result", locked=True)

archive = need_mapping(root.get("archive"), "archive")
need_text(archive.get("uri"), "archive.uri", locked=locked)
need_sha256(archive.get("manifest_sha256"), "archive.manifest_sha256", locked=locked)
need_text(archive.get("owner"), "archive.owner", locked=locked)
need_text(archive.get("failure_triage"), "archive.failure_triage", locked=locked)
need_text(archive.get("rerun_of"), "archive.rerun_of", locked=False)

pins = need_list(root.get("pins"), "pins")
pin_ids = [item.get("id") if isinstance(item, dict) else None for item in pins]
if pin_ids != PIN_IDS:
    fail(f"pins must contain {PIN_IDS} in order")
status_counts: dict[str, int] = {}
for pin_value in pins:
    pin = need_mapping(pin_value, "pin")
    pin_id = pin["id"]
    status = pin.get("status")
    if status not in PIN_STATUS:
        fail(f"{pin_id}.status has invalid value {status!r}")
    status_counts[status] = status_counts.get(status, 0) + 1
    reason = need_text(pin.get("reason"), f"{pin_id}.reason", locked=False)
    evidence = need_evidence_list(pin.get("evidence"), f"{pin_id}.evidence", locked=False)
    if locked and pin_id in ALWAYS_LOCKED and status != "LOCKED":
        fail(f"{pin_id} must be LOCKED")
    if locked and pin_id in CONDITIONAL and status not in {"LOCKED", "NOT_APPLICABLE"}:
        fail(f"{pin_id} must be LOCKED or NOT_APPLICABLE")
    if locked and not evidence:
        fail(f"{pin_id}.evidence must not be empty")
    if locked and status == "NOT_APPLICABLE" and not reason.strip():
        fail(f"{pin_id}.reason must explain NOT_APPLICABLE")

pin_by_id = {pin["id"]: pin for pin in pins}
if locked and pin_by_id["PIN-10"]["status"] != client.get("disposition"):
    fail("PIN-10 status must match client_matrix.disposition")
if locked and pin_by_id["PIN-11"]["status"] != floor.get("disposition"):
    fail("PIN-11 status must match release_floor_guard.disposition")

summary = {
    "valid": True,
    "mode": args.mode,
    "manifest": str(manifest_path),
    "validation_label": root["validation_label"],
    "packs": packs,
    "distro_lanes": len(lanes),
    "pin_status_counts": dict(sorted(status_counts.items())),
    "client_matrix_disposition": client.get("disposition"),
    "release_floor_guard_disposition": floor.get("disposition"),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
