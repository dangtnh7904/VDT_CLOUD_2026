"""Classify inspected optional Dashboard AuthX CRUD backend and unit tests."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
reasons = {
    "src/pybind/mgr/dashboard/controllers/_crud.py":
        "T07-dashboard-optional-crud: New CRUD metadata/form/serializer framework "
        "is invoked by newly added AuthX user and RGW role Dashboard pages; "
        "no existing upgrade command, daemon startup or acceptance path uses "
        "these manual management forms. SecretStr redaction is unit-tested.",
    "src/pybind/mgr/dashboard/controllers/ceph_users.py":
        "T07-dashboard-optional-authx: New /api/cluster/user CRUD handlers call "
        "MON auth ls/add/del/caps/import/export only on explicit Dashboard "
        "requests. No automatic migration of existing keys/caps or demonstrated "
        "dependency in upgrade delivery/validation; inspect separately if the "
        "site runbook manages upgrade identities through this new page.",
    "src/pybind/mgr/dashboard/tests/test_ceph_users.py":
        "T07-dashboard-authx-unit: New mocked API/schema unit tests cover "
        "optional AuthX CRUD and key redaction, without changing an executed "
        "upgrade recipe or production state.",
    "src/pybind/mgr/dashboard/tests/test_crud.py":
        "T07-dashboard-crud-unit: New serializer/form schema unit tests "
        "exercise optional CRUD framework; no independent upgrade path."
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for target, reason in reasons.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "trivial"
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
