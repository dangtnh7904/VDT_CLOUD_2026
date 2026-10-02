"""Record screened RADOS task/workunit changes and narrow test-only exclusions."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
affect = {
    "qa/tasks/rados.py": ("OSD-054", "RADOS QA task forwards dedup chunk size/algorithm and new set-chunk/tier op weights into ceph_test_rados, activating the dedup matrix described in OSD-054."),
    "qa/tasks/radosbench.py": ("OSD-079", "Radosbench task defaults to every client role instead of client.0; selected QA can run more concurrent clients and change load/pass-fail."),
    "qa/tasks/scrub_test.py": ("OSD-080", "Scrub corruption QA resolves rbd pool ID and chooses a PG only from that pool; Pacific could select a populated PG from another pool."),
    "qa/workunits/rados/test.sh": ("OSD-062", "RADOS API workunit adds api_cls_remote_reads to its executed tests, extending object-class validation when the workunit runs."),
    "qa/workunits/rados/test_dedup_tool.sh": ("OSD-081", "Dedup tool workunit changes estimate assertions and adds chunk-scrub, chunk-repair and object-dedup cases, changing lab validation coverage."),
}
trivial = {
    "qa/workunits/rados/test_envlibrados_for_rocksdb.sh": "Test-only prerequisite install script adds SoftIron to Debian-like distro case and removes a CentOS PowerTools repo enable step; no Ceph endpoint runtime or selected upgrade path is established.",
    "qa/workunits/rados/test_librados_build.sh": "Test-only librados build prerequisite adds SoftIron to Debian-like package branch; no Ceph endpoint runtime or selected upgrade path is established.",
    "src/test/osdc/object_cacher_stress.cc": "Object cacher stress-test main adapts to argv_to_vec return API and nullptr spelling; same arguments and correctness workload remain.",
}
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
selected = set(affect) | set(trivial)
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    path = row["path"]
    if path in selected:
        assert not row["upgrade_impact"], path
        if path in affect:
            finding_id, reason = affect[path]
            row["upgrade_impact"] = "affect"
            row["finding_id"] = finding_id
            row["impact_reason"] = f"{finding_id}: {reason}"
        else:
            row["upgrade_impact"] = "trivial"
            row["finding_id"] = ""
            row["impact_reason"] = f"T01-rados-workunits: {trivial[path]}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
