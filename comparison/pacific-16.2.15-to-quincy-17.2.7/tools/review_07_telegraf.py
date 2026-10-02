"""Classify inspected Telegraf MGR module and line-protocol helper changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/pybind/mgr/telegraf/module.py": "MGR-009: Target asserts configured interval is truthy during module initialization whereas base directly converts it; zero/false interval can prevent Telegraf module startup after target MGR activation, changing monitoring availability.",
}
trivial = {
    "src/pybind/mgr/telegraf/basesocket.py": "T07-telegraf-socket: Adds types and earlier hostname/port asserts for malformed non-Unix URLs; valid URL socket family, address and send path remain unchanged.",
    "src/pybind/mgr/telegraf/protocol.py": "T07-telegraf-protocol: Adds types and replaces u-prefixed literals with equivalent Python 3 strings; line-protocol fields and separators unchanged.",
    "src/pybind/mgr/telegraf/utils.py": "T07-telegraf-utils: Adds types and explicit conversion/error for nonstandard values; inspected module call sites use string measurement/tag keys and scalar numeric/string values, leaving emitted valid metrics unchanged.",
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
        row["finding_id"] = "MGR-009"
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
