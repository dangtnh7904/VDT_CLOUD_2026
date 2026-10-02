"""Classify inspected telemetry migration, dashboard flow, docs and tests."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/pybind/mgr/telemetry/module.py": "MGR-004: Telemetry migrates legacy revision consent to persistent collection list, gates report data and nagging by collection, adds off-by-default perf channel, and changes CLI on/off/preview behavior.",
    "src/pybind/mgr/dashboard/controllers/telemetry.py": "MGR-004: Dashboard telemetry preview now uses report lock and opt-in forwards license to target telemetry on method; affects consent flow after target MGR activation.",
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/cluster/telemetry/telemetry.component.ts": "MGR-004: Dashboard adds perf channel to form and omits large perf fields from inline preview while preserving full report for download; affects consent review workflow.",
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/cluster/telemetry/telemetry.component.html": "MGR-004: Dashboard exposes perf channel checkbox and warns inline preview omits perf fields, changing opt-in and report inspection flow.",
}
trivial = {
    "doc/mgr/progress.rst": "T07-progress-doc: New operator explanation of existing progress commands and new option; implementation impact is MGR-002, no independent upgrade recipe.",
    "doc/mgr/prometheus.rst": "T07-prometheus-doc: Adds config reference directives and link markup; no independent exporter default or rollout step.",
    "doc/mgr/telemetry.rst": "T07-telemetry-doc: Documents channels, collections and preview CLI; runtime consent behavior is in MGR-004, no independent upgrade procedure.",
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/cluster/telemetry/telemetry.component.spec.ts": "T07-telemetry-ui-test: Unit assertions cover perf preview formatting; no separate deployed or acceptance-selector change.",
    "src/pybind/mgr/dashboard/frontend/src/app/shared/components/telemetry-notification/telemetry-notification.component.scss": "T07-telemetry-style: Changes only font size/link color and weight in telemetry notification; no consent or health-signal logic.",
    "src/pybind/mgr/telemetry/__init__.py": "T07-telemetry-test-hook: Import wrapper and UNITTEST hook were added with telemetry upgrade unit-test setup; no distinct runtime upgrade behavior established beyond MGR-004.",
    "src/pybind/mgr/telemetry/tests/__init__.py": "T07-telemetry-test-marker: Empty test-package marker, no runtime or acceptance selector.",
    "src/pybind/mgr/telemetry/tests/test_telemetry.py": "T07-telemetry-unit-test: Mocked cases assert legacy revision 1/2/3 conversion to collections; supports MGR-004 without independent rollout effect.",
    "src/pybind/mgr/telemetry/tox.ini": "T07-telemetry-local-tox: Defines a local pytest environment; no evidence it is an executed upgrade acceptance gate or production dependency.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert not (set(affect) & set(trivial))
selected = set(affect) | set(trivial)
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-004"
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
