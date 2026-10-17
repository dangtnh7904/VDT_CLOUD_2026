"""Classify inspected MGR and Dashboard QA acceptance changes for owner 07."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
qa_mgr = {
    "qa/tasks/mgr/mgr_test_case.py":
        "MGR-039: Shared MGR QA setup now requests explicit JSON from mgr module ls "
        "and no longer sets mds/defer_client_eviction_on_laggy_osds=false; "
        "module test setup and warning baseline can differ.",
    "qa/tasks/mgr/test_module_selftest.py":
        "MGR-039: Selftest QA no longer deletes legacy device_health_metrics "
        "pool and now prunes crash reports after synthetic failure; acceptance "
        "cleanup follows target .mgr storage and health behavior.",
    "qa/tasks/mgr/test_progress.py":
        "MGR-039: Recovery-event QA cases explicitly enable "
        "mgr/progress/allow_pg_recovery_event while a new case asserts the "
        "default disabled behavior; test setup and expected result change.",
    "qa/workunits/mgr/test_per_module_finisher.sh":
        "MGR-039: RADOS MGR workunit adds ceph telemetry diff to its command "
        "smoke sequence; the command can now fail that suite."
}
qa_dashboard = {
    "qa/tasks/mgr/dashboard/helper.py":
        "MGR-040: Dashboard QA schema helper fixes JTuple's namedtuple type "
        "name; assertion machinery changes for tests using tuple schemas.",
    "qa/tasks/mgr/dashboard/test_health.py":
        "MGR-040: Dashboard health QA now requires flags_state booleans in "
        "CephFS payload; API acceptance schema changes.",
    "qa/tasks/mgr/dashboard/test_mgr_module.py":
        "MGR-040: Dashboard MGR-module QA adds channel_perf to telemetry "
        "option schemas; target acceptance covers the new option.",
    "qa/tasks/mgr/dashboard/test_pool.py":
        "MGR-040: Dashboard pool QA switches expected device health pool to "
        ".mgr and includes RBD application metadata in expected pool objects.",
    "qa/tasks/mgr/dashboard/test_rgw.py":
        "MGR-040: Dashboard RGW QA requires daemon port and changes subuser "
        "create status expectation from 201 to 200; API acceptance changes."
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for target, reason in {**qa_mgr, **qa_dashboard}.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "MGR-039" if target in qa_mgr else "MGR-040"
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
