"""Classify Dashboard RBD image observability and cache refactor."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/pybind/mgr/dashboard/controllers/rbd.py":
        "MGR-042: Dashboard GET /api/block/image/{image_spec} drops the "
        "omit_usage argument and calls RbdService.get_image without it; "
        "image management handlers move to the service layer and its cache "
        "invalidation. RBD detail validation can differ.",
    "src/pybind/mgr/dashboard/services/rbd.py":
        "MGR-042: RBD detail no longer supports omit_usage, so eligible "
        "fast-diff usage is computed on detail reads; disabled journal "
        "mirroring is reported Disabled rather than journal/unknown. CRUD "
        "calls invalidate 30-second image-reference cache after success; "
        "snapshot schedule remote dispatch also moves to direct module methods."
}
trivial = {
    "src/pybind/mgr/dashboard/tests/test_cache.py":
        "T07-dashboard-rbd-cache-unit: New unit tests exercise TTLCache get, "
        "expiry, FIFO maxsize and manager identity; they corroborate cache "
        "code but do not change upgrade acceptance or runtime behavior."
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for target, reason in {**affect, **trivial}.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "affect" if target in affect else "trivial"
    row["finding_id"] = "MGR-042" if target in affect else ""
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
