#!/usr/bin/env python3
"""Assign reading ownership to this endpoint inventory; never assign impact."""
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "00-file-inventory.csv"
OWNERS = {
    "01": "01-osd-pg-recovery", "02": "02-bluestore-bluefs",
    "03": "03-rocksdb-block-device", "04": "04-mon-osdmap-crush",
    "05": "05-messaging-auth-common", "06": "06-config-defaults",
    "07": "07-mgr-modules-monitoring", "08": "08-cephadm-orchestrator",
    "09": "09-ceph-volume-activation", "10": "10-rados-rbd-clients",
    "11": "11-cephfs-mds", "12": "12-rgw",
    "13": "13-build-packaging-submodules", "14": "14-security-cross-reference",
    "15": "15-upgrade-validation",
}


def starts(path, *prefixes):
    return any(path.startswith(prefix) for prefix in prefixes)


def owner(path):
    p = path.lower()
    # Build and dependency records own their own delivery or source provenance.
    if p.endswith("cmakelists.txt") or "/cmake/" in p or p.startswith("cmake/"):
        return "13", "build target or dependency"
    if p in {"src/arrow", "src/civetweb", "src/dmclock", "src/fmt", "src/isa-l",
             "src/rocksdb", "src/s3select", "src/seastar", "src/utf8proc",
             "ceph-object-corpus"} or p.startswith("src/jaegertracing/") and p.count("/") <= 2:
        return "13", "gitlink dependency pointer"
    if p.startswith("doc/security/") or p == "security.md":
        return "14", "direct security document"
    if starts(p, "src/cephadm/", "src/pybind/mgr/cephadm/", "qa/suites/orch/",
              "qa/tasks/cephadm", "qa/workunits/cephadm/", "doc/cephadm/", "doc/dev/cephadm/"):
        return "08", "cephadm or orchestrator workflow"
    if starts(p, "src/ceph-volume/", "qa/tasks/ceph_volume", "qa/workunits/ceph-volume"):
        return "09", "ceph-volume discovery and activation"
    if starts(p, "src/pybind/mgr/volumes/", "src/pybind/mgr/nfs/", "src/pybind/mgr/snap_schedule/",
              "src/pybind/mgr/cephfs/", "src/tools/cephfs/", "src/tools/cephfs_mirror/",
              "src/mds/", "src/client/", "src/pybind/cephfs/", "doc/cephfs/",
              "qa/cephfs/", "qa/suites/fs/", "qa/tasks/cephfs/", "qa/workunits/fs/"):
        return "11", "CephFS/MDS owned path"
    if starts(p, "src/rgw/", "src/pybind/rgw/", "src/cls/rgw", "src/cls/2pc_queue/",
              "src/cls/fifo/", "src/cls/queue/", "doc/radosgw/", "qa/rgw/",
              "qa/rgw_frontend/", "qa/suites/rgw/", "qa/suites/rgw-multisite-upgrade/",
              "qa/tasks/rgw", "qa/tasks/radosgw", "qa/tasks/s3tests", "qa/workunits/rgw/"):
        return "12", "RGW owned path"
    if starts(p, "src/librbd/", "src/librados/", "src/libradosstriper/", "src/neorados/",
              "src/rbd_replay/", "src/pybind/rbd/", "src/pybind/rados/", "src/cls/rbd/",
              "src/tools/rbd", "src/tools/rados/", "src/tools/immutable_object_cache/",
              "src/include/rbd/", "src/include/rados/", "src/test/librbd/", "src/test/librados/",
              "src/test/rbd_mirror/", "doc/rbd/", "qa/rbd/", "qa/suites/rbd/",
              "qa/suites/krbd/", "qa/workunits/rbd/"):
        return "10", "RADOS/RBD client owned path"
    if starts(p, "src/pybind/mgr/", "src/mgr/", "src/exporter/", "monitoring/",
              "doc/mgr/", "doc/monitoring/", "qa/tasks/mgr/", "qa/workunits/mgr/"):
        return "07", "MGR, dashboard or monitoring path"
    if starts(p, "src/common/options", "src/common/config", "src/common/legacy_config_opts",
              "src/sample.ceph.conf", "doc/rados/configuration/"):
        return "06", "option or configuration source"
    if starts(p, "src/mon/", "src/crush/", "src/tools/monmaptool", "src/tools/osdmaptool",
              "src/tools/crushtool", "src/tools/crushdiff", "qa/standalone/mon/",
              "qa/standalone/mon-stretch/", "qa/standalone/crush/", "qa/workunits/mon/"):
        return "04", "MON, map or CRUSH path"
    if starts(p, "src/kv/", "src/blk/", "src/key_value_store/", "src/tools/kvstore",
              "src/tools/ceph_kvstore", "src/os/kstore/"):
        return "03", "KV or block-device path"
    if starts(p, "src/os/bluestore/", "src/os/filestore/", "src/os/memstore/",
              "src/test/objectstore/", "src/test/filestore/"):
        return "02", "object-store and replay path"
    if starts(p, "src/osd/", "src/erasure-code/", "src/test/osd/", "src/test/erasure-code/",
              "qa/standalone/osd", "qa/standalone/scrub/", "qa/standalone/erasure-code/",
              "qa/suites/rados/", "qa/suites/big/", "qa/suites/crimson-rados/"):
        if p.startswith("src/osd/osdmap"):
            return "04", "OSDMap state"
        return "01", "OSD, PG, recovery or data-path test"
    if starts(p, "src/crimson/os/seastore/", "src/test/crimson/seastore/"):
        return "02", "Crimson SeaStore persistence"
    if starts(p, "src/crimson/osd/", "src/crimson/os/", "src/crimson/tools/"):
        return "01", "Crimson OSD or object store"
    if starts(p, "src/crimson/net/", "src/crimson/common/", "src/msg/", "src/auth/",
              "src/crypto/", "src/common/", "src/include/", "src/log/", "src/global/"):
        if p.startswith("src/include/cephfs/"):
            return "11", "CephFS wire definitions"
        return "05", "shared wire, auth or runtime path"
    if p.startswith("src/messages/"):
        name = Path(p).name
        if name.startswith(("mclient", "mmds", "mcache", "mdentry", "mdir", "mdiscover", "mexport", "mgather", "mheartbeat", "minode", "mlock")):
            return "11", "MDS/client wire message"
        if name.startswith(("mosd", "mremovesnaps")):
            return "01", "OSD/PG wire message"
        if name.startswith("mmon"):
            return "04", "MON wire message"
        if name.startswith("mmgr"):
            return "07", "MGR wire message"
        return "05", "shared wire message"
    if p.startswith("src/test/"):
        for marker, num in (("rgw", "12"), ("rbd", "10"), ("rados", "10"),
                            ("cephfs", "11"), ("mds", "11"), ("fs/", "11"),
                            ("mon", "04"), ("crush", "04"), ("osd", "01"),
                            ("os/", "02"), ("kv", "03"), ("msgr", "05")):
            if marker in p:
                return num, "component-specific repository test"
        return "15", "cross-component or generic repository test"
    if p.startswith("qa/"):
        if starts(p, "qa/suites/upgrade/", "qa/suites/upgrade-clients/", "qa/suites/smoke/",
                  "qa/distros/", "qa/packages/", "qa/releases/", "qa/tasks/tests/"):
            return "15", "upgrade, distribution or cross-component QA"
        if any(x in p for x in ("cephfs", "kclient", "mds")):
            return "11", "CephFS QA"
        if "rgw" in p or "s3" in p:
            return "12", "RGW QA"
        if "rbd" in p or "iscsi" in p:
            return "10", "RBD QA"
        if "mon" in p or "crush" in p:
            return "04", "MON/CRUSH QA"
        if "osd" in p or "rados" in p or "scrub" in p:
            return "01", "OSD/RADOS QA"
        return "15", "cross-component QA support"
    if p.startswith("doc/"):
        if "blue" in p or "osd" in p or "mclock" in p:
            return "01", "OSD operational documentation"
        if "mon" in p or "crush" in p:
            return "04", "MON or placement documentation"
        if "rbd" in p or "rados/api" in p:
            return "10", "client documentation"
        if "rgw" in p:
            return "12", "RGW documentation"
        if "cephfs" in p or "mds" in p or "nfs" in p:
            return "11", "CephFS documentation"
        if "config" in p:
            return "06", "configuration documentation"
        if "install" in p or "build" in p:
            return "13", "installation or build documentation"
        return "15", "cross-component release or reference documentation"
    if starts(p, "src/tools/ceph_objectstore", "src/tools/ceph_osdomap", "src/tools/erasure-code/"):
        return "01", "OSD maintenance tool"
    if starts(p, "src/tools/ceph_monstore", "src/tools/rebuild_mondb"):
        return "04", "MON maintenance tool"
    if p.startswith("src/tools/"):
        return "15", "cross-component administration tool"
    if starts(p, "src/cls/cephfs/", "src/ceph_fuse", "src/ceph_mds", "src/libcephfs", "src/mount"):
        return "11", "CephFS client or class"
    if starts(p, "src/cls/", "src/osdc/", "src/simple'rados"):
        return "10", "RADOS client or object class"
    if starts(p, "src/ceph_osd", "src/os/", "src/crimson/"):
        return "01", "OSD or object-store runtime"
    if starts(p, "src/ceph_mon", "src/ceph_mgr"):
        return ("04" if "mon" in p else "07"), "daemon entry point"
    if starts(p, "src/pybind/", "src/python-common/"):
        return "15", "cross-component Python binding or support"
    if starts(p, "src/", "cmake/", "debian/", "systemd/", "selinux/", "udev/"):
        return "13", "shared build, packaging or toolchain source"
    if starts(p, "monitoring/"):
        return "07", "monitoring asset"
    if starts(p, "examples/"):
        return "15", "example or validation context"
    if starts(p, ".github/", "admin/", "mirroring/", "man/") or p in {
        ".githubmap", ".gitignore", ".gitmodules", ".mailmap", ".organizationmap",
        ".peoplemap", "cmakelists.txt", "copying", "codingstyle", "readme.md",
        "ceph.spec.in", "do_cmake.sh", "do_freebsd.sh", "install-deps.sh",
        "make-dist", "man", "run-make-check.sh", "win32_deps_build.sh"}:
        return "13", "repository or package infrastructure"
    if p == "pendingreleasenotes":
        return "15", "release-note source claims"
    raise ValueError(f"No owner rule: {path}")


def classify(row):
    p = row["path"]
    group, why = owner(p)
    row["group"] = group
    row["owner_report"] = OWNERS[group]
    is_gitlink = "160000" in (row["old_mode"], row["new_mode"])
    is_test = p.startswith("qa/") or p.startswith("src/test/")
    is_doc = p.startswith("doc/") or p.endswith((".md", ".rst"))
    is_build = group == "13" or p.endswith("CMakeLists.txt")
    if is_gitlink:
        row["file_type"] = "dependency/gitlink"
    elif is_test:
        row["file_type"] = "test/QA"
    elif is_doc:
        row["file_type"] = "documentation"
    elif is_build:
        row["file_type"] = "build/package"
    elif row["binary"] == "TRUE":
        row["file_type"] = "binary/asset"
    elif p.endswith((".json", ".lock", ".po", ".ts")) and "dashboard" in p:
        row["file_type"] = "generated/lock/data"
    else:
        row["file_type"] = "runtime/source"
    row["priority"] = "P2" if is_test or is_doc or row["file_type"] in {"binary/asset", "generated/lock/data"} else "P0" if group in {"01", "02", "04", "05", "11"} and row["file_type"] == "runtime/source" else "P1"
    row["review_mode"] = "support" if is_test or is_doc else "reference-only" if row["file_type"] in {"binary/asset", "generated/lock/data"} else "conditional" if group in {"07", "10", "11", "12"} else "deep"
    row["analysis_decision"] = f"Triage owner {group}: {why}; inspect endpoint hunk before binary impact verdict."


def main():
    with CSV.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = reader.fieldnames
        rows = list(reader)
    assert header and len(header) == 21
    for row in rows:
        classify(row)
    with CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    print(dict(sorted(Counter(row["owner_report"] for row in rows).items())))


if __name__ == "__main__":
    main()
