"""Validate runtime test-pack coverage and source assets at the target tag."""

import argparse
import re
import subprocess
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
default_repo = root.parents[1] / "ceph17.2.7"
parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=default_repo)
parser.add_argument("--target", default="v18.2.7")
args = parser.parse_args()

path = root / "RUNTIME-TEST-SELECTION.md"
matrix_path = root / "LAB-RUNTIME-GATES.md"
allowed_modes = {"NATIVE_HOP", "REUSABLE", "HYBRID", "CUSTOM"}
allowed_status = {"NOT_RUN", "READY", "RUNNING", "PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}

matrix_text = matrix_path.read_text(encoding="utf-8-sig")
gate_ids = set(re.findall(r"^\| (LAB-\d{3}) \|", matrix_text, re.MULTILINE))

text = path.read_text(encoding="utf-8-sig")
rows = [line for line in text.splitlines() if line.startswith("| TP-")]
assert len(rows) == 19, len(rows)

pack_ids = []
referenced_gates = set()
source_paths = set()
modes = []
statuses = []
for line in rows:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    assert len(cells) == 7, (len(cells), line)
    pack_id, tier, mode, assets, purpose, gates, status = cells
    assert re.fullmatch(r"TP-\d{2}", pack_id), pack_id
    assert tier in {"P0", "P1"}, (pack_id, tier)
    assert mode in allowed_modes, (pack_id, mode)
    assert len(purpose) >= 30, pack_id
    refs = set(re.findall(r"LAB-\d{3}", gates))
    assert refs, pack_id
    missing_gates = refs - gate_ids
    assert not missing_gates, (pack_id, missing_gates)
    paths = set(re.findall(r"`((?:qa|src)/[^`]+)`", assets))
    if mode != "CUSTOM":
        assert paths, pack_id
    assert status in allowed_status, (pack_id, status)
    pack_ids.append(pack_id)
    referenced_gates.update(refs)
    source_paths.update(paths)
    modes.append(mode)
    statuses.append(status)

assert pack_ids == [f"TP-{number:02d}" for number in range(1, 20)]
assert referenced_gates == gate_ids, sorted(gate_ids - referenced_gates)

repo = args.repo.resolve()
assert (repo / ".git").exists(), repo
target_sha = subprocess.run(
    ["git", "-C", str(repo), "rev-parse", f"{args.target}^{{commit}}"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
assert target_sha == "6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad", target_sha

missing_paths = []
for source_path in sorted(source_paths):
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{args.target}:{source_path}"],
        capture_output=True,
    )
    if result.returncode:
        missing_paths.append(source_path)
assert not missing_paths, missing_paths

print(
    f"Validated {len(rows)} test packs covering {len(referenced_gates)} runtime gates; "
    f"source_assets={len(source_paths)} at {args.target} ({target_sha}); "
    f"modes={dict(sorted(Counter(modes).items()))}; "
    f"status_counts={dict(sorted(Counter(statuses).items()))}"
)
