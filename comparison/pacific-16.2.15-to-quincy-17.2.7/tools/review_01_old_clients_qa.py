"""Screen the relocated old-client RADOS thrash suite as one QA selection cluster."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
prefix = "qa/suites/rados/thrash-old-clients/"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = [row for row in rows if row["path"].startswith(prefix)]
assert len(selected) == 45
assert all(not row["upgrade_impact"] for row in selected)

for row in selected:
    suffix = row["path"][len(prefix) :]
    if suffix.startswith("1-install/"):
        detail = "Old-client install matrix is reachable through the relocated RADOS suite; Pacific install is added and legacy install recipes exclude ceph-volume."
    elif suffix.startswith("thrashers/") or suffix.startswith("backoff/"):
        detail = "Relocated suite selects OSD thrash/backoff variants; thrasher recipes also change POOL_APP_NOT_ENABLED log filtering."
    elif suffix.startswith("workloads/"):
        detail = "Relocated suite selects RADOS/RBD workloads while older client branches exercise the target cluster."
    else:
        detail = "Suite discovery/composition path is relocated from orch/cephadm to rados, including its cluster, distro, messenger, balancer, and shared-config selectors."
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "OSD-075"
    row["impact_reason"] = f"OSD-075 old-client-QA: {detail} Git R100 on markers/symlinks is heuristic, not proof of a logical file move."

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
