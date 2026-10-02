"""Classify reviewed scrubber renames using rename-aware endpoint hunks."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "src/osd/scrubber/scrub_machine.cc": "Scrub FSM tracks reservation and duration, warns when blocked, and discards unexpected DigestUpdate rather than deferring it.",
    "src/osd/scrubber/scrub_machine.h": "Scrub FSM custom start/digest reactions and blocked-range warning state change transition behavior.",
    "src/osd/scrubber/scrub_machine_lstnr.h": "Scrub listener gains reservation, timing and blocked-range warning hooks used by FSM.",
}
trivial = {
    "src/osd/scrubber/PrimaryLogScrub.cc": "Rename-aware diff against src/osd/PrimaryLogScrub.cc shows include/access refactor, equivalent object_info construction, and debug-string changes only.",
    "src/osd/scrubber/PrimaryLogScrub.h": "Rename-aware diff against src/osd/PrimaryLogScrub.h only adjusts OSD include path.",
    "src/osd/scrubber/ScrubStore.cc": "Rename-aware diff against src/osd/ScrubStore.cc only adjusts osd_types include path.",
    "src/osd/scrubber/ScrubStore.h": "Rename-aware diff against src/osd/ScrubStore.h only adjusts SnapMapper include path.",
}
all_paths = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in all_paths} == all_paths
for row in rows:
    name = row["path"]
    if name in affect:
        assert row["upgrade_impact"] in ("", "affect")
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "OSD-025"
        row["impact_reason"] = f"OSD-025: {affect[name]}"
    elif name in trivial:
        assert row["upgrade_impact"] in ("", "trivial")
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-scrub-rename: {trivial[name]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
