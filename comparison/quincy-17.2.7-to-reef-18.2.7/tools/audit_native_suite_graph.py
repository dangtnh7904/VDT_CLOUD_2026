"""Parse exact-hop native YAML and validate every symlink at the target tag."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
from collections import Counter
from pathlib import Path

import yaml


root = Path(__file__).resolve().parents[1]
default_repo = root.parents[1] / "ceph17.2.7"
scopes = [
    "qa/suites/upgrade/quincy-x",
    "qa/suites/upgrade/telemetry-upgrade/quincy-x",
]

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=default_repo)
parser.add_argument("--target", default="v18.2.7")
parser.add_argument("--strict", action="store_true")
args = parser.parse_args()
repo = args.repo.resolve()


def git(*git_args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", "-C", str(repo), *git_args],
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise SystemExit(
            f"git {' '.join(git_args)} failed: "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    return result


target_sha = git("rev-parse", f"{args.target}^{{commit}}").stdout.decode().strip()
if target_sha != "6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad":
    raise SystemExit(f"Unexpected target SHA: {target_sha}")

tree_output = git("ls-tree", "-rz", args.target, "--", *scopes).stdout
entries: list[dict[str, str]] = []
for raw in tree_output.split(b"\0"):
    if not raw:
        continue
    metadata, path_bytes = raw.split(b"\t", 1)
    mode, object_type, object_sha = metadata.decode().split()
    entries.append(
        {
            "mode": mode,
            "type": object_type,
            "sha": object_sha,
            "path": path_bytes.decode("utf-8", errors="strict"),
        }
    )


class TaggedLoader(yaml.SafeLoader):
    """Safe YAML syntax loader that tolerates teuthology-local tags."""


def construct_unknown(loader: TaggedLoader, _suffix: str, node: yaml.Node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


TaggedLoader.add_multi_constructor("!", construct_unknown)

yaml_files: list[str] = []
yaml_errors: dict[str, str] = {}
symlinks: list[dict[str, str]] = []
broken_symlinks: list[dict[str, str]] = []
all_text: list[str] = []


def tree_mode(path: str) -> str | None:
    output = git("ls-tree", args.target, "--", path).stdout.decode("utf-8", errors="strict")
    lines = [line for line in output.splitlines() if line]
    for line in lines:
        metadata, listed_path = line.split("\t", 1)
        if listed_path == path:
            return metadata.split()[0]
    return None


def resolve_symlink_path(path: str) -> tuple[str, list[dict[str, str]], bool]:
    """Resolve nested symlinks in a Git tree, including symlinked directories."""

    current = posixpath.normpath(path)
    chain: list[dict[str, str]] = []
    for _ in range(32):
        parts = [part for part in current.split("/") if part not in ("", ".")]
        replaced = False
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            if tree_mode(prefix) != "120000":
                continue
            target = git("show", f"{args.target}:{prefix}").stdout.decode(
                "utf-8", errors="strict"
            ).strip()
            suffix = parts[index:]
            new_path = posixpath.normpath(
                posixpath.join(posixpath.dirname(prefix), target, *suffix)
            )
            chain.append({"link": prefix, "target": target, "result": new_path})
            current = new_path
            replaced = True
            break
        if replaced:
            continue
        exists = git("cat-file", "-e", f"{args.target}:{current}", check=False).returncode == 0
        return current, chain, exists
    return current, chain, False

for entry in entries:
    content = git("show", f"{args.target}:{entry['path']}").stdout.decode(
        "utf-8", errors="strict"
    )
    all_text.append(content)
    if entry["mode"] == "120000":
        target = content.strip()
        first_hop = posixpath.normpath(posixpath.join(posixpath.dirname(entry["path"]), target))
        resolved, chain, exists = resolve_symlink_path(first_hop)
        record = {
            "path": entry["path"],
            "target": target,
            "resolved": resolved,
            "chain": chain,
        }
        symlinks.append(record)
        if not exists:
            broken_symlinks.append(record)
        continue
    if not entry["path"].endswith((".yaml", ".yml")):
        continue
    yaml_files.append(entry["path"])
    try:
        yaml.load(content, Loader=TaggedLoader)
    except yaml.YAMLError as exc:
        yaml_errors[entry["path"]] = str(exc)

joined = "\n".join(all_text)
selector_counts = {
    "branch_quincy": len(re.findall(r"(?m)^\s*branch:\s*quincy\s*$", joined)),
    "cephadm_branch_quincy": len(re.findall(r"cephadm_branch:\s*quincy", joined)),
    "floating_base_image": len(
        re.findall(r"(?m)^\s*image:\s*.*(?::quincy|:latest-quincy)\s*$", joined)
    ),
    "target_sha_image": joined.count("ceph:$sha1"),
    "grep_sha1": joined.count("grep $sha1"),
}
boundary_counts = {
    "require_osd_release": joined.count("require-osd-release"),
    "set_require_min_compat_client": joined.count("set-require-min-compat-client"),
    "cephadm_upgrade": joined.count("ceph orch upgrade"),
    "cephadm_pause": joined.count("ceph orch upgrade pause"),
    "cephadm_resume": joined.count("ceph orch upgrade resume"),
    "thrasher_mentions": len(re.findall(r"(?i)thrash", joined)),
    "zap_mentions": len(re.findall(r"(?i)\bzap\b", joined)),
    "repair_mentions": len(re.findall(r"(?i)\brepair\b", joined)),
}

summary = {
    "target": args.target,
    "target_sha": target_sha,
    "scopes": scopes,
    "entries": len(entries),
    "mode_counts": dict(sorted(Counter(entry["mode"] for entry in entries).items())),
    "yaml_files": len(yaml_files),
    "yaml_parse_errors": yaml_errors,
    "symlinks": len(symlinks),
    "broken_symlinks": broken_symlinks,
    "selector_counts": selector_counts,
    "boundary_counts": boundary_counts,
}
print(json.dumps(summary, ensure_ascii=False, indent=2))

if args.strict and (yaml_errors or broken_symlinks):
    raise SystemExit(1)
