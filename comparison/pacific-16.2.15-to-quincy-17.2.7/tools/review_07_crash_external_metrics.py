"""Classify inspected crash, Influx and Zabbix monitoring changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/pybind/mgr/crash/module.py": ("MGR-006", "Crash health now separates daemon RECENT_CRASH from RECENT_MGR_MODULE_CRASH; the detail-pruning helper only slices a local list and does not cap emitted detail after many crashes."),
    "doc/mgr/crash.rst": ("MGR-006", "Crash collection runbook adds ceph-crash.service upload path and client.crash keyring/profile requirements; following it changes availability of post-upgrade crash health evidence."),
    "src/pybind/mgr/influx/module.py": ("MGR-007", "Influx module constrains interval/threads options, changes runtime config-set parsing, and replaces None worker shutdown sentinel with empty list; can alter metrics delivery and MGR restart behavior."),
    "src/pybind/mgr/zabbix/module.py": ("MGR-008", "Zabbix config-set validates numeric text but stores the original string in live config, while serve waits on interval; target may lose Zabbix monitoring after a runtime interval change."),
}
trivial = {
    "doc/mgr/influx.rst": "T07-influx-doc: Converts configuration prose to confval directives and fixes markup; monitoring runtime change is MGR-007, no new upgrade recipe.",
    "doc/mgr/telegraf.rst": "T07-telegraf-doc: Adds literal-block markers to existing socket listener examples; address and command content unchanged.",
    "doc/mgr/zabbix.rst": "T07-zabbix-doc: Corrects hostname/address spelling only; command and configuration values unchanged.",
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
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
