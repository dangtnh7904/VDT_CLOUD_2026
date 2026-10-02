"""Classify inspected MGR Python bridge, config-error, and message-factory changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/mgr/ActivePyModule.cc": ("MGR-006", "Target records module and caller when handling Python errors in module load, notify, or remote dispatch, generating crash metadata consumed by crash health."),
    "src/mgr/ActivePyModules.cc": ("MGR-006;MGR-014", "Target supplies module and caller to Python exception crash dumps and returns MON config-set status to Python module callers rather than discarding it."),
    "src/mgr/ActivePyModules.h": ("MGR-014", "Target set_config interface returns MON status and message to the Python bridge, enabling rejected module options to surface as exceptions."),
    "src/mgr/BaseMgrModule.cc": ("MGR-014", "Target Python bridge converts nonzero MON config-set result into ValueError, changing module command error handling during rollout."),
    "src/mgr/PyModule.cc": ("MGR-006;MGR-014", "Target generates crash dump metadata for Python module exceptions and propagates MON config-set status/message instead of log-only failure."),
    "src/mgr/PyModule.h": ("MGR-006;MGR-014", "Target declares the crash metadata path and status-returning module-config interface used by the changed Python bridge."),
    "src/mgr/PyModuleRunner.cc": ("MGR-006", "Target records module and caller for Python serve/shutdown exceptions, changing crash evidence available during MGR module restart."),
    "src/mgr/StandbyPyModules.cc": ("MGR-006", "Target records module and caller for standby module load exceptions, changing crash evidence on MGR failover."),
}
trivial = {
    **{name: "T07-crimson-mgr-message-factory: Adds Crimson make_message friend access only; wire encoding, payload, and classic MGR/MON behavior are unchanged." for name in (
        "src/messages/MMgrConfigure.h", "src/messages/MMgrDigest.h", "src/messages/MMgrMap.h",
        "src/messages/MMgrOpen.h", "src/messages/MMgrReport.h")},
    "src/mgr/ActivePyModule.h": "T07-activepy-include: Includes PyModule.h for relocated handle_pyerror declaration; no separate runtime behavior beyond MGR-006.",
    "src/mgr/BaseMgrStandbyModule.cc": "T07-standbypy-namespace: Qualifies std::string namespace only; module entry points and behavior unchanged.",
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
