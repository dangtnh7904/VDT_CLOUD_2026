"""Validate exact-hop pin register and audited floating selectors in target source."""

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

path = root / "EXACT-HOP-PINS.md"
allowed_status = {"PENDING_INPUT", "LOCKED", "BLOCKED", "NOT_APPLICABLE"}
scopes = [
    "qa/suites/upgrade/quincy-x",
    "qa/suites/upgrade/telemetry-upgrade/quincy-x",
]

text = path.read_text(encoding="utf-8-sig")
rows = [line for line in text.splitlines() if line.startswith("| PIN-")]
assert len(rows) == 12, len(rows)

pin_ids = []
statuses = []
for line in rows:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    assert len(cells) == 6, (len(cells), line)
    pin_id, selector, required, evidence, packs, status = cells
    assert re.fullmatch(r"PIN-\d{2}", pin_id), pin_id
    assert len(selector) >= 20, pin_id
    assert len(required) >= 20, pin_id
    assert len(evidence) >= 20, pin_id
    assert re.search(r"TP-\d{2}", packs), pin_id
    assert status in allowed_status, (pin_id, status)
    pin_ids.append(pin_id)
    statuses.append(status)

assert pin_ids == [f"PIN-{number:02d}" for number in range(1, 13)]

repo = args.repo.resolve()
assert (repo / ".git").exists(), repo

def git_lines(*git_args: str, allow_no_match: bool = False) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *git_args],
        capture_output=True,
        text=True,
    )
    if allow_no_match and result.returncode == 1:
        return []
    result.check_returncode()
    return result.stdout.splitlines()


target_sha = git_lines("rev-parse", f"{args.target}^{{commit}}")[0]
assert target_sha == "6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad", target_sha

def grep_count(pattern: str) -> int:
    return len(
        git_lines(
            "grep",
            "-n",
            "-E",
            pattern,
            args.target,
            "--",
            *scopes,
            allow_no_match=True,
        )
    )


selector_counts = {
    "branch_quincy": grep_count(r"^\s*branch: quincy"),
    "cephadm_branch_quincy": grep_count(r"cephadm_branch: quincy"),
    "base_image_tag": grep_count(r"image: .*(:quincy|:latest-quincy)$"),
    "target_sha_image": grep_count(r"ceph:\$sha1"),
    "grep_sha1": grep_count(r"grep \$sha1"),
}
expected_counts = {
    "branch_quincy": 16,
    "cephadm_branch_quincy": 3,
    "base_image_tag": 3,
    "target_sha_image": 3,
    "grep_sha1": 7,
}
assert selector_counts == expected_counts, selector_counts

distro_selectors = [
    "qa/suites/upgrade/quincy-x/parallel/0-random-distro$",
    "qa/suites/upgrade/quincy-x/stress-split/0-distro",
    "qa/suites/upgrade/telemetry-upgrade/quincy-x/0-random-distro$",
]
for selector in distro_selectors:
    mode_line = git_lines("ls-tree", args.target, selector)
    assert len(mode_line) == 1 and mode_line[0].startswith("120000 "), (selector, mode_line)
    target = git_lines("show", f"{args.target}:{selector}")[0]
    assert target == ".qa/distros/supported-container-hosts", (selector, target)

print(
    f"Validated {len(rows)} exact-hop pins against {args.target} ({target_sha}); "
    f"floating_selectors={selector_counts}; distro_selectors={len(distro_selectors)}; "
    f"status_counts={dict(sorted(Counter(statuses).items()))}"
)
