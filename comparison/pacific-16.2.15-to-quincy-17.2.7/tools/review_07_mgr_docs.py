"""Classify inspected MGR/monitoring documentation and Dashboard screenshots."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
trivial = {
    "doc/mgr/administrator.rst": "T07-mgr-admin-doc: Clarifies manual keyring path and documents .mgr pool rename already covered by MGR-001; no changed daemon behavior or upgrade recipe execution in this document.",
    "doc/mgr/ceph_api/index.rst": "T07-mgr-api-prompt-doc: Rewrites curl examples as prompt directives and changes Sphinx anchor; API request headers and authentication examples remain the same.",
    "doc/mgr/dashboard.rst": "T07-dashboard-guide: Describes new landing-page cards, toggle, SSO file access and centralized logging setup; documentation only, with no independent runtime or executed upgrade gate.",
    "doc/mgr/diskprediction.rst": "T07-diskprediction-typo: Removes punctuation typo before existing disable-prediction command; command and option value unchanged.",
    "doc/mgr/index.rst": "T07-mgr-index-links: Adds RGW and progress module entries to documentation table of contents; no runtime or upgrade sequence change.",
    "doc/mgr/localpool.rst": "T07-localpool-confval-doc: Replaces prose option list with Sphinx confval directives and preserves the example config values; no module option behavior change in this file.",
    "doc/mgr/modules.rst": "T07-module-developer-guide: Expands custom-module command/debugging examples, including future Reef decorators; developer documentation does not change target MGR command execution or this upgrade's acceptance path.",
    "doc/mgr/nfs.rst": "T07-nfs-guide: Updates create syntax and explains keepalive-only ingress configuration for optional NFS provisioning; documentation does not change an existing NFS service during the version rollout.",
    "doc/mgr/rgw.rst": "T07-rgw-module-guide: Adds documentation for optional RGW multisite bootstrap/zone creation; no RGW provisioning is part of this endpoint upgrade unless separately chosen.",
    "doc/monitoring/index.rst": "T07-monitoring-guide: New generic Ceph exporter/PromQL metric reference and examples; not an executed upgrade validation recipe or metric implementation change.",
}
for name in (
    "capacity-card.png", "cluster-utilization-card.png", "dashboard-landing-page.png",
    "details-card.png", "inventory-card.png", "status-card-open.png",
):
    trivial["doc/mgr/" + name] = (
        "T07-dashboard-screenshot: New PNG screenshot referenced by dashboard.rst for landing-page documentation; image asset has no executable metric, health, or upgrade-gate behavior."
    )
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in trivial} == set(trivial)
for row in rows:
    name = row["path"]
    if name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
