"""Classify inspected orchestrator CLI endpoint changes for owner 07."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
findings = {
    "src/pybind/mgr/orchestrator/_interface.py": (
        "affect", "MGR-036",
        "MGR-036: Orchestrator upgrade_ls interface now forwards show_all_versions "
        "to cephadm; with the default false, candidate versions older than the "
        "active MGR major/minor disappear. The same interface also forwards "
        "maintenance override and set_unmanaged, covered by owner 08."
    ),
    "src/pybind/mgr/orchestrator/module.py": (
        "affect", "MGR-036;MGR-037;MGR-038",
        "MGR-036: orch upgrade ls gains --show-all-versions and forwards it to "
        "cephadm's version filter. MGR-037: _end_positional_ makes only image "
        "positional for orch upgrade start, changing CLI argument metadata for "
        "ceph_version and filters. MGR-038: plain orch host ls uses natural order "
        "and comma-separated labels, orch ps/device ls use natural host/daemon "
        "order, and device unavailable renders No rather than blank. The file "
        "also forwards maintenance override, OSD method, RGW zonegroup, "
        "managed-service and tuned-profile commands, cross-referenced to owner 08."
    ),
    "src/pybind/mgr/orchestrator/tests/test_orchestrator.py": (
        "trivial", "",
        "T07-orchestrator-sort-test: Unit tests assert natural ordering of "
        "orchestrator plain output; they do not run in an upgrade or modify "
        "runtime behavior. Production ordering change is MGR-038."
    ),
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for target, (impact, finding_id, reason) in findings.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = impact
    row["finding_id"] = finding_id
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
