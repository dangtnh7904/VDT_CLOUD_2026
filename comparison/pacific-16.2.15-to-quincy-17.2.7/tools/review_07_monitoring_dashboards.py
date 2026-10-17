"""Classify inspected monitoring dashboard null rendering and SNMP schema."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
base = "monitoring/ceph-mixin/"
affect = {
    base + "dashboards/osd.libsonnet": "MGR-023: OSD Grafana panel schema changes missing metric rendering from null as zero to null; gaps are no longer drawn as zero in an imported target dashboard.",
    base + "dashboards/rbd.libsonnet": "MGR-023: RBD Grafana panel schema changes missing metric rendering from null as zero to null; rollout metric gaps display differently.",
    base + "dashboards/rgw.libsonnet": "MGR-023: RGW Grafana panel schemas change missing metric rendering from null as zero to null; rollout metric gaps display differently.",
    base + "dashboards_out/osd-device-details.json": "MGR-023: Generated OSD-device Grafana panels carry nullPointMode=null in six places, matching the changed Jsonnet source.",
    base + "dashboards_out/radosgw-detail.json": "MGR-023: Generated RGW-detail Grafana panels carry nullPointMode=null in three places, matching the changed Jsonnet source.",
    base + "dashboards_out/radosgw-overview.json": "MGR-023: Generated RGW-overview Grafana panels carry nullPointMode=null in ten places, matching the changed Jsonnet source.",
    base + "dashboards_out/rbd-overview.json": "MGR-023: Generated RBD-overview Grafana panels carry nullPointMode=null in three places, matching the changed Jsonnet source.",
}
trivial = {
    base + "tox.ini": "T07-monitoring-doctest: Removes one doctest invocation for tests_dashboards/util.py while retaining behave feature tests; no production metric, alert, or upgrade acceptance recipe executes this tox target.",
    "monitoring/snmp/CEPH-PROMETHEUS-ALERT-MIB.txt": "T07-snmp-schema: Adds an SNMP notification OID schema for optional external Alertmanager gateway integration; no Ceph SNMP agent, automatic installation, active trap sender, or executed upgrade gate is changed by this file alone.",
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
        row["finding_id"] = "MGR-023"
        row["impact_reason"] = affect[name]
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
