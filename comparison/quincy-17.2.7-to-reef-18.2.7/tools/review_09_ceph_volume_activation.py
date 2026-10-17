#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 09 ceph-volume rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "09-ceph-volume-activation.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


PRODUCTION: dict[str, tuple[str, str, str]] = {
    "src/ceph-volume/ceph_volume/__init__.py": affect(
        "CVCRYPT-001",
        "Adds process-wide dmcrypt_no_workqueue state used to select target cryptsetup performance flags during encrypted OSD preparation and activation.",
    ),
    "src/ceph-volume/ceph_volume/activate/main.py": trivial(
        "CV-CODE: help and informational-message capitalization only; activation fallback order and arguments are unchanged in this row."
    ),
    "src/ceph-volume/ceph_volume/api/lvm.py": affect(
        "CVFILESTORE-001",
        "Removes the journal device tag from the LVM creation API as part of deleting ceph-volume FileStore provisioning and activation support.",
    ),
    "src/ceph-volume/ceph_volume/devices/lvm/activate.py": affect(
        "CVFILESTORE-001, CVCRYPT-001",
        "Deletes LVM FileStore activation/autodetection and initializes dm-crypt no-workqueue policy before opening encrypted BlueStore devices.",
    ),
    "src/ceph-volume/ceph_volume/devices/lvm/batch.py": affect(
        "CVFILESTORE-001, CVCRYPT-001",
        "Removes FileStore/journal batch options and layouts, while dm-crypt selection now probes cryptsetup capabilities before encrypted provisioning.",
    ),
    "src/ceph-volume/ceph_volume/devices/lvm/common.py": affect(
        "CVFILESTORE-001, CVCRYPT-001",
        "Removes shared FileStore/journal CLI arguments and changes --dmcrypt into an action that establishes the target cryptsetup workqueue policy.",
    ),
    "src/ceph-volume/ceph_volume/devices/lvm/create.py": affect(
        "CVFILESTORE-001",
        "Removes FileStore as a selectable LVM create objectstore; target defaults and accepts only the BlueStore path.",
    ),
    "src/ceph-volume/ceph_volume/devices/lvm/listing.py": affect(
        "CVLVM-001",
        "Resolves a VG/LV argument by both vg_name and lv_name instead of lv_name alone, changing which tagged OSD volume is listed when names repeat across VGs.",
    ),
    "src/ceph-volume/ceph_volume/devices/lvm/migrate.py": affect(
        "CVMIGRATE-001",
        "After a successful BlueStore DB/WAL migration, returns removed source LVs and invokes ceph-volume zap on them; source-device cleanup and rollback boundaries differ.",
    ),
    "src/ceph-volume/ceph_volume/devices/lvm/prepare.py": affect(
        "CVFILESTORE-001, CVLVM-001",
        "Deletes FileStore prepare/mkfs and permits a disk or partition to back newly created BlueStore DB/WAL LVs; accepted layouts and resulting tags differ.",
    ),
    "src/ceph-volume/ceph_volume/devices/lvm/zap.py": affect(
        "CVFILESTORE-001, CVZAP-001",
        "Drops journal association and changes encrypted-partition holder discovery plus mapper refusal rules; the target zap device set and dm-crypt closure behavior differ.",
    ),
    "src/ceph-volume/ceph_volume/devices/raw/common.py": affect(
        "CVCRYPT-001",
        "Changes raw --dmcrypt parsing to probe cryptsetup and establish the no-workqueue policy before preparing encrypted devices.",
    ),
    "src/ceph-volume/ceph_volume/devices/raw/list.py": affect(
        "CVINVENTORY-001",
        "Filters phantom Atari child partitions using parent BlueStore labels and changes explicit-device enumeration; raw OSD discovery can return a different, safer device set.",
    ),
    "src/ceph-volume/ceph_volume/devices/raw/prepare.py": trivial(
        "CV-CODE: comment-only removal of the obsolete FileStore data/journal wording; executable raw BlueStore prepare behavior is unchanged in this row."
    ),
    "src/ceph-volume/ceph_volume/devices/simple/activate.py": affect(
        "CVFILESTORE-001",
        "Removes legacy simple-scan FileStore detection, required data/journal checks, mounting, and journal linking; old FileStore JSON can no longer be activated.",
    ),
    "src/ceph-volume/ceph_volume/main.py": affect(
        "CVPLUGIN-001",
        "Moves ceph-volume plugin discovery from pkg_resources to importlib.metadata with a fallback, changing extension discovery across Python/package environments.",
    ),
    "src/ceph-volume/ceph_volume/util/arg_validators.py": affect(
        "CVFILESTORE-001, CVCRYPT-001",
        "Removes journal from valid Ceph auxiliary LV types and makes --dmcrypt execute the cryptsetup capability probe during argument parsing.",
    ),
    "src/ceph-volume/ceph_volume/util/device.py": affect(
        "CVINVENTORY-001",
        "Refreshes the full device inventory when a path is absent, changes rejection from all removable devices to USB bus devices, and consumes new parent/actuator metadata; availability decisions differ.",
    ),
    "src/ceph-volume/ceph_volume/util/disk.py": affect(
        "CVINVENTORY-001, CVZAP-001",
        "Reworks sysfs partition/parent discovery, stops globally skipping removable media, adds udev bus and actuator facts, and distinguishes partitions from whole block devices; inventory and zap targeting differ.",
    ),
    "src/ceph-volume/ceph_volume/util/encryption.py": affect(
        "CVCRYPT-001",
        "Parses cryptsetup version and adds no-read/no-write-workqueue flags for eligible non-rotational encrypted devices; activation commands and I/O path differ.",
    ),
    "src/ceph-volume/ceph_volume/util/prepare.py": affect(
        "CVFILESTORE-001",
        "Deletes journal sizing/linking and ceph-osd FileStore mkfs helpers, removing the remaining ceph-volume FileStore preparation path.",
    ),
    "src/ceph-volume/ceph_volume/util/system.py": affect(
        "CVACTIVATE-001",
        "Changes mkdir_p from single-level mkdir to recursive makedirs, allowing activation/preparation directories to be created when parent components are missing.",
    ),
    "src/ceph-volume/setup.py": affect(
        "CVCRYPT-001, CVPKG-001",
        "Adds the packaging Python dependency required by cryptsetup version comparison; a target artifact missing that dependency can fail ceph-volume import or encrypted activation.",
    ),
}


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if "/tests/" in path:
        return trivial(
            "CV-TEST: unit/functional fixture, Vagrant inventory, playbook, or distro-layout edit only; it supports the promoted ceph-volume findings but is not an executed acceptance result."
        )

    try:
        return PRODUCTION[path]
    except KeyError as error:
        raise RuntimeError(f"owner 09 has an unreviewed row: {path!r}") from error


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 215:
        raise RuntimeError(f"owner 09 expected 215 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 09 CSV contains duplicate paths")

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
        f"Classified owner 09: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
