"""Classify the remaining owner-01 Crimson and test rows from endpoint diffs."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "01-osd-pg-recovery.csv"
affect = {
    "src/crimson/os/alienstore/alien_collection.h": ("OSD-091", "AlienCollection adds a per-collection mutex used by AlienStore to serialize operations on the same collection across alien workers."),
    "src/crimson/os/alienstore/alien_store.cc": ("OSD-090;OSD-091", "AlienStore now creates a selected ObjectStore backend and changes mount/mkfs error handling; it also routes collection IO to multiple alien workers, guards shutdown, and fixes get_attr lifetime/get_attrs storage."),
    "src/crimson/os/alienstore/alien_store.h": ("OSD-090;OSD-091", "AlienStore interface now accepts the objectstore type, reports stateful mount/mkfs errors, and owns worker-pool and gate state used in runtime IO."),
    "src/crimson/os/alienstore/semaphore.h": ("OSD-091", "New semaphore coordinates per-worker alien thread queues and wakeup/stop behavior for Crimson ObjectStore operations."),
    "src/crimson/os/alienstore/thread_pool.cc": ("OSD-091", "Alien thread pool changes from a single queue to CPU-affined worker queues, altering IO scheduling and shutdown."),
    "src/crimson/os/alienstore/thread_pool.h": ("OSD-091", "ThreadPool API adds shard-targeted submission and worker-count lifecycle used by AlienStore collection IO."),
    "src/crimson/os/futurized_store.cc": ("OSD-090", "Crimson ObjectStore factory now selects cyanstore/seastore explicitly and uses AlienStore fallback for other supported backend types; create is asynchronous."),
    "src/crimson/os/futurized_store.h": ("OSD-090", "FuturizedStore interface changes backend creation to a future and mount/mkfs to stateful errorators, affecting Crimson store activation."),
    "src/crimson/osd/main.cc": ("OSD-092", "Crimson startup now parses environment/CEPH_ARGS, optionally fetches MON config, defaults to one Seastar core, creates store before OSD start, and changes stop/signal lifecycle."),
    "src/crimson/osd/objclass.cc": ("OSD-093", "Crimson object-class helpers implement STAT, GETXATTRS, OMAPCLEAR, OMAPRMKEYS and current version previously stubbed, changing class method results."),
    "src/crimson/osd/osd.cc": ("OSD-092", "Crimson mkfs now writes magic/osd_key/ready metadata, startup picks v2 addresses and changes bind/boot advertisement, with changed logging and shutdown behavior."),
    "src/crimson/osd/osd.h": ("OSD-092", "Crimson OSD fields and API carry externally created store, boot/bind epochs and log client used by changed mkfs/start/boot lifecycle."),
    "src/crimson/osd/osd_operations/compound_peering_request.cc": ("OSD-094", "Crimson compound peering sub-event completion becomes interruptible while buffering recovery messages under the target PeeringState API."),
}
trivial = {
    "qa/suites/rados/thrash/workloads/pool-snaps-few-objects.yaml": "T01-final-qa: Added log-ignorelist is nested under singular top-level `override`; teuthology documents/uses `overrides`, so this hunk is not an effective QA override. Verify merged job config before relying on the filter.",
    "src/test/behave_tests/features/ceph_osd_test.feature": "T01-final-test: New standalone Behave scenario describes lab cephadm OSD creation on Fedora32; endpoint diff contains no suite selector or production code change, and no invocation is established for this upgrade gate.",
    "src/test/cli/osdmaptool/create-print.t": "T01-final-test: CLI transcript expectations follow printed CRUSH weight precision and omission of min/max rule lines; no production executable logic changes in this fixture.",
    "src/test/cli/osdmaptool/create-racks.t": "T01-final-test: Large CLI transcript updates only printed CRUSH weight precision and min/max rule lines; it is expected output, not an OSDMap algorithm change.",
}
selected = set(affect) | set(trivial)
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    path = row["path"]
    if path not in selected:
        continue
    assert not row["upgrade_impact"], path
    if path in affect:
        fid, reason = affect[path]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[path]
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
