"""Classify inspected local disk-prediction source changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
prefix = "src/pybind/mgr/diskprediction_local/"
affect = {
    prefix + "module.py": "MGR-022: Local prediction uses typed integer intervals and a Predictor factory; model initialization exceptions return an empty result (direct query maps to unknown), while periodic predictions can set/reset MON device life expectancy.",
    prefix + "predictor.py": "MGR-022: ProphetStor differential SMART attributes now use intersection across all days instead of first-day keys, and Red Hat unknown model manufacturer returns Unknown rather than raising from None.lower().",
}
trivial = {
    prefix + "__init__.py": "T07-diskprediction-flake8: Adds only a flake8 noqa directive before the unchanged Module import; no prediction/runtime behavior changes."
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = set(affect) | set(trivial)
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-022"
        row["impact_reason"] = affect[name]
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
