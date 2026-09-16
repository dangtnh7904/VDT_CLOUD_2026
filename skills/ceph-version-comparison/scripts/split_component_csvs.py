#!/usr/bin/env python3
"""Create owner component CSVs as exact, ordered subsets of a master inventory."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path


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


class SplitError(RuntimeError):
    pass


def read_inventory(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise SplitError(f"Inventory does not exist: {path}")
    data = path.read_bytes()
    if not data.startswith(b"\xef\xbb\xbf"):
        raise SplitError("Inventory must use UTF-8 with BOM")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SplitError(f"Inventory is not valid UTF-8: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
    header = list(reader.fieldnames or [])
    if header != BASE_COLUMNS:
        raise SplitError("Master inventory header does not match the 21-column contract")
    rows = [dict(row) for row in reader]
    if not rows:
        raise SplitError("Inventory has no data rows")
    return header, rows


def validate_owner(row: dict[str, str], line_number: int) -> str:
    group = row.get("group", "")
    owner = row.get("owner_report", "")
    if not re.fullmatch(r"\d{1,2}", group) or not 1 <= int(group) <= 99:
        raise SplitError(f"Line {line_number}: invalid group {group!r}")
    normalized_group = f"{int(group):02d}"
    if not re.fullmatch(
        re.escape(normalized_group) + r"-[a-z0-9][a-z0-9-]*", owner
    ):
        raise SplitError(
            f"Line {line_number}: owner_report {owner!r} does not match group {group!r}"
        )
    if row.get("priority", "") not in {"P0", "P1", "P2"}:
        raise SplitError(f"Line {line_number}: invalid priority")
    if row.get("review_mode", "") not in {
        "deep",
        "conditional",
        "support",
        "reference-only",
    }:
        raise SplitError(f"Line {line_number}: invalid review_mode")
    for column in ("file_type", "analysis_decision"):
        if not row.get(column, ""):
            raise SplitError(f"Line {line_number}: blank {column}")
    return owner


def atomic_write(
    path: Path,
    header: list[str],
    rows: list[dict[str, str]],
) -> None:
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
                fieldnames=header,
                delimiter=";",
                lineterminator="\r\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split a classified master inventory into owner component CSVs."
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--owner",
        action="append",
        help="Owner report stem to emit; repeat as needed. Omit to emit all owners.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing component CSVs; may erase appended analysis columns",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        header, rows = read_inventory(args.inventory.resolve())
        grouped: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
        paths: set[str] = set()
        for line_number, row in enumerate(rows, start=2):
            path = row.get("path", "")
            if not path:
                raise SplitError(f"Line {line_number}: blank path")
            if path in paths:
                raise SplitError(f"Line {line_number}: duplicate path {path!r}")
            paths.add(path)
            owner = validate_owner(row, line_number)
            grouped.setdefault(owner, []).append(row)

        selected = list(dict.fromkeys(args.owner or list(grouped)))
        unknown = [owner for owner in selected if owner not in grouped]
        if unknown:
            raise SplitError(f"Unknown owner report(s): {', '.join(unknown)}")

        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        targets = {owner: output_dir / f"{owner}.csv" for owner in selected}
        existing = [str(path) for path in targets.values() if path.exists()]
        if existing and not args.force:
            raise SplitError(
                "Refusing to overwrite existing component CSV(s): " + ", ".join(existing)
            )

        for owner in selected:
            atomic_write(targets[owner], header, grouped[owner])

        result = {
            "inventory": str(args.inventory.resolve()),
            "output_dir": str(output_dir),
            "created": {owner: len(grouped[owner]) for owner in selected},
            "rows_created": sum(len(grouped[owner]) for owner in selected),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (SplitError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
