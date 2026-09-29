"""Screen MON/CRUSH documentation and standalone QA clusters."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "04-mon-osdmap-crush.csv"
affect = {
    "doc/rados/troubleshooting/troubleshooting-mon.rst": (
        "MON-025",
        "MON store recovery recipe now states --mon-ids must be ordered by monitor IP and documents OSD-based rebuild limitations; this can change a recovery runbook.",
    ),
}
docs_editorial = {
    "doc/dev/mon-bootstrap.rst",
    "doc/dev/mon-on-disk-formats.rst",
    "doc/man/8/ceph-mon.rst",
    "doc/man/8/crushtool.rst",
    "doc/man/8/monmaptool.rst",
    "doc/rados/operations/add-or-rm-mons.rst",
    "doc/rados/operations/change-mon-elections.rst",
    "doc/rados/operations/monitoring.rst",
}
docs_crush = {
    "doc/man/8/crushdiff.rst",
    "doc/rados/operations/crush-map-edits.rst",
    "doc/rados/operations/crush-map.rst",
}
qa_source = {
    "qa/standalone/crush/crush-choose-args.sh",
    "qa/standalone/mon-stretch/mon-stretch-fail-recovery.sh",
    "qa/standalone/mon-stretch/mon-stretch-uneven-crush-weights.sh",
    "qa/standalone/mon/misc.sh",
    "qa/standalone/mon/mon-last-epoch-clean.sh",
    "qa/standalone/mon/osd-crush.sh",
    "qa/standalone/mon/osd-pool-create.sh",
    "qa/tasks/rebuild_mondb.py",
    "qa/workunits/mon/auth_key_rotation.sh",
    "qa/workunits/mon/pool_ops.sh",
    "qa/workunits/mon/rbd_snaps_ops.sh",
    "qa/workunits/mon/test_mon_config_key.py",
    "qa/workunits/mon/test_noautoscale_flag.sh",
    "qa/workunits/rados/test_crushdiff.sh",
}
assert len(docs_editorial) == 8 and len(docs_crush) == 3 and len(qa_source) == 14
all_paths = set(affect) | docs_editorial | docs_crush | qa_source
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in all_paths} == all_paths
for row in rows:
    p = row["path"]
    if p in affect:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "affect"
        fid, reason = affect[p]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = reason
    elif p in docs_editorial:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T04-doc-editorial: reviewed endpoint hunk/commit; copy, markup, URL, prompts or example output changed without changing MON/CRUSH recovery or upgrade command sequence."
    elif p in docs_crush:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T04-doc-crush: documents MON-006/MON-020/MON-022 rule-ID and tool behavior; no independent deployment or acceptance step changed."
    elif p in qa_source:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == "trivial"
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = "T04-qa: standalone/teuthology test changes corroborate MON feature, CRUSH rule, auth rotation, MON log or noautoscale findings; not an identified upgrade execution/acceptance gate."
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
