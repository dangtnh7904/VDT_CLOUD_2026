"""Classify target MGR tox dependency and test-discovery changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
reasons = {
    "src/pybind/mgr/requirements-required.txt": (
        "MGR-032: New tox minimal-dependency set excludes optional asyncssh and "
        "Kubernetes packages for the nooptional cephadm SSH test profile; it also "
        "pins prettytable below 3.4.0 for Python 3.6 compatibility."
    ),
    "src/pybind/mgr/requirements.txt": (
        "MGR-032: Tox full dependency set now includes the required subset, pins "
        "asyncssh 2.9, Kubernetes 11.0.0, urllib3 1.26.15, and drops remoto/" 
        "execnet; these are test-environment requirements here, not proof of a "
        "production package change."
    ),
    "src/pybind/mgr/tox.ini": (
        "MGR-032: Default MGR tox envs and pytest discovery change; a nooptional "
        "profile tests cephadm SSH without optional dependencies, while the general "
        "testenv runs pytest discovery excluding dashboard and rook trees. A source "
        "build or upgrade test gate using tox can therefore exercise different tests."
    ),
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
for target, reason in reasons.items():
    matching = [row for row in rows if row["path"] == target]
    assert len(matching) == 1, target
    row = matching[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "MGR-032"
    row["impact_reason"] = reason
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
