"""Classify inspected Dashboard v3 widgets and module wiring."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
prefix = "src/pybind/mgr/dashboard/frontend/src/app/"
v3 = prefix + "ceph/dashboard-v3/"
affect = {
    prefix + "ceph/dashboard/dashboard.module.ts": "Imports DashboardV3Module into the existing landing-page module, making the new component available when the feature toggle selects it.",
    v3 + "dashboard-v3.module.ts": "Declares and exports Dashboard v3 widgets and PG summary pipe consumed by the new default landing page.",
    v3 + "card-row/card-row.component.ts": "New inventory card chooses total counts and iSCSI up/down summary for the v3 landing page.",
    v3 + "card-row/card-row.component.html": "New inventory card renders host, MON, MGR, OSD, PG and optional service counts, including up/down/out and warning badges.",
    v3 + "card/card.component.ts": "New card component supplies the v3 status/capacity/inventory wrapper and title.",
    v3 + "card/card.component.html": "New card template displays the v3 summary title and projected card contents.",
    v3 + "dashboard-pie/dashboard-pie.component.ts": "New capacity pie computes used percentage from df totals and colors it at OSD nearfull/full ratios.",
    v3 + "dashboard-pie/dashboard-pie.component.html": "New capacity pie renders the threshold-colored doughnut consumed by the default v3 dashboard.",
    v3 + "dashboard-time-selector/dashboard-time-selector.component.ts": "New selector emits Prometheus query ranges from five minutes to seven days for utilization charts.",
    v3 + "dashboard-time-selector/dashboard-time-selector.component.html": "New selector template sends the chosen time range to Dashboard v3 range queries.",
    v3 + "pg-summary.pipe.ts": "New PG summary groups health statuses by PgCategoryService for the v3 inventory card.",
    v3 + "dashboard-area-chart/dashboard-area-chart.component.html": "New chart template displays the labeled Prometheus series values and graph, including the mislabeled IOPS series.",
}
trivial = {
    prefix + "shared/services/feature-toggles.service.ts": "T07-unused-dashboardV3-type-default: Only adds dashboardV3=true to the TypeScript FeatureTogglesMap class; the HTTP response is a plain object with backend key dashboard, and no code reads the new class property. Runtime toggle selection is covered by MGR-020."
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
        row["finding_id"] = "MGR-020"
        row["impact_reason"] = "MGR-020: " + affect[name]
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
