"""Classify inspected RGW data-notifier and legacy FIFO endpoint diffs."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
decisions = {
    "src/rgw/rgw_datalog.cc": (
        "affect", "RGW-003",
        "RGW-003: At notify interval 0, target skips collecting modified bucket shards but still appends data-log entries; base retains the growing in-memory set while its notifier waits."
    ),
    "src/rgw/rgw_rados.cc": (
        "affect", "RGW-003",
        "RGW-003: Target starts RGWDataNotifier only when notify interval is nonzero at init; base always starts it, and a target started at zero needs restart to create the notifier. Other hunks need review."
    ),
    "src/rgw/rgw_datalog.h": (
        "trivial", "RGW-003",
        "RGW-003 support: endpoint hunk changes equivalent string literals and adds noexcept to existing renew_run thread function declaration; no independent data-log or notification behavior path."
    ),
    "src/rgw/cls_fifo_legacy.cc": (
        "trivial", "",
        "Legacy FIFO hunk only switches equivalent string_view npos/nullopt spelling and per-operation log prefix calls; push/trim/meta state transitions and wire data remain unchanged."
    ),
    "src/rgw/cls_fifo_legacy.h": (
        "trivial", "",
        "Legacy FIFO push declaration has only whitespace/line-wrap change; API parameters and implementation behavior remain the same."
    ),
}

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for path, (impact, finding, reason) in decisions.items():
    matches = [row for row in rows if row["path"] == path]
    assert len(matches) == 1, path
    row = matches[0]
    assert row["upgrade_impact"] in ("", impact) and row["finding_id"] in ("", finding), path
    if row["impact_reason"]:
        assert row["impact_reason"].startswith("RGW-003:") or row["impact_reason"] == reason or path.startswith("src/rgw/cls_fifo_legacy"), path
    row["upgrade_impact"] = impact
    row["finding_id"] = finding
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified 2 RGW data-notifier and 3 supporting/trivial rows")
