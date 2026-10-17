"""Validate integrity and command coverage of a capture_as_is.ps1 bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--bundle", type=Path, required=True)
parser.add_argument("--require-success", action="store_true")
args = parser.parse_args()

bundle = args.bundle.resolve()
required_top = {
    "run.json",
    "commands.json",
    "results.json",
    "MANIFEST.sha256",
}
missing_top = sorted(name for name in required_top if not (bundle / name).is_file())
if missing_top:
    raise SystemExit(f"Missing bundle files: {missing_top}")

run = json.loads((bundle / "run.json").read_text(encoding="utf-8-sig"))
commands = json.loads((bundle / "commands.json").read_text(encoding="utf-8-sig"))
results = json.loads((bundle / "results.json").read_text(encoding="utf-8-sig"))

if run.get("schema_version") != 1:
    raise SystemExit(f"Unsupported schema_version: {run.get('schema_version')!r}")
if run.get("comparison") != "quincy-17.2.7-to-reef-18.2.7":
    raise SystemExit(f"Unexpected comparison identity: {run.get('comparison')!r}")

command_ids = [item.get("id") for item in commands]
result_ids = [item.get("id") for item in results]
if not command_ids or len(command_ids) != len(set(command_ids)):
    raise SystemExit("commands.json has no commands or contains duplicate IDs")
if result_ids != command_ids:
    raise SystemExit("results.json IDs/order do not match commands.json")

manifest_entries: dict[str, str] = {}
manifest_re = re.compile(r"^([0-9a-f]{64})  (.+)$")
for line in (bundle / "MANIFEST.sha256").read_text(encoding="utf-8-sig").splitlines():
    match = manifest_re.fullmatch(line)
    if not match:
        raise SystemExit(f"Invalid manifest line: {line!r}")
    digest, relative = match.groups()
    if relative in manifest_entries:
        raise SystemExit(f"Duplicate manifest path: {relative}")
    manifest_entries[relative] = digest

actual_files = {
    path.relative_to(bundle).as_posix()
    for path in bundle.rglob("*")
    if path.is_file() and path.name != "MANIFEST.sha256"
}
if actual_files != set(manifest_entries):
    raise SystemExit(
        "Manifest/file mismatch: "
        f"missing={sorted(actual_files - set(manifest_entries))}, "
        f"extra={sorted(set(manifest_entries) - actual_files)}"
    )

for relative, expected in manifest_entries.items():
    target = (bundle / relative).resolve()
    try:
        target.relative_to(bundle)
    except ValueError as exc:
        raise SystemExit(f"Manifest path escapes bundle: {relative}") from exc
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"SHA-256 mismatch for {relative}: {actual} != {expected}")

covered_as_ids: set[str] = set()
failures: list[str] = []
for command, result in zip(commands, results, strict=True):
    for as_id in command.get("as_ids", []):
        if not re.fullmatch(r"AS-\d{3}", as_id):
            raise SystemExit(f"Invalid As-Is ID in {command['id']}: {as_id!r}")
        covered_as_ids.add(as_id)
    for key in ("stdout_file", "stderr_file"):
        relative = result.get(key)
        if not relative or relative not in manifest_entries:
            raise SystemExit(f"Missing {key} for {command['id']}: {relative!r}")
    meta_path = f"commands/{command['id']}.meta.json"
    if meta_path not in manifest_entries:
        raise SystemExit(f"Missing metadata for {command['id']}")
    if not isinstance(result.get("exit_code"), int):
        raise SystemExit(f"Invalid exit code for {command['id']}")
    if result["exit_code"] != 0:
        failures.append(command["id"])

if args.require_success and failures:
    raise SystemExit(f"Capture has failed commands: {failures}")

summary = {
    "valid": True,
    "bundle": str(bundle),
    "run_id": run.get("run_id"),
    "commands": len(commands),
    "failed_commands": failures,
    "as_is_groups_touched": sorted(covered_as_ids),
    "configuration_included": bool(run.get("include_configuration")),
    "service_specs_included": bool(run.get("include_service_specs")),
    "note": "Bundle integrity does not by itself change any AS-* status to CAPTURED.",
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
