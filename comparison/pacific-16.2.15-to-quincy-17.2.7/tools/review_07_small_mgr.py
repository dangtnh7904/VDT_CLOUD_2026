"""Classify reviewed small MGR runtime, RESTful, stub, and test hunks."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
findings = {
    "src/pybind/mgr/mgr_util.py": (
        "affect", "MGR-029",
        "MGR-029: to_pretty_timedelta changes total_seconds to timedelta.seconds; for "
        "24-48 hour positive durations the displayed hours wrap at 24 (e.g. 30h becomes "
        "6h), and negative durations format differently. Orchestrator and progress status "
        "call this formatter; name_to_config_section only moves within the file."
    ),
    "src/pybind/mgr/restful/module.py": (
        "affect", "MGR-030",
        "MGR-030: get_osd_pools no longer gates CRUSH rule traversal on rule min_size/" 
        "max_size versus pool size. RESTful OSD inventory and pool-filter responses now "
        "derive pool membership whenever a matching rule exists, including when rule "
        "size metadata is absent or outside the old gate. No CRUSH placement change claimed."
    ),
    "src/pybind/mgr/ceph_module.pyi": (
        "trivial", "",
        "T07-ceph-module-stub: Only Python type declarations change for OSDMap test "
        "builder, generic get return, and RocksDB version getter; implementation is "
        "reviewed in its runtime owner, with no executable code in this stub."
    ),
    "src/pybind/mgr/devicehealth/__init__.py": (
        "trivial", "", "T07-devicehealth-init: Adds flake8 noqa to an unchanged Module import."
    ),
    "src/pybind/mgr/insights/tests/test_health.py": (
        "trivial", "", "T07-insights-test-style: Test assertions and fixtures are unchanged; only formatting differs."
    ),
    "src/pybind/mgr/restful/api/crush.py": (
        "trivial", "", "T07-restful-unused-import: Removes unused defaultdict import; no executed API path changes."
    ),
    "src/pybind/mgr/restful/decorators.py": (
        "trivial", "", "T07-restful-py2-import: Removes Python 2 absolute_import future declaration; runtime code unchanged."
    ),
    "src/pybind/mgr/restful/hooks.py": (
        "trivial", "", "T07-restful-py2-import: Removes Python 2 absolute_import future declaration; runtime code unchanged."
    ),
    "src/pybind/mgr/rook/__init__.py": (
        "trivial", "", "T07-rook-test-import: Additional tests import is gated by UNITTEST environment; production Module import unchanged."
    ),
    "src/pybind/mgr/selftest/__init__.py": (
        "trivial", "", "T07-selftest-init: Adds flake8 noqa and removes blank lines; Module import unchanged."
    ),
    "src/pybind/mgr/tests/__init__.py": (
        "trivial", "", "T07-mgr-test-style: Changes only test mock spacing, blank lines, and Python 2 future import; no production path."
    ),
    "src/pybind/mgr/tests/test_tls.py": (
        "trivial", "", "T07-tls-test-style: Same invalid-RDN assertion reformatted onto one line."
    ),
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
for target, (impact, finding_id, reason) in findings.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = impact
    row["finding_id"] = finding_id
    row["impact_reason"] = reason
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
