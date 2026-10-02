"""Classify inspected cephadm tuning, monitoring, exporter and maintenance changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "08-cephadm-orchestrator.csv"
affect = {
    "doc/cephadm/host-management.rst": (
        "ADM-009;ADM-011",
        "Operator instructions add tuned-profile sysctl apply/remove commands and the maintenance override that bypasses safety checks.",
    ),
    "doc/cephadm/services/monitoring.rst": (
        "ADM-010;ADM-012",
        "Monitoring runbook adds optional Loki/Promtail and service discovery guidance plus Grafana anonymous-access spec behavior.",
    ),
    "src/cephadm/cephadm": (
        "ADM-010",
        "Endpoint diff removes cephadm-exporter bootstrap flags and its non-container daemon implementation; this file has additional hunks still requiring detailed review.",
    ),
    "src/pybind/mgr/cephadm/module.py": (
        "ADM-009;ADM-010;ADM-011",
        "Adds tuned-profile API, replaces exporter service registration with Loki/Promtail, and adds explicit maintenance safety override; other hunks remain for detailed review.",
    ),
    "src/pybind/mgr/cephadm/serve.py": (
        "ADM-005;ADM-009",
        "Service apply path gates non-agent specs on fresh agent metadata and invokes tuned-profile reconciliation on hosts; other hunks remain for detailed review.",
    ),
    "src/pybind/mgr/cephadm/tuned_profiles.py": (
        "ADM-009",
        "New reconciler writes/removes cephadm-named files under /etc/sysctl.d and runs sysctl --system on reachable hosts.",
    ),
    "src/pybind/mgr/cephadm/services/exporter.py": (
        "ADM-010",
        "Deletes cephadm-exporter service class and its TLS/token configuration path from the target orchestrator.",
    ),
    "src/pybind/mgr/cephadm/services/monitoring.py": (
        "ADM-010;ADM-012",
        "Adds Loki/Promtail service config and Grafana Loki datasource; Grafana ini rendering now depends on anonymous_access.",
    ),
    "src/pybind/mgr/cephadm/templates/services/grafana/ceph-dashboard.yml.j2": (
        "ADM-010",
        "Grafana datasource provisioning adds Loki target when monitoring stack config is generated.",
    ),
    "src/pybind/mgr/cephadm/templates/services/grafana/grafana.ini.j2": (
        "ADM-012",
        "Grafana anonymous viewer section is conditional on spec option and external snapshots are disabled.",
    ),
    "src/pybind/mgr/cephadm/templates/services/loki.yml.j2": (
        "ADM-010",
        "New Loki service template configures port, local filesystem storage and schema for deployed Loki daemon.",
    ),
    "src/pybind/mgr/cephadm/templates/services/promtail.yml.j2": (
        "ADM-010",
        "New Promtail template sends /var/log/ceph log files to the selected Loki daemon.",
    ),
}
trivial = {
    "doc/dev/cephadm/cephadm-exporter.rst": "T08-exporter-design: Removes developer design notes for the removed exporter; executable removal is classified separately under ADM-010.",
    "src/pybind/mgr/cephadm/tests/test_tuned_profiles.py": "T08-tuned-tests: New unit tests mock file/SSH writes and verify tuned-profile reconciliation; no deployed code or upgrade acceptance selector in this file.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = set(affect) | set(trivial)
assert {r["path"] for r in rows if r["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name in affect:
        ids, reason = affect[name]
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = ids
        row["impact_reason"] = f"{ids}: {reason}"
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["impact_reason"] = trivial[name]
for row in rows:
    if row["path"] == "src/pybind/mgr/cephadm/inventory.py":
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == "ADM-003;ADM-004;ADM-005"
        row["finding_id"] += ";ADM-009"
        row["impact_reason"] += " ADM-009: TunedProfileStore persists profile specs and HostCache tracks last host profile update."
        break
else:
    raise AssertionError("inventory.py row missing")
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
