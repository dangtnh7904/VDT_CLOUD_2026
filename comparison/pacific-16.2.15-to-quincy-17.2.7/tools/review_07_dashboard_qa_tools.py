"""Classify inspected Dashboard test infrastructure and lint gate changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
e2e = {
    "src/pybind/mgr/dashboard/ci/cephadm/bootstrap-cluster.sh":
        "MGR-043: Dashboard cephadm E2E fixture boots a Quincy CI image "
        "instead of Pacific, changing the test cluster baseline.",
    "src/pybind/mgr/dashboard/ci/cephadm/run-cephadm-e2e-tests.sh":
        "MGR-043: E2E runner moves to Cypress 10 spec/exclude options, sets "
        "monitoring URLs, applies node-exporter and selects new cypress/e2e "
        "workflow/Grafana specs; acceptance path changes when this CI runs.",
    "src/pybind/mgr/dashboard/frontend/cypress.config.ts":
        "MGR-043: New Cypress configuration changes default baseUrl to HTTPS, "
        "spec selection, retries/video/session settings and reporter setup; "
        "these govern Dashboard E2E acceptance when invoked.",
    "src/pybind/mgr/dashboard/frontend/cypress.json":
        "MGR-043: Deletes old Cypress config; target cypress.config.ts replaces "
        "its HTTP baseUrl, ignoreTestFiles and video/retry behavior.",
    "src/pybind/mgr/dashboard/frontend/applitools.config.js":
        "MGR-043: Visual E2E matrix drops the two 800x600 browser cases and "
        "adds APPLITOOLS_BATCH_ID; visual acceptance coverage differs if used."
}
lint = {
    "src/pybind/mgr/dashboard/constraints.txt":
        "MGR-044: Dashboard tox and backend API test installation reference "
        "this file; compatible-release bounds widen from patch to minor/major "
        "families for several Python dependencies, changing possible resolved "
        "test environments without proving production package changes.",
    "src/pybind/mgr/dashboard/frontend/.eslintrc.json":
        "MGR-044: New Angular ESLint configuration defines TS/template lint "
        "rules used by ng lint when frontend unit/lint gate runs.",
    "src/pybind/mgr/dashboard/frontend/angular.json":
        "MGR-044: Angular lint builder switches from TSLint to ESLint and "
        "changes lintFilePatterns to src TS/HTML; npm lint gate examines "
        "different rules/files. Other JSON hunks are formatting."
}
trivial = {
    "src/pybind/mgr/dashboard/frontend/.gitignore":
        "T07-dashboard-gitignore: Only ignores the local .angular/cache "
        "directory; no target bundle, daemon or executed acceptance path changes."
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for target, reason in {**e2e, **lint, **trivial}.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "trivial" if target in trivial else "affect"
    row["finding_id"] = "" if target in trivial else ("MGR-043" if target in e2e else "MGR-044")
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
