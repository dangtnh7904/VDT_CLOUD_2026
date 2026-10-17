"""Classify inspected Dashboard settings helper extraction."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
prefix = "src/pybind/mgr/dashboard/"
trivial = {
    prefix + "controllers/settings.py": "T07-settings-helper-extract: Existing get/set/delete/bulk_set routes now call SettingsService.attribute_handler and _to_native with the same uppercase/hyphen normalization and NotFound behavior; new Prometheus settings route is reviewed in MGR-020.",
    prefix + "services/settings.py": "T07-settings-helper-extract: Moves the same attribute_handler and _to_native implementation out of the Settings controller for reuse; no independent setting value, permission or upgrade-gate behavior changes.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in trivial} == set(trivial)
for row in rows:
    name = row["path"]
    if name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
