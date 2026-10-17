"""Classify reviewed PG autoscaler changes and type-only MDS autoscaler diff."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
prefix = "src/pybind/mgr/"
pg = prefix + "pg_autoscaler/module.py"
trivial = {
    prefix + "mds_autoscaler/module.py": (
        "T07-mds-autoscaler-types: Endpoint hunk only changes typing imports, method annotations "
        "and whitespace; fs_map notification, orchestrator apply and error paths are unchanged."
    ),
    prefix + "balancer/__init__.py": (
        "T07-balancer-flake8: Adds only a flake8 noqa directive before the unchanged Module import; "
        "balancer runtime is screened separately in module.py."
    ),
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = {pg} | set(trivial)
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name == pg:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-024;MGR-025"
        row["impact_reason"] = (
            "MGR-024: Global noautoscale moves from MGR option and per-pool mode rewrites "
            "to persistent OSDMap flag, preserving per-pool modes but changing mixed-version control. "
            "MGR-025: Capacity calculation uses df bytes_used rather than stored times raw rate, "
            "and a configurable threshold replaces fixed factor 3 for PG adjustments."
        )
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
