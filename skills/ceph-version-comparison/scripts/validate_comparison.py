#!/usr/bin/env python3
"""Validate the structural and CSV invariants of a Ceph comparison suite."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


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

ALLOWED_STATUS = {"A", "M", "D", "R"}
ALLOWED_PRIORITY = {"P0", "P1", "P2"}
ALLOWED_REVIEW_MODE = {"deep", "conditional", "support", "reference-only"}
NUMBERED_FILE_RE = re.compile(r"^(\d{2}-.+)\.(md|csv)$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


@dataclass
class CsvData:
    path: Path
    header: list[str]
    rows: list[dict[str, str]]


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)

    def fail(self, message: str) -> None:
        self.errors.append(message)


def read_csv(path: Path, validation: Validation, *, master: bool) -> CsvData | None:
    if not path.is_file():
        validation.fail(f"Missing CSV: {path}")
        return None

    data = path.read_bytes()
    validation.check(data.startswith(b"\xef\xbb\xbf"), f"CSV lacks UTF-8 BOM: {path}")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        validation.fail(f"CSV is not valid UTF-8: {path}: {exc}")
        return None

    validation.check(
        re.search(r"(?<!\r)\n", text) is None and re.search(r"\r(?!\n)", text) is None,
        f"CSV must use CRLF only: {path}",
    )
    validation.check(text.endswith("\r\n"), f"CSV must end with CRLF: {path}")

    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
    header = list(reader.fieldnames or [])
    unique_header = len(header) == len(set(header))
    validation.check(unique_header, f"Duplicate CSV header in {path}")
    if master:
        header_matches = header == BASE_COLUMNS
        validation.check(header_matches, f"Master CSV header mismatch: {path}")
    else:
        header_matches = header[: len(BASE_COLUMNS)] == BASE_COLUMNS
        validation.check(header_matches, f"Component CSV must start with the 21 base columns: {path}")
    if not unique_header or not header_matches:
        return None

    rows: list[dict[str, str]] = []
    for line_number, raw_row in enumerate(reader, start=2):
        row = dict(raw_row)
        if None in row:
            validation.fail(f"CSV row has extra fields: {path}:{line_number}")
            row.pop(None, None)
        for column in header:
            if row.get(column) is None:
                validation.fail(
                    f"CSV row has fewer fields than the header: {path}:{line_number}"
                )
                row[column] = ""
        rows.append(row)
    validation.check(bool(rows), f"CSV has no data rows: {path}")
    return CsvData(path, header, rows)


def valid_blob(value: str) -> bool:
    return bool(re.fullmatch(r"0|[0-9a-f]{40}|[0-9a-f]{64}", value))


def absent_value(value: str) -> bool:
    return bool(value) and set(value) == {"0"}


def validate_master_rows(
    data: CsvData,
    validation: Validation,
    *,
    allow_unclassified: bool,
) -> None:
    paths: set[str] = set()
    indices: list[int] = []
    base_refs: set[str] = set()
    target_refs: set[str] = set()
    group_owners: dict[str, set[str]] = defaultdict(set)
    owner_groups: dict[str, set[str]] = defaultdict(set)

    for line_number, row in enumerate(data.rows, start=2):
        prefix = f"{data.path}:{line_number}"
        try:
            index = int(row["index"])
            validation.check(index > 0, f"{prefix}: index must be positive")
            indices.append(index)
        except (TypeError, ValueError):
            validation.fail(f"{prefix}: invalid index {row.get('index')!r}")

        path = row.get("path", "")
        validation.check(bool(path), f"{prefix}: path is blank")
        validation.check(path not in paths, f"{prefix}: duplicate path {path!r}")
        paths.add(path)

        base_refs.add(row.get("base_tag", ""))
        target_refs.add(row.get("target_tag", ""))
        status = row.get("status", "")
        detail = row.get("status_detail", "")
        old_path = row.get("old_path", "")
        validation.check(status in ALLOWED_STATUS, f"{prefix}: unsupported status {status!r}")
        validation.check(bool(detail) and detail.startswith(status), f"{prefix}: status_detail does not match status")
        if status == "R":
            validation.check(bool(old_path), f"{prefix}: rename lacks old_path")
            score = detail[1:]
            validation.check(
                score.isdigit() and 0 <= int(score or -1) <= 100,
                f"{prefix}: invalid rename status_detail {detail!r}",
            )
        else:
            validation.check(not old_path, f"{prefix}: non-rename has old_path")
            validation.check(detail == status, f"{prefix}: invalid status_detail {detail!r}")

        binary = row.get("binary", "")
        additions = row.get("additions", "")
        deletions = row.get("deletions", "")
        validation.check(binary in {"TRUE", "FALSE"}, f"{prefix}: invalid binary flag")
        if binary == "TRUE":
            validation.check(
                additions == "" and deletions == "",
                f"{prefix}: binary LOC must be blank",
            )
        elif binary == "FALSE":
            validation.check(
                additions.isdigit() and deletions.isdigit(),
                f"{prefix}: text LOC must be non-negative integers",
            )

        for column in ("old_mode", "new_mode"):
            validation.check(
                re.fullmatch(r"0|[0-7]{6}", row.get(column, "")) is not None,
                f"{prefix}: invalid {column}",
            )
        for column in ("old_blob", "new_blob"):
            validation.check(valid_blob(row.get(column, "")), f"{prefix}: invalid {column}")

        old_mode_absent = absent_value(row.get("old_mode", ""))
        new_mode_absent = absent_value(row.get("new_mode", ""))
        old_blob_absent = absent_value(row.get("old_blob", ""))
        new_blob_absent = absent_value(row.get("new_blob", ""))
        if status == "A":
            validation.check(
                old_mode_absent and old_blob_absent and not new_mode_absent and not new_blob_absent,
                f"{prefix}: A status has inconsistent mode/blob endpoints",
            )
        elif status == "D":
            validation.check(
                not old_mode_absent and not old_blob_absent and new_mode_absent and new_blob_absent,
                f"{prefix}: D status has inconsistent mode/blob endpoints",
            )
        elif status in {"M", "R"}:
            validation.check(
                not old_mode_absent
                and not old_blob_absent
                and not new_mode_absent
                and not new_blob_absent,
                f"{prefix}: {status} status has an absent mode/blob endpoint",
            )

        classification_columns = (
            "group",
            "owner_report",
            "priority",
            "file_type",
            "review_mode",
            "analysis_decision",
        )
        classification = [row.get(column, "") for column in classification_columns]
        if allow_unclassified and not any(classification):
            continue

        validation.check(all(classification), f"{prefix}: incomplete classification")
        group = row.get("group", "")
        owner = row.get("owner_report", "")
        group_is_valid = bool(re.fullmatch(r"\d{1,2}", group)) and 1 <= int(group or 0) <= 99
        validation.check(group_is_valid, f"{prefix}: invalid owner group {group!r}")
        normalized_group = f"{int(group):02d}" if group_is_valid else group
        validation.check(
            re.fullmatch(re.escape(normalized_group) + r"-[a-z0-9][a-z0-9-]*", owner)
            is not None,
            f"{prefix}: owner_report does not match group",
        )
        validation.check(
            row.get("priority", "") in ALLOWED_PRIORITY,
            f"{prefix}: invalid priority",
        )
        validation.check(bool(row.get("file_type", "")), f"{prefix}: blank file_type")
        validation.check(
            row.get("review_mode", "") in ALLOWED_REVIEW_MODE,
            f"{prefix}: invalid review_mode",
        )
        validation.check(
            bool(row.get("analysis_decision", "")),
            f"{prefix}: blank analysis_decision",
        )
        group_owners[group].add(owner)
        owner_groups[owner].add(group)

    validation.check(
        indices == list(range(1, len(data.rows) + 1)),
        f"Master index is not contiguous in {data.path}",
    )
    validation.check(
        len(base_refs) == 1 and "" not in base_refs,
        f"Master CSV must contain one non-blank base_tag: {sorted(base_refs)!r}",
    )
    validation.check(
        len(target_refs) == 1 and "" not in target_refs,
        f"Master CSV must contain one non-blank target_tag: {sorted(target_refs)!r}",
    )
    for group, owners in sorted(group_owners.items()):
        validation.check(
            len(owners) == 1,
            f"Group {group} maps to multiple owner reports: {sorted(owners)}",
        )
    for owner, groups in sorted(owner_groups.items()):
        validation.check(
            len(groups) == 1,
            f"Owner report {owner} maps to multiple groups: {sorted(groups)}",
        )


def split_markdown_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [re.sub(r"\s+", " ", cell.replace("`", "").strip().lower()) for cell in stripped.split("|")]


def separator_row(line: str) -> bool:
    cells = split_markdown_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def find_per_file_tables(text: str) -> list[int]:
    lines = text.splitlines()
    findings: list[int] = []
    for index in range(len(lines) - 1):
        if "|" not in lines[index] or not separator_row(lines[index + 1]):
            continue
        cells = split_markdown_row(lines[index])
        has_path = any(
            re.search(r"(^|\b)(path|file|đường dẫn)(\b|$)", cell) for cell in cells
        )
        has_status = any("status" in cell or "trạng thái" in cell for cell in cells)
        has_add = any(
            cell in {"+", "thêm"}
            or "addition" in cell
            or "dòng thêm" in cell
            for cell in cells
        )
        has_delete = any(
            cell in {"-", "−", "xóa"}
            or "deletion" in cell
            or "dòng xóa" in cell
            for cell in cells
        )
        if has_path and has_status and has_add and has_delete:
            findings.append(index + 1)
    return findings


def normalize_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif " " in target:
        target = target.split(" ", 1)[0]
    return unquote(target).split("#", 1)[0].split("?", 1)[0]


def markdown_links(text: str) -> list[str]:
    return [normalize_link_target(match.group(1)) for match in LINK_RE.finditer(text)]


def validate_markdown(
    path: Path,
    validation: Validation,
    *,
    expected_csv: str | None = None,
) -> None:
    if not path.is_file():
        validation.fail(f"Missing Markdown: {path}")
        return
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        validation.fail(f"Markdown is not valid UTF-8: {path}: {exc}")
        return

    for line_number in find_per_file_tables(text):
        validation.fail(
            f"Per-file diff table is forbidden: {path}:{line_number}; move rows to CSV"
        )

    links = markdown_links(text)
    if expected_csv:
        validation.check(
            expected_csv in links or f"./{expected_csv}" in links,
            f"{path} does not link to {expected_csv}",
        )

    for target in links:
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        target_path = (path.parent / target).resolve()
        validation.check(target_path.exists(), f"Broken local link in {path}: {target}")


def validate_component_csv(
    component: CsvData,
    master: CsvData,
    owner: str,
    validation: Validation,
) -> None:
    expected = [row for row in master.rows if row["owner_report"] == owner]
    validation.check(
        len(component.rows) == len(expected),
        f"{component.path}: expected {len(expected)} owner rows, found {len(component.rows)}",
    )

    for position, (actual, wanted) in enumerate(zip(component.rows, expected), start=2):
        for column in BASE_COLUMNS:
            validation.check(
                actual.get(column, "") == wanted.get(column, ""),
                f"{component.path}:{position}: base column {column!r} differs from master",
            )

    actual_paths = [row.get("path", "") for row in component.rows]
    expected_paths = [row["path"] for row in expected]
    validation.check(
        actual_paths == expected_paths,
        f"{component.path}: owner subset order or membership differs from master",
    )
    validation.check(
        len(actual_paths) == len(set(actual_paths)),
        f"{component.path}: duplicate path",
    )


def present_numbered_stems(root: Path) -> tuple[set[str], set[str]]:
    markdown: set[str] = set()
    csv_files: set[str] = set()
    for path in root.iterdir():
        if not path.is_file():
            continue
        match = NUMBERED_FILE_RE.fullmatch(path.name)
        if not match:
            continue
        stem, extension = match.groups()
        (markdown if extension == "md" else csv_files).add(stem)
    return markdown, csv_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a Ceph comparison Markdown/CSV suite."
    )
    parser.add_argument("--root", type=Path, required=True, help="Comparison directory")
    parser.add_argument(
        "--mode",
        choices=("inventory", "partial", "complete"),
        default="partial",
    )
    parser.add_argument("--plan", type=Path, help="Optional adjacent plan Markdown")
    parser.add_argument(
        "--allow-unclassified",
        action="store_true",
        help="Allow all-blank classification fields in a newly built raw inventory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.allow_unclassified and args.mode != "inventory":
        print(
            "ERROR: --allow-unclassified is only valid with --mode inventory",
            file=sys.stderr,
        )
        return 2
    validation = Validation()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"ERROR: comparison root does not exist: {root}", file=sys.stderr)
        return 1

    master_path = root / "00-file-inventory.csv"
    master = read_csv(master_path, validation, master=True)
    if master:
        validate_master_rows(
            master,
            validation,
            allow_unclassified=args.allow_unclassified,
        )

    readme = root / "README.md"
    validate_markdown(readme, validation)
    inventory_md = root / "00-file-inventory.md"
    validate_markdown(
        inventory_md,
        validation,
        expected_csv="00-file-inventory.csv",
    )

    if readme.is_file():
        try:
            readme_text = readme.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            readme_text = ""
        if readme_text:
            readme_targets = markdown_links(readme_text)
            validation.check(
                "00-file-inventory.md" in readme_targets
                or "./00-file-inventory.md" in readme_targets,
                f"{readme} does not link to 00-file-inventory.md",
            )
            validation.check(
                "00-file-inventory.csv" in readme_targets
                or "./00-file-inventory.csv" in readme_targets,
                f"{readme} does not link to 00-file-inventory.csv",
            )

    if args.plan:
        validate_markdown(args.plan.resolve(), validation)

    markdown_stems, csv_stems = present_numbered_stems(root)
    present_component_stems = (markdown_stems | csv_stems) - {"00-file-inventory"}

    if args.mode == "inventory":
        stems_to_validate: set[str] = set()
    elif args.mode == "partial":
        stems_to_validate = present_component_stems
        for stem in sorted(present_component_stems):
            validation.check(stem in markdown_stems, f"Missing Markdown for {stem}.csv")
            validation.check(stem in csv_stems, f"Missing CSV for {stem}.md")
    else:
        if master:
            expected_owners = {row["owner_report"] for row in master.rows if row["owner_report"]}
        else:
            expected_owners = set()
        stems_to_validate = expected_owners
        for stem in sorted(expected_owners):
            validation.check(stem in markdown_stems, f"Missing complete-suite Markdown: {stem}.md")
            validation.check(stem in csv_stems, f"Missing complete-suite CSV: {stem}.csv")
        unexpected = present_component_stems - expected_owners
        validation.check(
            not unexpected,
            f"Numbered reports have no owner rows in master inventory: {sorted(unexpected)}",
        )

    validated_components: list[str] = []
    for stem in sorted(stems_to_validate):
        md_path = root / f"{stem}.md"
        csv_path = root / f"{stem}.csv"
        if md_path.is_file():
            validate_markdown(md_path, validation, expected_csv=csv_path.name)
        if csv_path.is_file() and master:
            component = read_csv(csv_path, validation, master=False)
            if component:
                validate_component_csv(component, master, stem, validation)
                validated_components.append(stem)

    if validation.errors:
        print(f"Validation failed with {len(validation.errors)} error(s):", file=sys.stderr)
        for error in validation.errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    status_counts = Counter(row["status"] for row in master.rows) if master else Counter()
    classified = bool(master) and all(row["owner_report"] for row in master.rows)
    group_counts = (
        Counter(f"{int(row['group']):02d}" for row in master.rows if row["group"])
        if master
        else Counter()
    )
    priority_counts = (
        Counter(row["priority"] for row in master.rows if row["priority"])
        if master
        else Counter()
    )
    additions = (
        sum(int(row["additions"]) for row in master.rows if row["additions"])
        if master
        else 0
    )
    deletions = (
        sum(int(row["deletions"]) for row in master.rows if row["deletions"])
        if master
        else 0
    )
    result = {
        "valid": True,
        "mode": args.mode,
        "root": str(root),
        "rows": len(master.rows) if master else 0,
        "status_counts": dict(sorted(status_counts.items())),
        "additions": additions,
        "deletions": deletions,
        "binary_files": sum(row["binary"] == "TRUE" for row in master.rows)
        if master
        else 0,
        "mode_changes": sum(
            row["old_mode"] != row["new_mode"]
            and row["old_mode"] not in {"0", "000000"}
            and row["new_mode"] not in {"0", "000000"}
            for row in master.rows
        )
        if master
        else 0,
        "gitlinks": sum(
            "160000" in {row["old_mode"], row["new_mode"]} for row in master.rows
        )
        if master
        else 0,
        "classified": classified,
        "group_counts": dict(sorted(group_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "components_validated": validated_components,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
