"""Classify the last owner-08 rows after endpoint hunk inspection."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "08-cephadm-orchestrator.csv"
affect = {
    "doc/cephadm/install.rst": ("ADM-020", "Bootstrap package example changes from the Pacific release RPM to a release-substituted RPM and states an SSH prerequisite; affects target-host preparation guidance."),
    "doc/cephadm/operations.rst": ("ADM-020", "Runbook adds daemon control, redeploy/reconfig and rotate-key commands; logging guidance switches from stderr to journald, and destructive purge preparation changes from orch pause to disabling the cephadm module."),
    "doc/cephadm/services/index.rst": ("ADM-021", "Runbook adds set-unmanaged/set-managed commands and the special unmanaged osd-service caveat; affects operator reconciliation procedure."),
    "doc/cephadm/services/osd.rst": ("ADM-022", "OSD DriveGroup paths recipe adds per-device crush_device_class syntax; affects class assignment when creating replacement or new OSDs using this spec."),
    "doc/cephadm/services/rgw.rst": ("ADM-014;ADM-023", "RGW multisite recipe adds zonegroup and removes --default from realm/zone creation examples; ingress recipe documents multicast, VRRP network and virtual router ID options."),
    "src/cephadm/containers/keepalived/Dockerfile": ("ADM-024", "New Ceph keepalived image build uses UBI8 minimal with keepalived 2.1.5; image provenance matters if this build artifact is deployed for ingress."),
    "src/cephadm/containers/keepalived/skel/init.sh": ("ADM-024", "New keepalived image entrypoint starts the daemon with supplied config and debug option; affects ingress runtime when built image is deployed."),
    "src/cephadm/tox.ini": ("ADM-025", "Mypy tox environment changes from direct mypy 0.790 pin to repository constraint file; alters cephadm validation dependency resolution when that tox gate is run."),
    "src/pybind/mgr/cephadm/remotes.py": ("ADM-007", "Old remoto remote helper is deleted as mgr cephadm uses the asyncssh transport; old write-file and Python selection path is unavailable after target MGR activation."),
    "src/pybind/mgr/cephadm/utils.py": ("ADM-010", "Loki and Promtail join MONITORING_STACK_TYPES, which is included in CEPH_UPGRADE_ORDER and monitoring service handling."),
}
rook_reasons = {
    "0-distro/ubuntu_18.04.yaml": "Ubuntu 18.04 selector is removed from Rook smoke matrix.",
    "0-nvme-loop.yaml": "NVMe loop override selector is added to Rook smoke matrix.",
    "1-rook.yaml": "Rook smoke now asserts ceph orch device ls during setup.",
    "2-workload/radosbench.yaml": "Rook smoke workload now checks host-label add/list/remove operations.",
    "3-final.yaml": "Rook smoke final phase now removes and zaps an OSD, reapplies OSDs, waits for count recovery and applies RGW/MDS/RBD-mirror/NFS services.",
    "cluster/1-node.yaml": "One-node Rook topology sets OSD CRUSH chooseleaf type to zero, changing test topology defaults.",
    "net/flannel.yaml": "New Rook smoke network selector tests flannel pod networking.",
    "net/host.yaml": "New Rook smoke network selector tests host networking and MON placement.",
    "rook/1.6.2.yaml": "Rook 1.6.2 image/branch selector is removed from smoke matrix.",
    "rook/1.7.2.yaml": "Rook 1.7.2 image/branch selector is added to smoke matrix.",
}
affect.update({"qa/suites/orch/rook/smoke/" + suffix: ("ADM-019", reason)
               for suffix, reason in rook_reasons.items()})
trivial = {
    "doc/cephadm/services/mds.rst": "T08-mds-examples: Adds placement examples for existing MDS service syntax; no changed upgrade command, default or implementation is established by this document hunk.",
    "doc/dev/cephadm/developing-cephadm.rst": "T08-developer-guide: Rewords and extends developer kcli/DiD sandbox instructions; no cluster upgrade runbook or production implementation is changed by this document hunk.",
    "src/cephadm/containers/keepalived/LICENSE": "T08-keepalived-license: Adds license text only; no container command or upgrade decision.",
    "src/cephadm/containers/keepalived/README.md": "T08-keepalived-readme: Bundled upstream image usage documentation; actual build and entrypoint impact is recorded under ADM-024.",
    "src/cephadm/tests/fixtures.py": "T08-cephadm-test-fixtures: Unit-test fixture and exporter mock changes; production behavior is covered by implementation findings.",
    "src/cephadm/tests/test_cephadm.py": "T08-cephadm-unit-tests: Unit regression assertions change for existing implementation findings; this file does not select upgrade acceptance jobs or run in deployed clusters.",
    "src/pybind/mgr/cephadm/tests/fixtures.py": "T08-mgr-test-fixtures: Mock/agent fixture changes for unit tests only; no deployed orchestration path is changed.",
    "src/pybind/mgr/cephadm/tests/test_cephadm.py": "T08-mgr-unit-tests: Adds regression assertions for device cache, maintenance and tuned profiles; behavior impact is recorded on implementation rows.",
    "src/pybind/mgr/cephadm/tests/test_services.py": "T08-service-unit-tests: Adds mocked monitoring, MON and NFS service checks; no independent runtime or suite selector change.",
    "src/pybind/mgr/cephadm/tests/test_spec.py": "T08-spec-unit-tests: Updates spec serialization regression cases including exporter/anonymous access; no independent upgrade path.",
    "src/pybind/mgr/cephadm/tests/test_upgrade.py": "T08-upgrade-unit-tests: Adds mocked upgrade-list, resume and offline-host coverage; actual upgrade control-flow impact is recorded on implementation rows.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
blank = {r["path"] for r in rows if not r["upgrade_impact"]}
assert blank == set(affect) | set(trivial), (sorted(blank - (set(affect) | set(trivial))), sorted((set(affect) | set(trivial)) - blank))
for row in rows:
    name = row["path"]
    if name in affect:
        ids, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = ids
        row["impact_reason"] = f"{ids}: {reason}"
    elif name in trivial:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
