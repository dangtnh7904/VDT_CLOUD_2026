"""Audit YAML syntax, symlink integrity, selectors, and boundaries in Ceph QA suites."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
from collections import Counter
from pathlib import Path

import yaml


parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, required=True)
parser.add_argument("--target", required=True)
parser.add_argument("--expected-target-sha", required=True)
parser.add_argument("--scope", action="append", required=True)
parser.add_argument("--base-series", required=True)
parser.add_argument("--strict", action="store_true")
args = parser.parse_args()
repo = args.repo.resolve()


def git(*git_args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", "-C", str(repo), *git_args], capture_output=True, check=False
    )
    if check and result.returncode:
        raise SystemExit(
            f"git {' '.join(git_args)} failed: "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    return result


target_sha = git("rev-parse", f"{args.target}^{{commit}}").stdout.decode().strip()
if target_sha != args.expected_target_sha:
    raise SystemExit(f"Unexpected target SHA: {target_sha}")

tree_output = git("ls-tree", "-rz", args.target, "--", *args.scope).stdout
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
if not entries:
    raise SystemExit("No tree entries found in the requested scope(s)")


class TaggedLoader(yaml.SafeLoader):
    """Safe YAML loader that tolerates teuthology-local tags."""


def construct_unknown(loader: TaggedLoader, _suffix: str, node: yaml.Node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


TaggedLoader.add_multi_constructor("!", construct_unknown)


def tree_mode(path: str) -> str | None:
    output = git("ls-tree", args.target, "--", path).stdout.decode("utf-8")
    for line in output.splitlines():
        metadata, listed_path = line.split("\t", 1)
        if listed_path == path:
            return metadata.split()[0]
    return None


def resolve_symlink_path(path: str) -> tuple[str, list[dict[str, str]], bool]:
    current = posixpath.normpath(path)
    chain: list[dict[str, str]] = []
    for _ in range(32):
        parts = [part for part in current.split("/") if part not in ("", ".")]
        replaced = False
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            if tree_mode(prefix) != "120000":
                continue
            target = git("show", f"{args.target}:{prefix}").stdout.decode().strip()
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


yaml_files: list[str] = []
yaml_errors: dict[str, str] = {}
symlinks: list[dict[str, object]] = []
broken_symlinks: list[dict[str, object]] = []
all_text: list[str] = []
for entry in entries:
    content = git("show", f"{args.target}:{entry['path']}").stdout.decode("utf-8")
    all_text.append(content)
    if entry["mode"] == "120000":
        target = content.strip()
        first_hop = posixpath.normpath(posixpath.join(posixpath.dirname(entry["path"]), target))
        resolved, chain, exists = resolve_symlink_path(first_hop)
        record = {"path": entry["path"], "target": target, "resolved": resolved, "chain": chain}
        symlinks.append(record)
        if not exists:
            broken_symlinks.append(record)
        continue
    if entry["path"].endswith((".yaml", ".yml")):
        yaml_files.append(entry["path"])
        try:
            yaml.load(content, Loader=TaggedLoader)
        except yaml.YAMLError as exc:
            yaml_errors[entry["path"]] = str(exc)

joined = "\n".join(all_text)
series = re.escape(args.base_series)
selector_counts = {
    f"branch_{args.base_series}": len(
        re.findall(rf"(?m)^\s*branch:\s*{series}\s*$", joined)
    ),
    f"cephadm_branch_{args.base_series}": len(
        re.findall(rf"(?m)^\s*cephadm_branch:\s*{series}\s*$", joined)
    ),
    "floating_base_image": len(
        re.findall(rf"(?m)^\s*image:\s*.*(?::{series}|:latest-{series})\s*$", joined)
    ),
    "target_sha_image": joined.count("ceph:$sha1"),
    "grep_sha1": joined.count("grep $sha1"),
}
boundary_counts = {
    "require_osd_release": joined.count("require-osd-release"),
    "set_require_min_compat_client": joined.count("set-require-min-compat-client"),
    "cephadm_upgrade": joined.count("ceph orch upgrade"),
    "install_upgrade": joined.count("install.upgrade"),
    "cephadm_pause": joined.count("ceph orch upgrade pause"),
    "cephadm_resume": joined.count("ceph orch upgrade resume"),
    "thrasher_mentions": len(re.findall(r"(?i)thrash", joined)),
    "zap_mentions": len(re.findall(r"(?i)\bzap\b", joined)),
    "repair_mentions": len(re.findall(r"(?i)\brepair\b", joined)),
}
version_tokens = dict(sorted(Counter(re.findall(r"\bv\d+\.\d+\.\d+\b", joined)).items()))

summary = {
    "target": args.target,
    "target_sha": target_sha,
    "scopes": args.scope,
    "entries": len(entries),
    "mode_counts": dict(sorted(Counter(entry["mode"] for entry in entries).items())),
    "yaml_files": len(yaml_files),
    "yaml_parse_errors": yaml_errors,
    "symlinks": len(symlinks),
    "broken_symlinks": broken_symlinks,
    "selector_counts": selector_counts,
    "boundary_counts": boundary_counts,
    "explicit_version_tokens": version_tokens,
}
print(json.dumps(summary, ensure_ascii=False, indent=2))

if args.strict and (yaml_errors or broken_symlinks):
    raise SystemExit(1)
