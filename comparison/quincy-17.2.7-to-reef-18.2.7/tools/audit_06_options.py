#!/usr/bin/env python3
"""Print semantic endpoint changes for owner 06 option YAML files.

This is a read-only review helper.  It reads both blobs through ``git show``
and reports option additions, removals, and field-level changes so the binary
upgrade-impact review can be traced without relying on churn or path names.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1] / "ceph17.2.7"
BASE = "v17.2.7"
TARGET = "v18.2.7"
OPTION_DIR = "src/common/options"
FILES = [
    "cephfs-mirror.yaml.in",
    "crimson.yaml.in",
    "global.yaml.in",
    "mds-client.yaml.in",
    "mds.yaml.in",
    "mon.yaml.in",
    "osd.yaml.in",
    "rbd.yaml.in",
    "rgw.yaml.in",
]


def load(ref: str, path: str) -> dict[str, dict]:
    text = subprocess.check_output(
        ["git", "-C", str(REPO), "show", f"{ref}:{path}"],
        text=True,
        encoding="utf-8",
    )
    # CMake placeholders beginning with '@' are valid in the generated file
    # but not valid as an unquoted YAML scalar in the .in source.
    text = re.sub(
        r"^(\s+[A-Za-z_]+:\s+)(@[^\r\n]+)$",
        lambda match: match.group(1) + json.dumps(match.group(2)),
        text,
        flags=re.MULTILINE,
    )
    document = yaml.safe_load(text) or {}
    return {item["name"]: item for item in document.get("options", [])}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional YAML basenames to inspect; defaults to every owner-06 option file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = args.files or FILES
    unknown = sorted(set(selected) - set(FILES))
    if unknown:
        raise SystemExit(f"unknown option files: {unknown!r}")
    result: dict[str, dict] = {}
    for filename in selected:
        path = f"{OPTION_DIR}/{filename}"
        before = load(BASE, path)
        after = load(TARGET, path)
        added = {name: after[name] for name in sorted(after.keys() - before.keys())}
        removed = {name: before[name] for name in sorted(before.keys() - after.keys())}
        changed: dict[str, dict] = {}
        for name in sorted(before.keys() & after.keys()):
            fields = {}
            for field in sorted(before[name].keys() | after[name].keys()):
                old = before[name].get(field, "<ABSENT>")
                new = after[name].get(field, "<ABSENT>")
                if old != new:
                    fields[field] = {"before": old, "after": new}
            if fields:
                changed[name] = fields
        result[path] = {
            "added": added,
            "removed": removed,
            "changed": changed,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
