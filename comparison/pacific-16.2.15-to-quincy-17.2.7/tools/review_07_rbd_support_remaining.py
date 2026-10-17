"""Classify remaining inspected RBD support handler state and refactors."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
findings = {
    "src/pybind/mgr/rbd_support/perf.py": (
        "affect", "MGR-035",
        "MGR-035: PerfHandler user_queries and image caches move from instance "
        "initialization to mutable class attributes. A new handler made during "
        "RBD-support recovery can reuse unexpired query/counter state, whereas "
        "Pacific initializes empty state; immediate rbd perf output and query "
        "registration can differ. Other tuple/type rewrites preserve normal "
        "counter calculations."
    ),
    "src/pybind/mgr/rbd_support/task.py": (
        "trivial", "",
        "T07-rbd-task-refactor: Endpoint changes are annotations, equivalent "
        "CLI dispatch relocation, same JSON task-list output, and sequence-key "
        "str-to-bytes normalization. The RADOS cstr_list binding encodes both "
        "forms to the same bytes; open_ioctx reads only the first two spec "
        "fields and new asserts follow existing nonempty validation. Pool-removal "
        "and blocklist recovery branches already exist in Pacific 16.2.15."
    ),
    "src/pybind/mgr/rbd_support/schedule.py": (
        "trivial", "",
        "T07-rbd-schedule-refactor: from_name now receives the module directly "
        "with adapted callers; find searches the same image/pool/global IDs, "
        "and datetime imports/type hints retain normal scheduling. An empty "
        "Schedule raises a clearer exception but still cannot yield a next run. "
        "Localized-option migration and blocklist propagation already exist in "
        "the Pacific endpoint."
    ),
    "src/pybind/mgr/rbd_support/trash_purge_schedule.py": (
        "trivial", "",
        "T07-rbd-trash-schedule-refactor: Endpoint hunks move the lock to the "
        "class, add type hints and relocate CLI dispatch to module.py while "
        "the single handler's purge, refresh, queue and schedule expressions "
        "remain equivalent. Refresh-delay and blocklist-recovery paths are "
        "already present in Pacific 16.2.15."
    ),
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
for target, (impact, finding_id, reason) in findings.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = impact
    row["finding_id"] = finding_id
    row["impact_reason"] = reason
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
