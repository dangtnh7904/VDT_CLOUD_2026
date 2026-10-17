"""Classify inspected Dashboard frontend build and executed QA gate changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
base = "src/pybind/mgr/dashboard/"
decisions = {
    "frontend/cypress/e2e/orchestrator/grafana/grafana.feature": (
        "affect", "MGR-043",
        "T07-cephadm-cypress-spec: New Grafana panel and legend assertions are "
        "selected by run-cephadm-e2e-tests.sh, changing the executed "
        "Dashboard monitoring acceptance path."
    ),
    "frontend/cypress/e2e/orchestrator/workflow/01-create-cluster-welcome.feature": (
        "affect", "MGR-043",
        "T07-cephadm-cypress-spec: New welcome/cluster-expansion wizard steps "
        "are selected by the cephadm Dashboard E2E runner."
    ),
    "frontend/cypress/e2e/orchestrator/workflow/02-create-cluster-add-host.feature": (
        "affect", "MGR-043",
        "T07-cephadm-cypress-spec: New host add/remove/label workflow steps "
        "are selected by the cephadm Dashboard E2E runner, altering "
        "acceptance coverage if that job is used."
    ),
    "frontend/cypress/plugins/index.js": (
        "trivial", "",
        "T07-cypress-plugin-syntax: Removes only a trailing comma after the "
        "last log task; the registered task and returned value are unchanged."
    ),
    "frontend/jest.config.cjs": (
        "affect", "MGR-047",
        "T07-jest28-gate: New Jest 28 config moves package.json settings, adds "
        "ESM transforms/global setup and jasmine2 runner; npm test:ci invokes it "
        "from run-frontend-unittests.sh."
    ),
    "frontend/package-lock.json": (
        "affect", "MGR-047",
        "T07-frontend-lock: npm ci in Dashboard CMake and cephadm test setup "
        "uses changed locked dependency graph; package manifest upgrades "
        "Angular 12 to 13, Bootstrap 4 to 5, Cypress 9 to 10, Jest 26 to 28."
    ),
    "frontend/package.json": (
        "affect", "MGR-043;MGR-044;MGR-047",
        "T07-frontend-manifest: Changes Cypress 9->10 and Gherkin spec directory "
        "for MGR-043, TSLint->ESLint script for MGR-044, and Jest 26->28/"
        "Angular 12->13/Bootstrap 4->5 dependencies used by npm ci and "
        "frontend build/test for MGR-047."
    ),
    "run-frontend-unittests.sh": (
        "affect", "MGR-047",
        "T07-frontend-test-runner: Activation path moves from dashboard/"
        "node-env to dashboard/frontend/node-env, matching target CMake; "
        "script then runs build, Jest test:ci, lint and i18n gates."
    ),
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for relative, (impact, finding, reason) in decisions.items():
    target = base + relative
    matches = [row for row in rows if row["path"] == target]
    assert len(matches) == 1, target
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], target
    row["upgrade_impact"] = impact
    row["finding_id"] = finding
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
