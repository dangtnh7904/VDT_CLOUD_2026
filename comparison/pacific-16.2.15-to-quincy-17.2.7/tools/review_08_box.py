"""Classify cephadm-box developer sandbox after checking R100 old paths."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "08-cephadm-orchestrator.csv"
box_paths = {
    "src/cephadm/box/Dockerfile",
    "src/cephadm/box/__init__.py",
    "src/cephadm/box/box.py",
    "src/cephadm/box/daemon.json",
    "src/cephadm/box/docker-compose.cgroup1.yml",
    "src/cephadm/box/docker-compose.yml",
    "src/cephadm/box/docker/ceph/.bashrc",
    "src/cephadm/box/docker/ceph/Dockerfile",
    "src/cephadm/box/docker/ceph/locale.conf",
    "src/cephadm/box/host.py",
    "src/cephadm/box/osd.py",
    "src/cephadm/box/util.py",
}
special_old = {
    "src/cephadm/box/__init__.py": "qa/suites/upgrade/nautilus-x/stress-split/4-workload/+",
    "src/cephadm/box/docker/ceph/.bashrc": "qa/suites/upgrade/nautilus-x/stress-split/8-final-workload/+",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in box_paths} == box_paths
for row in rows:
    name = row["path"]
    if name not in box_paths:
        continue
    assert not row["upgrade_impact"], name
    row["upgrade_impact"] = "trivial"
    if name in special_old:
        assert row["status"] == "R" and row["old_path"] == special_old[name], name
        row["impact_reason"] = (
            "T08-box-rename: Git R100 paired two empty files, but the old path is a removed Nautilus-X "
            "upgrade-suite marker and the target is a cephadm-box sandbox file; no logical move or "
            "Pacific-to-Quincy acceptance path."
        )
    else:
        row["impact_reason"] = (
            "T08-box-dev: New cephadm-box Docker Compose sandbox/CLI for local developer clusters; "
            "no imports or deployment link from production cephadm or MGR orchestration."
        )
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
