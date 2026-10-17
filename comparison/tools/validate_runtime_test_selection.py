"""Validate runtime test-pack coverage and source assets at an exact target tag."""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import Counter
from pathlib import Path


ALLOWED_MODES = {"NATIVE_HOP", "REUSABLE", "HYBRID", "CUSTOM"}
ALLOWED_STATUS = {"NOT_RUN", "READY", "RUNNING", "PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-source", type=Path, required=True)
    parser.add_argument("--gate-pattern", action="append", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected-target-sha", required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    return parser.parse_args()


def collect_ids(text: str, patterns: list[str]) -> set[str]:
    ids: set[str] = set()
    for pattern in patterns:
        ids.update(re.findall(rf"(?<![A-Z0-9_-])(?:{pattern})(?![A-Z0-9_-])", text))
    return ids


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    gate_ids = collect_ids(
        args.runtime_source.resolve().read_text(encoding="utf-8-sig"),
        args.gate_pattern,
    )
    assert gate_ids, "runtime source contains no gate IDs"

    text = (root / "RUNTIME-TEST-SELECTION.md").read_text(encoding="utf-8-sig")
    rows = [line for line in text.splitlines() if line.startswith("| TP-")]
    assert len(rows) == args.expected_count, len(rows)

    pack_ids: list[str] = []
    referenced_gates: set[str] = set()
    source_paths: set[str] = set()
    modes: list[str] = []
    statuses: list[str] = []
    for line in rows:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 7, (len(cells), line)
        pack_id, tier, mode, assets, purpose, gates, status = cells
        assert re.fullmatch(r"TP-\d{2}", pack_id), pack_id
        assert tier in {"P0", "P1"}, (pack_id, tier)
        assert mode in ALLOWED_MODES, (pack_id, mode)
        assert len(purpose) >= 30, pack_id
        refs = collect_ids(gates, args.gate_pattern)
        assert refs, pack_id
        assert not refs - gate_ids, (pack_id, sorted(refs - gate_ids))
        paths = set(re.findall(r"`((?:qa|src)/[^`]+)`", assets))
        if mode != "CUSTOM":
            assert paths, pack_id
        assert status in ALLOWED_STATUS, (pack_id, status)
        pack_ids.append(pack_id)
        referenced_gates.update(refs)
        source_paths.update(paths)
        modes.append(mode)
        statuses.append(status)

    assert pack_ids == [f"TP-{number:02d}" for number in range(1, args.expected_count + 1)]
    assert referenced_gates == gate_ids, sorted(gate_ids - referenced_gates)

    repo = args.repo.resolve()
    assert (repo / ".git").exists(), repo
    target_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"{args.target}^{{commit}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert target_sha == args.expected_target_sha, target_sha

    missing_paths: list[str] = []
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


if __name__ == "__main__":
    main()
