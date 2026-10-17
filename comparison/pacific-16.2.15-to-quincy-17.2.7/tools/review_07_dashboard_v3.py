"""Classify the inspected Dashboard v3 activation and metric path."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
prefix = "src/pybind/mgr/dashboard/"
frontend = prefix + "frontend/src/app/"
affect = {
    prefix + "plugins/feature_toggles.py": "Adds default-enabled dashboard toggle returned by feature_toggles API; active Quincy MGR selects the new landing page unless the option is disabled.",
    frontend + "ceph/dashboard/dashboard/dashboard.component.html": "Selects Dashboard v3 when dashboard toggle is enabled and the legacy health page when false.",
    frontend + "ceph/dashboard/dashboard/dashboard.component.ts": "Reads feature toggle state to choose the landing page on active MGR.",
    frontend + "ceph/dashboard-v3/dashboard/dashboard-v3.component.html": "New status, capacity and utilization cards include a chart labeled IOPS whose inputs are the OPS/IPS PromQL results.",
    frontend + "ceph/dashboard-v3/dashboard/dashboard-v3.component.ts": "New landing page refreshes health/capacity and sends Prometheus range queries every 30 seconds when configured.",
    frontend + "ceph/dashboard-v3/dashboard-area-chart/dashboard-area-chart.component.ts": "New chart formats the supplied IOPS series as unitless values; it does not convert byte-rate input into operation counts.",
    frontend + "shared/enum/dashboard-promqls.enum.ts": "OPS/IPS PromQL uses ceph_osd_op_r_out_bytes and ceph_osd_op_w_in_bytes rate, so the IOPS chart receives byte rates rather than operation rates.",
    frontend + "shared/api/health.service.ts": "New Dashboard capacity and FSID API calls supply the v3 details and capacity cards.",
    prefix + "controllers/health.py": "Adds API endpoints for cluster capacity and FSID consumed by Dashboard v3.",
    prefix + "services/cluster.py": "Maps mgr df stats into the new Dashboard cluster-capacity response.",
    prefix + "controllers/orchestrator.py": "Adds orchestrator-name endpoint consumed by Dashboard v3 details card.",
    frontend + "shared/api/orchestrator.service.ts": "New getName request supplies Dashboard v3 orchestrator detail.",
    frontend + "shared/api/prometheus.service.ts": "New range-query client and Prometheus setting lookup supply Dashboard v3 utilization cards when Prometheus is configured.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in affect} == set(affect)
prometheus = prefix + "controllers/prometheus.py"
assert sum(row["path"] == prometheus for row in rows) == 1
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-020"
        row["impact_reason"] = "MGR-020: " + affect[name]
    elif name == prometheus:
        assert row["upgrade_impact"] == "affect" and row["finding_id"] == "MGR-018"
        row["finding_id"] = "MGR-018;MGR-020"
        row["impact_reason"] += " MGR-020: Adds /api/prometheus/data proxy to Prometheus /query_range for Dashboard v3 charts."
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
