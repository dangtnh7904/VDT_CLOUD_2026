"""Classify inspected non-operational cephadm documentation and mockups."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "08-cephadm-orchestrator.csv"
trivial = {
    "doc/cephadm/services/iscsi.rst": "T08-iscsi-link: Adds client-initiator cross-reference and improves a link label; cephadm iSCSI deployment and upgrade procedure are unchanged.",
    "doc/cephadm/services/mgr.rst": "T08-mgr-prose: Rephrases which modules the MGR hosts; no command, setting or deployment step changes.",
    "doc/dev/cephadm/host-maintenance.rst": "T08-maintenance-markup: Only marks an existing command as inline code; maintenance workflow text is unchanged.",
    "doc/dev/cephadm/index.rst": "T08-dev-toc: Replaces developer-doc toctree entry for exporter design with storage-device design; no operator procedure or executable code.",
    "doc/dev/cephadm/scalability-notes.rst": "T08-scalability-typo: Corrects one spelling error in speculative developer notes.",
    "doc/dev/cephadm/design/mockups/OSD_Creation_device_mode.svg": "T08-design-mockup: Added static SVG design illustration; no executable deployment or validation behavior.",
    "doc/dev/cephadm/design/mockups/OSD_Creation_host_mode.svg": "T08-design-mockup: Added static SVG design illustration; no executable deployment or validation behavior.",
    "doc/dev/cephadm/design/storage_devices_and_osds.rst": "T08-design-notes: Added proposed inventory/OSD workflows in developer design notes, not an operator migration recipe or executable implementation.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in trivial} == set(trivial)
for row in rows:
    if row["path"] not in trivial:
        continue
    assert row["upgrade_impact"] in ("", "trivial"), row["path"]
    assert not row["finding_id"], row["path"]
    row["upgrade_impact"] = "trivial"
    row["impact_reason"] = trivial[row["path"]]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
