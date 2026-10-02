"""Classify inspected MON location and ingress/NFS VIP behavior."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "08-cephadm-orchestrator.csv"
affect = {
    "doc/cephadm/services/mon.rst": ("ADM-013", "Runbook adds MON CRUSH location spec and reapply/redeploy steps for stretch/tiebreaker topology."),
    "src/pybind/mgr/cephadm/services/cephadmservice.py": ("ADM-013", "MonService now sets CRUSH location in daemon config and applies remaining locations through mon set_location; file has additional hunks for later detailed review."),
    "qa/suites/orch/cephadm/workunits/task/test_set_mon_crush_locations.yaml": ("ADM-013", "New workunit applies MON crush_locations and verifies mon dump values, providing explicit validation coverage."),
    "doc/cephadm/services/nfs.rst": ("ADM-014", "Runbook adds NFS VIP binding with keepalive-only ingress and count-one placement constraint."),
    "src/pybind/mgr/cephadm/services/ingress.py": ("ADM-014", "Ingress keepalive-only mode changes daemon selection; VRRP interface/router ID and generated password handling change."),
    "src/pybind/mgr/cephadm/services/nfs.py": ("ADM-014", "Ganesha bind address now selects NFS spec virtual_ip ahead of daemon IP when configured."),
    "src/pybind/mgr/cephadm/templates/services/ingress/keepalived.conf.j2": ("ADM-014", "Keepalived template uses spec-defined VRRP interface/router ID and conditionally omits unicast peers for multicast mode."),
    "qa/suites/orch/cephadm/smoke-roleless/2-services/nfs-keepalive-only.yaml": ("ADM-014", "New smoke recipe deploys NFS with keepalive-only ingress and verifies read/write over VIP."),
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in affect} == set(affect)
for row in rows:
    name = row["path"]
    if name not in affect:
        continue
    assert not row["upgrade_impact"], name
    fid, reason = affect[name]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = fid
    row["impact_reason"] = f"{fid}: {reason}"
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
