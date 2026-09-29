#!/usr/bin/env python3
"""Build a lossless Ceph endpoint diff inventory from one Git worktree."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BASE_COLUMNS = [
    "index",
    "base_tag",
    "target_tag",
    "path",
    "old_path",
    "status",
    "status_detail",
    "additions",
    "deletions",
    "binary",
    "old_mode",
    "new_mode",
    "old_blob",
    "new_blob",
    "group",
    "owner_report",
    "priority",
    "file_type",
    "review_mode",
    "analysis_decision",
    "diff_note",
]

ALLOWED_STATUS = {"A", "M", "D", "R", "T"}


class InventoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class NameRecord:
    path: str
    old_path: str
    status: str
    status_detail: str


@dataclass(frozen=True)
class NumstatRecord:
    path: str
    old_path: str
    additions: str
    deletions: str
    binary: bool


@dataclass(frozen=True)
class RawRecord:
    path: str
    old_path: str
    status_detail: str
    old_mode: str
    new_mode: str
    old_blob: str
    new_blob: str


def run_git(
    repo: Path,
    args: Iterable[str],
    *,
    allowed_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )
    if process.returncode not in allowed_codes:
        stderr = process.stderr.decode("utf-8", errors="replace").strip()
        raise InventoryError(
            f"git {' '.join(args)} failed with exit code "
            f"{process.returncode}: {stderr}"
        )
    return process


def decode_git_field(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InventoryError(
            "A Git path is not valid UTF-8. The CSV contract cannot represent it "
            "losslessly; handle that path explicitly before continuing."
        ) from exc


def nul_tokens(data: bytes, label: str) -> list[bytes]:
    if not data:
        return []
    if not data.endswith(b"\0"):
        raise InventoryError(f"{label} output is not NUL-terminated")
    return data[:-1].split(b"\0")


def add_unique(records: dict[str, object], path: str, record: object, label: str) -> None:
    if path in records:
        raise InventoryError(f"Duplicate endpoint path in {label}: {path!r}")
    records[path] = record


def parse_status_detail(detail: str, label: str) -> str:
    if not detail:
        raise InventoryError(f"Empty status token in {label} output")
    status = detail[0]
    if status not in ALLOWED_STATUS:
        raise InventoryError(
            f"Unsupported Git status {detail!r} in {label}; handle "
            "type/copy/conflict semantics explicitly instead of coercing it"
        )
    if status in {"A", "M", "D", "T"} and detail != status:
        raise InventoryError(f"Malformed status token {detail!r} in {label}")
    if status == "R":
        score = detail[1:]
        if not score.isdigit() or not 0 <= int(score) <= 100:
            raise InventoryError(f"Malformed rename token {detail!r} in {label}")
    return status


def parse_name_status(data: bytes) -> tuple[list[str], dict[str, NameRecord]]:
    tokens = nul_tokens(data, "name-status")
    order: list[str] = []
    records: dict[str, NameRecord] = {}
    index = 0

    while index < len(tokens):
        detail = decode_git_field(tokens[index])
        index += 1
        status = parse_status_detail(detail, "name-status")

        if status == "R":
            if index + 1 >= len(tokens):
                raise InventoryError("Truncated rename in name-status output")
            old_path = decode_git_field(tokens[index])
            path = decode_git_field(tokens[index + 1])
            index += 2
        else:
            if index >= len(tokens):
                raise InventoryError("Truncated path in name-status output")
            old_path = ""
            path = decode_git_field(tokens[index])
            index += 1

        record = NameRecord(path, old_path, status, detail)
        add_unique(records, path, record, "name-status")
        order.append(path)

    return order, records


def parse_numstat(data: bytes) -> dict[str, NumstatRecord]:
    tokens = nul_tokens(data, "numstat")
    records: dict[str, NumstatRecord] = {}
    index = 0

    while index < len(tokens):
        header = decode_git_field(tokens[index])
        index += 1
        parts = header.split("\t", 2)
        if len(parts) != 3:
            raise InventoryError(f"Malformed numstat record: {header!r}")
        additions, deletions, path = parts

        if path == "":
            if index + 1 >= len(tokens):
                raise InventoryError("Truncated rename in numstat output")
            old_path = decode_git_field(tokens[index])
            path = decode_git_field(tokens[index + 1])
            index += 2
        else:
            old_path = ""

        binary = additions == "-" and deletions == "-"
        if (additions == "-") != (deletions == "-"):
            raise InventoryError(f"Half-binary numstat record for {path!r}")
        if binary:
            additions = ""
            deletions = ""
        elif not additions.isdigit() or not deletions.isdigit():
            raise InventoryError(f"Invalid numstat counts for {path!r}")

        record = NumstatRecord(path, old_path, additions, deletions, binary)
        add_unique(records, path, record, "numstat")

    return records


def parse_raw(data: bytes) -> dict[str, RawRecord]:
    tokens = nul_tokens(data, "raw")
    records: dict[str, RawRecord] = {}
    index = 0

    while index < len(tokens):
        metadata = decode_git_field(tokens[index])
        index += 1
        if not metadata.startswith(":"):
            raise InventoryError(f"Malformed raw metadata: {metadata!r}")
        fields = metadata[1:].split()
        if len(fields) != 5:
            raise InventoryError(
                f"Unsupported combined or malformed raw record: {metadata!r}"
            )
        old_mode, new_mode, old_blob, new_blob, detail = fields
        status = parse_status_detail(detail, "raw")

        if status == "R":
            if index + 1 >= len(tokens):
                raise InventoryError("Truncated rename in raw output")
            old_path = decode_git_field(tokens[index])
            path = decode_git_field(tokens[index + 1])
            index += 2
        else:
            if index >= len(tokens):
                raise InventoryError("Truncated path in raw output")
            old_path = ""
            path = decode_git_field(tokens[index])
            index += 1

        record = RawRecord(
            path,
            old_path,
            detail,
            old_mode,
            new_mode,
            old_blob,
            new_blob,
        )
        add_unique(records, path, record, "raw")

    return records


def parse_shortstat(text: str) -> tuple[int, int, int]:
    def extract(pattern: str) -> int:
        match = re.search(pattern, text)
        return int(match.group(1)) if match else 0

    return (
        extract(r"(\d+) files? changed"),
        extract(r"(\d+) insertions?\(\+\)"),
        extract(r"(\d+) deletions?\(-\)"),
    )


def atomic_csv_write(path: Path, rows: list[dict[str, str]], force: bool) -> None:
    if path.exists() and not force:
        raise InventoryError(
            f"Output already exists: {path}. Refusing to erase classification; "
            "pass --force only when replacement is intentional."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8-sig",
        newline="",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(handle.name)
    try:
        with handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=BASE_COLUMNS,
                delimiter=";",
                lineterminator="\r\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def atomic_json_write(path: Path, payload: dict[str, object], force: bool) -> None:
    if path.exists() and not force:
        raise InventoryError(f"Summary output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def preflight(args: argparse.Namespace) -> dict[str, object]:
    repo = args.repo.resolve()
    if not repo.is_dir():
        raise InventoryError(f"Repository directory does not exist: {repo}")

    inside = run_git(repo, ["rev-parse", "--is-inside-work-tree"]).stdout.strip()
    if inside != b"true":
        raise InventoryError(f"Not a Git worktree: {repo}")

    base_sha = decode_git_field(
        run_git(repo, ["rev-parse", "--verify", f"{args.base}^{{commit}}"]).stdout
    ).strip()
    target_sha = decode_git_field(
        run_git(repo, ["rev-parse", "--verify", f"{args.target}^{{commit}}"]).stdout
    ).strip()

    dirty = bool(run_git(repo, ["status", "--porcelain=v1", "-z"]).stdout)
    if dirty and not args.allow_dirty:
        raise InventoryError(
            "The source worktree is dirty. Commit/stash it or pass --allow-dirty "
            "and disclose the exception."
        )

    shallow_text = decode_git_field(
        run_git(repo, ["rev-parse", "--is-shallow-repository"]).stdout
    ).strip()
    shallow = shallow_text == "true"
    if shallow and not args.allow_shallow:
        raise InventoryError(
            "The source repository is shallow. Fetch the required history or pass "
            "--allow-shallow and disclose the limitation."
        )

    ancestor_process = run_git(
        repo,
        ["merge-base", "--is-ancestor", base_sha, target_sha],
        allowed_codes=(0, 1),
    )
    ancestor = ancestor_process.returncode == 0
    if not ancestor and not args.allow_non_ancestor:
        raise InventoryError(
            "The base commit is not an ancestor of the target. Pass "
            "--allow-non-ancestor only when a two-endpoint comparison is intended."
        )

    git_version = decode_git_field(run_git(repo, ["--version"]).stdout).strip()
    commit_count = int(
        decode_git_field(
            run_git(repo, ["rev-list", "--count", f"{base_sha}..{target_sha}"]).stdout
        ).strip()
    )
    return {
        "repo": str(repo),
        "base_ref": args.base,
        "target_ref": args.target,
        "base_sha": base_sha,
        "target_sha": target_sha,
        "git_version": git_version,
        "dirty": dirty,
        "shallow": shallow,
        "base_is_ancestor": ancestor,
        "commit_count": commit_count,
    }


def build(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, object]]:
    facts = preflight(args)
    repo = Path(str(facts["repo"]))
    rename_option = f"--find-renames={args.rename_threshold}"
    common = [
        "--no-ext-diff",
        "--no-textconv",
        rename_option,
        str(facts["base_sha"]),
        str(facts["target_sha"]),
    ]

    name_process = run_git(repo, ["diff", "--name-status", "-z", *common])
    numstat_process = run_git(repo, ["diff", "--numstat", "-z", *common])
    raw_process = run_git(repo, ["diff", "--raw", "-z", "--no-abbrev", *common])
    shortstat_process = run_git(repo, ["diff", "--shortstat", *common])
    for label, process in (
        ("name-status", name_process),
        ("numstat", numstat_process),
        ("raw", raw_process),
        ("shortstat", shortstat_process),
    ):
        warning = process.stderr.decode("utf-8", errors="replace").strip()
        if warning:
            raise InventoryError(
                f"git diff {label} emitted a warning; resolve it before trusting "
                f"rename detection: {warning}"
            )

    name_data = name_process.stdout
    numstat_data = numstat_process.stdout
    raw_data = raw_process.stdout
    shortstat_text = decode_git_field(shortstat_process.stdout)

    order, names = parse_name_status(name_data)
    numstats = parse_numstat(numstat_data)
    raw = parse_raw(raw_data)
    if not order:
        raise InventoryError(
            "The endpoint refs have no changed files; no inventory was written."
        )
    key_set = set(order)
    if key_set != set(numstats) or key_set != set(raw):
        raise InventoryError(
            "name-status, numstat, and raw diff produced different endpoint-path sets"
        )

    rows: list[dict[str, str]] = []
    for row_index, path in enumerate(order, start=1):
        name = names[path]
        numstat = numstats[path]
        raw_record = raw[path]
        if name.old_path != numstat.old_path or name.old_path != raw_record.old_path:
            raise InventoryError(f"Rename source mismatch for {path!r}")
        if name.status_detail != raw_record.status_detail:
            raise InventoryError(f"Status-detail mismatch for {path!r}")

        notes: list[str] = []
        if name.status == "R" and numstat.additions == "0" and numstat.deletions == "0":
            notes.append("Git rename heuristic with 0/0 content change; verify logical move.")
        if (
            raw_record.old_mode != raw_record.new_mode
            and raw_record.old_mode != "000000"
            and raw_record.new_mode != "000000"
        ):
            notes.append(
                f"Mode changed {raw_record.old_mode} -> {raw_record.new_mode}."
            )
        if "160000" in {raw_record.old_mode, raw_record.new_mode}:
            notes.append("Gitlink changed; inspect referenced dependency objects.")

        rows.append(
            {
                "index": str(row_index),
                "base_tag": args.base,
                "target_tag": args.target,
                "path": path,
                "old_path": name.old_path,
                "status": name.status,
                "status_detail": name.status_detail,
                "additions": numstat.additions,
                "deletions": numstat.deletions,
                "binary": "TRUE" if numstat.binary else "FALSE",
                "old_mode": raw_record.old_mode,
                "new_mode": raw_record.new_mode,
                "old_blob": raw_record.old_blob,
                "new_blob": raw_record.new_blob,
                "group": "",
                "owner_report": "",
                "priority": "",
                "file_type": "",
                "review_mode": "",
                "analysis_decision": "",
                "diff_note": " ".join(notes),
            }
        )

    status_counts = Counter(row["status"] for row in rows)
    additions = sum(int(row["additions"]) for row in rows if row["additions"])
    deletions = sum(int(row["deletions"]) for row in rows if row["deletions"])
    short_files, short_additions, short_deletions = parse_shortstat(shortstat_text)
    if (len(rows), additions, deletions) != (
        short_files,
        short_additions,
        short_deletions,
    ):
        raise InventoryError(
            "Parsed totals do not match git diff --shortstat: "
            f"parsed={(len(rows), additions, deletions)}, "
            f"shortstat={(short_files, short_additions, short_deletions)}"
        )

    summary: dict[str, object] = {
        **facts,
        "rename_detection": rename_option,
        "files": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "additions": additions,
        "deletions": deletions,
        "binary_files": sum(row["binary"] == "TRUE" for row in rows),
        "zero_zero_text_records": sum(
            row["binary"] == "FALSE"
            and row["additions"] == "0"
            and row["deletions"] == "0"
            for row in rows
        ),
        "renames": status_counts.get("R", 0),
        "mode_changes": sum(
            row["old_mode"] != row["new_mode"]
            and row["old_mode"] != "000000"
            and row["new_mode"] != "000000"
            for row in rows
        ),
        "gitlinks": sum(
            "160000" in {row["old_mode"], row["new_mode"]} for row in rows
        ),
    }
    return rows, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the 21-column master CSV for a Ceph endpoint comparison."
    )
    parser.add_argument("--repo", type=Path, required=True, help="Git worktree")
    parser.add_argument("--base", required=True, help="Base ref or tag")
    parser.add_argument("--target", required=True, help="Target ref or tag")
    parser.add_argument("--output", type=Path, required=True, help="Inventory CSV")
    parser.add_argument(
        "--summary-json", type=Path, help="Optional path for the JSON source summary"
    )
    parser.add_argument(
        "--rename-threshold",
        default="50%",
        help="Value passed to --find-renames (default: 50%%)",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--allow-shallow", action="store_true")
    parser.add_argument("--allow-non-ancestor", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace output files; this can erase manual classification",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path = args.output.resolve()
        summary_path = args.summary_json.resolve() if args.summary_json else None
        if summary_path and os.path.normcase(str(output_path)) == os.path.normcase(
            str(summary_path)
        ):
            raise InventoryError(
                "--output and --summary-json must resolve to different files"
            )
        if not args.force:
            existing = [
                str(path)
                for path in (output_path, summary_path)
                if path is not None and path.exists()
            ]
            if existing:
                raise InventoryError(
                    "Refusing to overwrite existing output(s): " + ", ".join(existing)
                )
        rows, summary = build(args)
        atomic_csv_write(output_path, rows, args.force)
        if summary_path:
            atomic_json_write(summary_path, summary, args.force)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (InventoryError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
