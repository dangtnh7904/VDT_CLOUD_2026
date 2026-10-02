"""Classify inspected Dashboard service pagination, alert filtering, and Python-3 cleanup."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
prefix = "src/pybind/mgr/dashboard/"
affect = {
    prefix + "controllers/service.py": ("MGR-017", "Service list API becomes v2 with default limit=5, X-Total-Count and pagination; unmodified API clients can see HTTP 415 or an incomplete service list."),
    prefix + "services/orchestrator.py": ("MGR-017", "Orchestrator service list now returns filtered, sorted, paginated dicts and total count instead of all ServiceDescription objects."),
    prefix + "services/_paginate.py": ("MGR-017", "New ListPaginator implements service-list offset, limit, search and sort used by Dashboard inventory checks."),
    prefix + "frontend/src/app/ceph/cluster/services/services.component.ts": ("MGR-017", "Target Dashboard service table sends pagination parameters and reads total count, changing service inventory displayed after MGR upgrade."),
    prefix + "frontend/src/app/ceph/cluster/services/service-daemon-list/service-daemon-list.component.ts": ("MGR-017", "Target service detail requests limit=-1 explicitly so daemon/service relation view does not inherit default five-service page."),
    prefix + "frontend/src/app/shared/api/ceph-service.service.ts": ("MGR-017", "Target client sends Accept API v2 and wraps service-list response in PaginateObservable rather than treating it as an unversioned full list."),
    prefix + "controllers/prometheus.py": ("MGR-018", "Target returns full non-CephPGImbalance alert objects via filter when balancer is active and has no optimization needed; active-alert display/acceptance differs from base in that condition."),
}
future_only = (
    "auth.py", "cluster_configuration.py", "docs.py", "erasure_code_profile.py",
    "frontend_logging.py", "grafana.py", "home.py", "logs.py", "mgr_modules.py",
    "monitor.py", "nfs.py", "osd.py", "perf_counters.py", "pool.py", "role.py",
    "saml2.py", "summary.py", "task.py", "user.py",
)
trivial = {prefix + "controllers/" + name:
    "T07-dashboard-py3-import: Only removes Python 2 absolute_import future statement; endpoint logic and response remain unchanged under Python 3."
    for name in future_only}
trivial[prefix + "controllers/_paginate.py"] = (
    "T07-empty-marker-rename: Git R100 0/0 pairs an empty Dashboard marker with an unrelated empty QA marker; target file has no contents or pagination implementation."
)
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
