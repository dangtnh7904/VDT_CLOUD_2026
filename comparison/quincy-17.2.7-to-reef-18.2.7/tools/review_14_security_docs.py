#!/usr/bin/env python3
"""Classify the two direct security-document rows after endpoint hunk review."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "14-security-cross-reference.csv"

VERDICTS = {
    "doc/security/cves.rst": (
        "trivial",
        "",
        "SEC-DOC-001: endpoint hunk only adds index/link entries for CVE-2023-46159 "
        "and CVE-2022-3650; it changes no code, configuration, packaging or executed "
        "validation path. Advisory applicability must be established from component "
        "code and authoritative affected-version evidence, not this list row.",
    ),
    "doc/security/index.rst": (
        "trivial",
        "",
        "SEC-DOC-002: endpoint hunk removes obsolete GPG key and key-server prose from "
        "the vulnerability-reporting page; it changes reporting documentation only and "
        "has no causal path to upgrade delivery, mixed-version behavior or runtime state.",
    ),
}


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    paths = {row["path"] for row in rows}
    if paths != set(VERDICTS):
        raise RuntimeError(f"owner 14 row set changed: {sorted(paths)!r}")

    for row in rows:
        impact, finding_id, reason = VERDICTS[row["path"]]
        row["upgrade_impact"] = impact
        row["finding_id"] = finding_id
        row["impact_reason"] = reason

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=header,
            delimiter=";",
            lineterminator="\r\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    print("Classified owner 14: affect=0 trivial=2 unclassified=0")


if __name__ == "__main__":
    main()
