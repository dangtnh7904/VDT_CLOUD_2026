"""Verify and classify the Cypress 10 Dashboard E2E migration cluster."""

import csv
import subprocess
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"
prefix = "src/pybind/mgr/dashboard/frontend/cypress/"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


# Endpoint evidence for test discovery and the Cypress major-version migration.
base_config = show("v16.2.15", "src/pybind/mgr/dashboard/frontend/cypress.json")
target_config = show("v17.2.7", "src/pybind/mgr/dashboard/frontend/cypress.config.ts")
base_package = show("v16.2.15", "src/pybind/mgr/dashboard/frontend/package.json")
target_package = show("v17.2.7", "src/pybind/mgr/dashboard/frontend/package.json")
assert '"ignoreTestFiles"' in base_config
assert '"supportFile": "cypress/support/index.ts"' in base_config
assert "specPattern: 'cypress/e2e/**/*-spec.{js,jsx,ts,tsx}'" in target_config
assert "excludeSpecPattern: ['*.po.ts', '**/orchestrator/**']" in target_config
assert '"cypress": "9.7.0"' in base_package
assert '"cypress": "10.11.0"' in target_package
assert '"lint:gherkin": "gherkin-lint -c .gherkin-lintrc cypress/integration"' in base_package
assert '"lint:gherkin": "gherkin-lint -c .gherkin-lintrc cypress/e2e"' in target_package
assert '"stepDefinitions": "cypress/e2e/common"' in target_package

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

# These four Cypress rows were already reviewed with MGR-043 (or as a trivial
# punctuation-only plugin change). The remaining target subtree is the stable
# 80-row migration/test-inventory cluster handled here.
previously_reviewed = {
    prefix + "e2e/orchestrator/grafana/grafana.feature",
    prefix + "e2e/orchestrator/workflow/01-create-cluster-welcome.feature",
    prefix + "e2e/orchestrator/workflow/02-create-cluster-add-host.feature",
    prefix + "plugins/index.js",
}
cluster = [
    row for row in rows
    if row["path"].startswith(prefix) and row["path"] not in previously_reviewed
]
assert len(cluster) == 80
assert Counter(row["status"] for row in cluster) == {"R": 70, "A": 8, "M": 2}
assert sum(row["status_detail"] == "R100" for row in cluster) == 24
for row in cluster:
    if row["status"] == "R":
        if row["path"] == prefix + "support/e2e.ts":
            assert row["old_path"] == prefix + "support/index.ts"
        else:
            assert row["old_path"].startswith(prefix + "integration/")
            assert row["path"].startswith(prefix + "e2e/")
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect", row["path"]
        assert row["finding_id"] == "MGR-043", row["path"]
    else:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-043"
        row["impact_reason"] = (
            "MGR-043: Cypress 10 changes Dashboard E2E discovery from "
            "cypress/integration to cypress/e2e; this moved/added spec, imported "
            "page object, support file or TypeScript config participates in the "
            "repository acceptance suite and its path/content changes alter the "
            "cases or assertions available when that gate is run. It is not a "
            "production daemon runtime path."
        )

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
unclassified = sum(not row["upgrade_impact"] for row in rows)
assert affect + trivial + unclassified == 726
assert affect >= 212 and trivial >= 152 and unclassified <= 362
print("Classified Cypress E2E migration cluster: 80 affect -> MGR-043")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
