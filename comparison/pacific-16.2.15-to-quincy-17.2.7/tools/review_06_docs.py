"""Record the screened configuration-documentation clusters for owner 06."""

import csv
from pathlib import Path

csv_path = Path(__file__).resolve().parents[1] / "06-config-defaults.csv"
review = {
    "doc/rados/configuration/auth-config-ref.rst": ("trivial", "", "T06-confval: hunk removes hand-written keyring/signature option tables; no command or upgrade procedure changes; runtime auth reviewed in owner 05."),
    "doc/rados/configuration/bluestore-config-ref.rst": ("affect", "CFG-006", "CFG-006: offline ceph-bluestore-tool reshard example changes CF prefix case O/L/P to o/l/p and SPDK path example; if used in recovery, command behavior can differ."),
    "doc/rados/configuration/ceph-conf.rst": ("trivial", "", "T06-editorial: documentation reorganizes config precedence/CLI descriptions; assimilate-conf and mixed-version daemon config-help commands exist in base; no new upgrade step."),
    "doc/rados/configuration/common.rst": ("trivial", "", "T06-heading: only renames deprecated multi-cluster heading; no setting or instruction changes."),
    "doc/rados/configuration/general-config-ref.rst": ("trivial", "", "T06-confval: static option descriptions become confval/describe directives; no executed config value or procedure changes."),
    "doc/rados/configuration/index.rst": ("trivial", "", "T06-toc: drops link to ms-ref page merged into network configuration docs; no runtime or upgrade step change."),
    "doc/rados/configuration/journal-ref.rst": ("trivial", "", "T06-confval: legacy journal option tables become confval directives; no journal migration procedure introduced."),
    "doc/rados/configuration/mclock-config-ref.rst": ("affect", "CFG-007", "CFG-007: target adds actionable profile switching and recovery-limit override steps used to validate/stabilize new mClock default after OSD restart."),
    "doc/rados/configuration/mon-config-ref.rst": ("trivial", "", "T06-confval: MON option tables are replaced by confval directives with editorial prose; no new MON upgrade command in endpoint hunk."),
    "doc/rados/configuration/mon-lookup-dns.rst": ("trivial", "", "T06-confval: anchor and mon_dns_srv_name directive replace static description; no DNS lookup behavior or upgrade instruction change."),
    "doc/rados/configuration/mon-osd-interaction.rst": ("trivial", "", "T06-confval: MON/OSD interaction option tables become confval directives; runtime behavior covered by source rows."),
    "doc/rados/configuration/ms-ref.rst": ("trivial", "", "T06-doc-move: legacy messenger reference page removed and table material moved to network-config-ref; no code or upgrade recipe."),
    "doc/rados/configuration/msgr2.rst": ("trivial", "", "T06-confval: messenger2 page adds compression-mode explanation and option links; no independently executed upgrade step."),
    "doc/rados/configuration/network-config-ref.rst": ("trivial", "", "T06-confval: network/MSGR option tables replaced by confval directives; ms_bind_port_max behavior separately captured by CFG-002."),
    "doc/rados/configuration/osd-config-ref.rst": ("trivial", "", "T06-confval: OSD/recovery/scrub option tables become confval directives plus editorial links; no changed operational command."),
    "doc/rados/configuration/pool-pg-config-ref.rst": ("trivial", "", "T06-confval: pool/PG defaults tables replaced by confval directives and heading anchor; no pool migration recipe change."),
    "doc/rados/configuration/pool-pg.conf": ("trivial", "", "T06-sample-comment: sample comments explain min_size differently and a sample key spelling changes; file is not a deployed config or upgrade script."),
    "doc/rados/configuration/storage-devices.rst": ("trivial", "", "T06-editorial: prose edit removes conflict markers and rewords BlueStore/FileStore overview; no device activation command."),
}
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert sum(row["path"] in review for row in rows) == len(review)
for row in rows:
    if row["path"] in review:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == review[row["path"]][0]
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = review[row["path"]]
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
