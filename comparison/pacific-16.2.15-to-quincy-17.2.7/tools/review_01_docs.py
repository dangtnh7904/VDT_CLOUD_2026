"""Record reviewed OSD documentation and static study images."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
affect = {
    "doc/man/8/ceph-bluestore-tool.rst": (
        "OSD-026",
        "Tool man page documents -i, qfsck, allocmap and restore_cfb; build gates and executable behavior are cross-checked in BLU-004.",
    ),
    "doc/dev/osd_internals/mclock_wpq_cmp_study.rst": (
        "OSD-027",
        "New development study uses 17.0 pre-release high_client_ops default, whereas v17.2.7 endpoint YAML defaults to balanced; study results are not endpoint upgrade predictions.",
    ),
}
trivial = {
    "doc/dev/crimson/osd.rst": "New Crimson OSD lifecycle diagram describes states but supplies no executable setting or release-specific upgrade procedure.",
    "doc/dev/osd-class-path.rst": "Updates class-load troubleshooting example/path wording; osd_class_dir remedy and runtime behavior remain as before.",
    "doc/dev/osd_internals/async_recovery.rst": "Corrects spelling of threshold only.",
    "doc/dev/osd_internals/erasure_coding/ecbackend.rst": "Editorial grammar/capitalization edits in design notes; no algorithm or instruction change.",
    "doc/dev/osd_internals/log_based_pg.rst": "Corrects up-to-date spelling only.",
    "doc/dev/osd_internals/manifest.rst": "Corrects constituent spelling only.",
    "doc/dev/osd_internals/stale_read.rst": "Development explanation is support material only; no executable upgrade procedure or changed operator action in endpoint hunk.",
    "doc/man/8/ceph-osd.rst": "Only updates documentation URL to https://docs.ceph.com.",
    "doc/man/8/osdmaptool.rst": "Only updates documentation URL to https://docs.ceph.com.",
    "doc/rados/operations/add-or-rm-osds.rst": "Rephrases existing manual add/remove/replace OSD commands and cautions without changing command sequence for this upgrade.",
    "doc/rados/operations/monitoring-osd-pg.rst": "Editorial clarification of in/out/up/down states and links; no new monitoring command or threshold.",
    "doc/rados/troubleshooting/troubleshooting-osd.rst": "Reformats existing diagnostic and noout maintenance commands; per-OSD noout advice already exists in Pacific text.",
    "doc/jaegertracing/osd_jaeger.png": "Static tracer screenshot; executable tracing differences are recorded in OSD-021.",
}
images = [
    "Avg_Client_Latency_Percentiles_HDD_NoWALdB_WPQ_vs_mClock.png",
    "Avg_Client_Latency_Percentiles_HDD_WALdB_WPQ_vs_mClock.png",
    "Avg_Client_Latency_Percentiles_NVMe_SSD_WPQ_vs_mClock.png",
    "Avg_Client_Throughput_HDD_NoWALdB_WPQ_vs_mClock.png",
    "Avg_Client_Throughput_HDD_WALdB_WPQ_vs_mClock.png",
    "Avg_Client_Throughput_NVMe_SSD_WPQ_vs_mClock.png",
    "Avg_Obj_Rec_Throughput_HDD_NoWALdB_WPQ_vs_mClock.png",
    "Avg_Obj_Rec_Throughput_HDD_WALdB_WPQ_vs_mClock.png",
    "Avg_Obj_Rec_Throughput_NVMe_SSD_WPQ_vs_mClock.png",
    "Clat_Latency_Comparison_HDD_NoWALdB_WPQ_vs_mClock.png",
    "Clat_Latency_Comparison_HDD_WALdB_WPQ_vs_mClock.png",
    "Clat_Latency_Comparison_NVMe_SSD_WPQ_vs_mClock.png",
    "Recovery_Rate_Comparison_HDD_NoWALdB_WPQ_vs_mClock.png",
    "Recovery_Rate_Comparison_HDD_WALdB_WPQ_vs_mClock.png",
    "Recovery_Rate_Comparison_NVMe_SSD_WPQ_vs_mClock.png",
]
for name in images:
    trivial[f"doc/images/mclock_wpq_study/{name}"] = (
        "Static chart from the 17.0 development mClock/WPQ study; it does not change Quincy 17.2.7 runtime, config or upgrade procedure. See OSD-027."
    )
all_paths = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["file_type"] == "documentation" and not row["upgrade_impact"]} == all_paths
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"]
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    elif name in trivial:
        assert not row["upgrade_impact"]
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-doc: {trivial[name]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
