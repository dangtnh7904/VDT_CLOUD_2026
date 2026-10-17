#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 15 validation/residual rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "15-upgrade-validation.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


DEPLOY_OSD = {
    "src/python-common/ceph/deployment/drive_group.py",
    "src/python-common/ceph/deployment/drive_selection/filter.py",
    "src/python-common/ceph/deployment/drive_selection/matchers.py",
    "src/python-common/ceph/deployment/drive_selection/selector.py",
}

EXACT_HARNESS = {
    "qa/.qa",
    "qa/suites/.qa",
    "qa/tasks/ceph.py",
    "qa/tasks/ceph_manager.py",
    "qa/tasks/thrasher.py",
}

DENCODER_QA = {
    "qa/tasks/dencoder.py",
    "qa/workunits/dencoder/test-dencoder.sh",
    "qa/workunits/dencoder/test_readable.py",
}


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if path.startswith("qa/suites/upgrade/quincy-x/filestore-remove-check/"):
        return affect(
            "VALFILE-001, FILESTORE-001",
            "Adds the Quincy-to-Reef negative upgrade case that expects Reef installation to reject a cluster with FileStore OSDs; the suite source exists but no exact-tag run result is present.",
        )
    if path.startswith("qa/suites/upgrade/quincy-x/"):
        return affect(
            "VALDAEMON-001",
            "Defines the Quincy-to-Reef parallel or stress-split daemon upgrade, mixed-version pause/resume, workload, and final-version assertions; selectors use a branch and $sha1 rather than the two audited tags.",
        )
    if path.startswith("qa/suites/upgrade/telemetry-upgrade/quincy-x/"):
        return affect(
            "VALTELEM-001",
            "Defines telemetry opt-in, collection continuity, upgrade, and opt-out coverage for Quincy-to-Reef, but references latest-quincy/$sha1 and supplies no executed result for the audited endpoints.",
        )
    if path in {
        "qa/workunits/test_telemetry_quincy.sh",
        "qa/workunits/test_telemetry_quincy_x.sh",
    }:
        return affect(
            "VALTELEM-001",
            "Implements the before/after telemetry revision and collection assertions invoked by the Quincy-to-Reef validation suites; this is test logic, not proof that the exact tags passed.",
        )
    if (
        path.startswith("qa/suites/upgrade-clients/client-upgrade-quincy-reef/")
        or path.startswith("qa/suites/upgrade-clients/client-upgrade-reef-squid/")
    ):
        return affect(
            "VALCLIENT-001",
            "Moves/repurposes the independent RBD client-upgrade topology from Quincy-to-Reef toward Reef-to-Squid, so the target tree does not retain a complete exact-hop client suite that can be selected unchanged.",
        )
    if path.startswith("qa/distros/supported-container-hosts/"):
        return affect(
            "VALDISTRO-001",
            "Changes the supported container-host matrix consumed by the exact-hop suite, adding CentOS Stream 9/runc and Ubuntu 22.04 coverage selectors.",
        )
    if path in EXACT_HARNESS:
        return affect(
            "VALHARNESS-001",
            "Changes suite discovery or Ceph/thrasher command and lifecycle helpers used by the exact-hop tests; the target harness must be pinned with the suite when reproducing results.",
        )
    if path == "qa/releases/reef.yaml":
        return affect(
            "VALFINAL-001",
            "Adds a post-upgrade fixture that raises require-osd-release and require-min-compat-client to Reef; invoking it is a separate compatibility gate and was not part of an observed exact-hop run.",
        )
    if path in DENCODER_QA:
        return affect(
            "VALDENC-001",
            "Changes cross-version dencoder/readability validation tooling and corpus execution; branch defaults are not exact tag locks and no corpus result is included.",
        )
    if path == "qa/tasks/deduplication.py":
        return affect(
            "RADOSDEDUP-001",
            "Adds a task that exercises sample deduplication and validates chunk references/repair, providing required coverage when that optional feature is deployed.",
        )

    if path.startswith("qa/"):
        return trivial(
            "VAL-OTHER-QA: generic, older/newer-release, Windows, smoke, distro, or component test source outside the selected exact-hop coverage; it was not executed and does not itself alter the production upgrade path.",
        )

    if path == "src/pybind/ceph_argparse.py":
        return affect(
            "OPSCLI-001",
            "Changes address/PG command argument validation, including removal of v1:/v2:/any: stripping in CephIPAddr; automation inputs accepted by Quincy can fail target-side parsing.",
        )
    if path == "src/pybind/ceph_daemon.py":
        return trivial(
            "VAL-TYPING: admin-socket watcher signal annotations are widened only; socket commands and runtime loop are unchanged.",
        )

    if path in DEPLOY_OSD:
        return affect(
            "ADMOSD-001, CVINVENTORY-001",
            "Changes persisted DriveGroup filtering/selection through actuator matching, existing-OSD limit accounting, and service-id comparison; managed OSD dry-run output can differ after MGR failover.",
        )
    if path == "src/python-common/ceph/deployment/translate.py":
        return affect(
            "ADMOSD-001, CVFILESTORE-001, FILESTORE-001",
            "Removes FileStore command rendering and changes raw/LVM crush-device-class command generation used by managed OSD reconcile.",
        )
    if path == "src/python-common/ceph/deployment/hostspec.py":
        return affect(
            "ADMHOST-001, NODEPROXY-001",
            "Adds persisted out-of-band host credentials/validation used by target hardware monitoring; existing host-spec export and access controls must be reviewed before opt-in.",
        )
    if path == "src/python-common/ceph/deployment/service_spec.py":
        return affect(
            "ADMMIG-001, ADMSCHED-001, ADMSVC-001",
            "Changes persisted placement/spec serialization, host-pattern semantics, container argument representation, and existing RGW/NFS/ingress service fields consumed during target reconcile.",
        )
    if path == "src/python-common/ceph/deployment/utils.py":
        return affect(
            "ADMHOST-001",
            "Changes host address validation order for bracketed IPv4 and therefore target-side acceptance of persisted or newly supplied host addresses.",
        )
    if path == "src/python-common/ceph/rgw/rgwam_core.py":
        return affect(
            "ADMMIG-001, ADMSVC-001",
            "Changes secondary-zone endpoint fields, realm-token update, and period-update retry behavior in orchestrated RGW multisite creation.",
        )
    if path == "src/python-common/ceph/utils.py":
        return affect(
            "ADMAGENT-001, NODEPROXY-001",
            "Adds the shared HTTP/TLS request path used by cephadm agent and node-proxy communication, including certificate-verification and timeout behavior.",
        )

    if path.startswith("src/python-common/ceph/tests/") or path == "src/python-common/tox.ini":
        return trivial(
            "VAL-UNIT: Python unit-test or tox-only row; it supports reviewed deployment contracts but is not an executed exact-hop result or production path.",
        )
    if path.startswith("src/test/"):
        return trivial(
            "VAL-UNIT: component/unit/performance test source only; no execution result is present and the row does not alter the production rollout path.",
        )
    if path.startswith("src/tools/ceph-dencoder/"):
        return affect(
            "VALDENC-001",
            "Changes dencoder plugin discovery and the registered message/OSD/RGW type set used to test old encoded objects against target decoders.",
        )
    if path == "src/tools/ceph_dedup_tool.cc":
        return affect(
            "RADOSDEDUP-001",
            "Changes ceph-dedup-tool CLI/defaults and adds daemonized sample deduplication plus snapshot-aware object deduplication; this is conditional on operators using the opt-in dedup feature.",
        )
    if path == "src/tools/crimson/perf_crimson_msgr.cc":
        return trivial(
            "VAL-PERF: deletes a standalone Crimson messenger performance utility, not a production daemon or exact-hop acceptance path.",
        )

    if path == "PendingReleaseNotes" or path.startswith("doc/"):
        return trivial(
            "VAL-DOC: release-note or documentation source only; useful for candidate discovery but not executable compatibility evidence or a rollout control path.",
        )
    if path.startswith("examples/"):
        return trivial(
            "VAL-EXAMPLE: sample code/configuration only; it is not selected by the production upgrade or exact-hop validation suite.",
        )

    raise RuntimeError(f"owner 15 has an unreviewed row: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 529:
        raise RuntimeError(f"owner 15 expected 529 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 15 CSV contains duplicate paths")

    for row in rows:
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = verdict(row)

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=header,
            delimiter=";",
            lineterminator="\r\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
    trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
    print(
        f"Classified owner 15: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
