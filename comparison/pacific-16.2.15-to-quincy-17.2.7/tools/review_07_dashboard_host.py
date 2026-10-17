"""Classify inspected Dashboard host inventory and adjacent support hunks."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/pybind/mgr/dashboard/controllers/host.py":
        "MGR-041: GET /api/host switches to API 1.3, defaults to five hosts "
        "with X-Total-Count, returns orchestrator hosts rather than a merged "
        "Ceph/orchestrator list when backend is available, and caches source "
        "host inventory for 60 seconds. Host acceptance can differ.",
    "src/pybind/mgr/dashboard/plugins/ttl_cache.py":
        "MGR-041: New named cache and invalidator back the target 60-second "
        "Dashboard host inventory cache. This file also changes RBD cache "
        "implementation; that separate caller still requires review.",
    "src/pybind/mgr/dashboard/frontend/src/app/shared/api/host.service.ts":
        "MGR-041: Dashboard host client passes table pagination params, "
        "observes response headers and attaches them to returned host rows; "
        "its Accept 1.2 is supported by target API 1.3 minor compatibility.",
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/cluster/hosts/hosts.component.ts":
        "MGR-041: Host UI passes table page/search/sort params and reads total "
        "count from response headers instead of treating the response as a "
        "complete inventory; service-instance display also moves backend-side.",
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/cluster/hosts/hosts.component.html":
        "MGR-041: Host table enables server-side pagination with maxLimit 25 "
        "and new service-instance display, changing how the host inventory "
        "is presented during rollout checks."
}
trivial = {
    "src/pybind/mgr/dashboard/tests/test_host.py":
        "T07-dashboard-host-unit: Mock/unit assertions corroborate MGR-041 "
        "host source, API version, fact and service-instance changes; no "
        "executed upgrade or acceptance recipe changes in this file.",
    "src/pybind/mgr/dashboard/frontend/src/app/shared/api/host.service.spec.ts":
        "T07-dashboard-host-service-spec: Frontend unit request expectation "
        "tracks paged host query parameters from MGR-041; no independent "
        "upgrade gate or runtime change.",
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/cluster/hosts/hosts.component.spec.ts":
        "T07-dashboard-host-component-spec: Unit fixtures adapt to response "
        "headers, service-instance schema and unavailable fact display "
        "from MGR-041; no independent upgrade execution path.",
    "src/pybind/mgr/dashboard/__init__.py":
        "T07-dashboard-init: Drops Python 2 absolute_import and changes "
        "UNITTEST-only frontend path mock/PATH setup; production Dashboard "
        "module import path is unchanged.",
    "src/pybind/mgr/dashboard/api/__init__.py":
        "T07-dashboard-api-init: Only drops Python 2 absolute_import; no "
        "endpoint registration or upgrade execution change.",
    "src/pybind/mgr/dashboard/cherrypy_backports.py":
        "T07-dashboard-typing: Only adds a type-ignore comment to the "
        "same cheroot SSL adapter import; runtime patch call is identical.",
    "src/pybind/mgr/dashboard/controllers/__init__.py":
        "T07-dashboard-crud-export: Adds exports for the new optional CRUD "
        "controller framework and an executable mode bit; Python import of "
        "existing controllers and upgrade delivery path do not change.",
    "src/pybind/mgr/dashboard/controllers/_rest_controller.py":
        "T07-dashboard-crud-alias: Maps generated CRUD method aliases by "
        "attribute name instead of wrapped function name; target callers are "
        "new optional authx/RGW CRUD endpoints, not upgrade control paths.",
    "src/pybind/mgr/dashboard/exceptions.py":
        "T07-dashboard-exceptions: Only drops Python 2 absolute_import; "
        "Dashboard exception fields and handling are unchanged."
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for target, reason in {**affect, **trivial}.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "affect" if target in affect else "trivial"
    row["finding_id"] = "MGR-041" if target in affect else ""
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
