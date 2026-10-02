"""Classify inspected MGR daemon-device metadata and nearby mechanical hunks."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
affect = {
    "src/mgr/DaemonState.cc": "MGR-015: Target DaemonState::set_metadata looks up device_paths by device ID although producer keys paths by device name; by-path attachments can disappear after MGR metadata refresh.",
    "src/mgr/DaemonState.h": "MGR-015: Endpoint base implements device path mapping here while target moves implementation to DaemonState.cc, where changed lookup key affects device attachment metadata.",
}
trivial = {
    "src/mgr/ClusterState.cc": "T07-clusterstate-admin-signature: Adds unused input-buffer parameter and namespace qualifications; dump_osd_network/admin output logic unchanged.",
    "src/mgr/ClusterState.h": "T07-clusterstate-typing: Qualifies map and ostream types only; state representation and admin command behavior unchanged.",
    "src/mgr/DaemonHealthMetricCollector.cc": "T07-healthcollector-namespace: Qualifies standard-library types only; SLOW_OPS relevance and health metrics unchanged.",
    "src/mgr/ServiceMap.cc": "T07-servicemap-namespace: Removes unused includes and qualifies make_pair; service summary grouping keys and output unchanged.",
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
        row["finding_id"] = "MGR-015"
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
