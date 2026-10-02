"""Classify inspected Python module registry and OSDMap binding hunks."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/mgr/PyOSDMap.cc": (
        "MGR-016",
        "Target BasePyOSDMap constructor returns Python TypeError for missing/wrong capsule instead of aborting MGR; conditional continuity change if custom module or selftest passes invalid input.",
    ),
}
trivial = {
    "src/mgr/PyModuleRegistry.cc": "T07-module-probe-order: Directory iterator results move from sorted set to vector, but names remain unique, each module has its own Python sub-interpreter, and active/standby activation iterates stored map; no demonstrated upgrade-path behavior from probe order alone.",
    "src/mgr/PyModuleRegistry.h": "T07-module-probe-interface: Declares vector return type for probe_modules and std::optional type migration; no independent activation or wire behavior beyond screened implementation.",
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
        ids, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = ids
        row["impact_reason"] = f"{ids}: {reason}"
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
