#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 13 build/package rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "13-build-packaging-submodules.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


GITLINKS = {
    "src/fmt",
    "src/jaegertracing/opentelemetry-cpp",
    "src/rapidjson",
    "src/rocksdb",
    "src/s3select",
    "src/seastar",
}


TRIVIAL_EXACT: dict[str, str] = {
    "COPYING": "PKG-DOC: license text cleanup only; payload licensing must still be carried by the package metadata.",
    "src/SimpleRADOSStriper.cc": "PKG-LOG: changes error log priority only; striper operations and return codes are unchanged.",
    "src/btrfs_ioc_test.c": "PKG-TEST: deletes a standalone developer test utility, not a daemon/client payload used by the upgrade.",
    "src/ceph-run": "PKG-HARNESS: developer restart wrapper option used by vstart; it is not a production daemon service path.",
    "src/ceph.in": "PKG-HELP: admin-socket help wording only.",
    "src/ckill.sh": "PKG-HARNESS: local developer process cleanup helper only.",
    "src/cstart.sh": "PKG-HARNESS: local Crimson lab bootstrap helper only.",
    "src/mrun": "PKG-HARNESS: local multi-vstart wrapper only.",
    "src/mstart.sh": "PKG-HARNESS: local multi-vstart wrapper only.",
    "src/stop.sh": "PKG-HARNESS: local vstart/cephadm teardown helper only; it is not an installed production stop workflow.",
    "src/vstart.sh": "PKG-HARNESS: local development-cluster topology and defaults only; no runtime acceptance was executed from this row.",
    "src/mypy-constrains.txt": "PKG-LINT: static type-check dependency constraint only.",
    "src/mypy.ini": "PKG-LINT: static type-check configuration only.",
    "src/script/backport-create-issue": "PKG-RELENG: backport issue helper only; it is not shipped in the daemon/client rollout path.",
    "src/script/backport-resolve-issue": "PKG-RELENG: backport issue helper only.",
    "src/script/ceph-backport.sh": "PKG-RELENG: release backport helper only.",
    "src/script/ceph-debug-docker.sh": "PKG-RELENG: developer debug-container helper only.",
    "src/script/cpatch": "PKG-RELENG: developer patch helper only.",
    "src/script/ptl-tool.py": "PKG-RELENG: pull-request testing/release helper only.",
    "src/script/requirements.backport-create-issue.txt": "PKG-RELENG: dependency list for a backport helper only.",
    "mirroring/MIRRORS": "PKG-RELENG: upstream source mirror list cleanup only.",
    "mirroring/mirror-ceph.sh": "PKG-RELENG: upstream source mirror helper cleanup only.",
    "mirroring/test-mirrors.sh": "PKG-RELENG: source-mirror test helper only.",
    "run-make-check.sh": "PKG-CI: local test harness changes; no production payload or executed acceptance result is established by this row.",
}


EXPORTER_FILES = {
    "debian/ceph-exporter.install",
    "systemd/CMakeLists.txt",
    "systemd/ceph-exporter.service.in",
}


BUILD_HELPERS = {
    "Dockerfile.build",
    "do_cmake.sh",
    "do_freebsd.sh",
    "install-deps.sh",
    "make-debs.sh",
    "make-dist",
    "mingw_conf.sh",
    "win32_build.sh",
    "win32_deps_build.sh",
    "src/nasm-wrapper",
    "src/script/build-with-container.py",
    "src/script/buildcontainer-setup.sh",
    "src/script/lib-build.sh",
    "src/script/run-make.sh",
}


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if path in TRIVIAL_EXACT:
        return trivial(TRIVIAL_EXACT[path])

    if (
        path.startswith(".github/")
        or path in {
            ".githubmap",
            ".gitignore",
            ".gitleaks.toml",
            ".mailmap",
            ".organizationmap",
            ".peoplemap",
            ".readthedocs.yml",
        }
    ):
        return trivial(
            "PKG-CI: repository governance, workflow, mapping, secret-scan, or documentation-hosting metadata only; it is not part of the rollout artifact."
        )
    if (
        path.startswith("doc/")
        or path.startswith("src/doc/")
        or path.startswith("README")
        or path.startswith("SubmittingPatches")
        or path in {"ContainerBuild.md", "admin/doc-requirements.txt", "ceph-menv/README"}
    ):
        return trivial(
            "PKG-DOC: documentation or documentation-build dependency only; it does not build, install, or validate the target production artifact."
        )
    if path.startswith("src/test/") or "/tests/CMakeLists.txt" in path:
        return trivial(
            "PKG-TEST: test target registration/linkage only; it is supporting evidence, not a production path or an executed acceptance result."
        )

    if path == ".gitmodules" or path in GITLINKS:
        return affect(
            "SUBMOD-001",
            "Changes the exact bundled dependency set or gitlink pointer used by recursive/offline source builds; artifact provenance cannot be reproduced from the old submodule cache.",
        )

    if path in EXPORTER_FILES:
        return affect(
            "PKGEXP-001, MGRMETRIC-001",
            "Adds the ceph-exporter package/service install path and hardened systemd unit required by the target manager-to-exporter metric handoff.",
        )

    if path == "selinux/ceph.te":
        return affect(
            "PKGSEC-001",
            "Allows Ceph domains to use io_uring when the SELinux interface exists; target services can fail only under enforcing policy if policy and binary features are out of sync.",
        )

    if path == "ceph.spec.in":
        return affect(
            "PKGRPM-001, PKGEXP-001, NODEPROXY-001, EXTBLK-001",
            "Changes RPM build requirements, distro conditionals, default Jaeger/system-Arrow choices, installed utilities/plugins, and adds MIB/node-proxy packaging.",
        )
    if path.startswith("debian/"):
        ids = "PKGDEB-001"
        if "ceph-exporter" in path:
            ids += ", PKGEXP-001, MGRMETRIC-001"
        if path.endswith("ceph-base.install"):
            ids += ", EXTBLK-001"
        return affect(
            ids,
            "Changes Debian package dependencies, ownership, Python requirement generation, maintainer scripts, or installed payload used during package upgrade/restart.",
        )

    if path.startswith("container/"):
        return affect(
            "PKGCONT-001",
            "Adds the target multi-architecture container build/manifest path; image contents and provenance depend on this recipe when it is used for deployment.",
        )
    if path in BUILD_HELPERS:
        return affect(
            "BUILDTOOL-001",
            "Changes source-build, dependency bootstrap, tarball, container, or Windows toolchain behavior; custom artifacts must be rebuilt cleanly with recorded provenance.",
        )

    if path.startswith("cmake/modules/"):
        return affect(
            "BUILDDEP-001",
            "Changes dependency discovery or bundled-build logic, version/components, or system-vs-bundled selection that controls the actual target feature/ABI set.",
        )
    if path == "CMakeLists.txt":
        return affect(
            "BUILDDEP-001, BUILDGRAPH-001",
            "Raises dependency/toolchain expectations and changes defaults including Boost 1.79, required FUSE, Jaeger ON, liburing/PMDK discovery, and all Dashboard languages.",
        )

    if path.startswith("src/ceph-node-proxy/"):
        return affect(
            "NODEPROXY-001",
            "Adds the target hardware-monitoring agent, Redfish client/reporter, packaging metadata, and build target used when node-proxy is deployed.",
        )
    if path.startswith("src/extblkdev/") or path in {
        "src/blk/CMakeLists.txt",
        "src/include/CMakeLists.txt",
    }:
        return affect(
            "EXTBLK-001",
            "Adds and links the external block-device plugin interface and VDO implementation; enabled storage builds gain a new device capability and dependency surface.",
        )
    if path.startswith("src/compressor/"):
        return affect(
            "COMPRESS-001",
            "Changes the production compressor interface/build and QAT zlib session pooling/fallback behavior; accelerated compression requires target hardware/library validation.",
        )
    if path == "src/libcephsqlite.cc":
        return affect(
            "MGRDB-001",
            "Adds synchronized RADOS handle replacement and reconnect-on-blocklist throughout the Ceph SQLite VFS used by manager databases.",
        )
    if path.startswith("src/dokan/"):
        return affect(
            "DOKAN-001",
            "Changes the Windows CephFS Dokan client option/encoding/build and runtime paths; Windows artifacts require rebuild and mount smoke testing.",
        )
    if path.startswith("src/objclass/"):
        return affect(
            "OBJCLASS-001",
            "Changes the public object-class development API and logging implementation; external class plugins must be rebuilt and symbol-checked against target headers/libraries.",
        )
    if path == "src/tracing/librados.tp":
        return affect(
            "TRACE-001, RADOSAPI-001",
            "Changes librados tracepoint schema alongside the new stat2 APIs; tracing consumers must regenerate or validate probes against the target library.",
        )
    if path == "src/ceph_release":
        return affect(
            "BUILDGRAPH-001",
            "Changes the compiled release identity from Quincy 17 to Reef 18; artifact identity must match the endpoint and package/container metadata.",
        )
    if path == "src/cephadm/CMakeLists.txt":
        return affect(
            "PKGCEPHADM-001",
            "Builds cephadm as a generated version-stamped executable and installs that artifact instead of directly packaging the source script.",
        )

    if path == "src/os/CMakeLists.txt":
        return affect(
            "BUILDGRAPH-001, FILESTORE-001",
            "Removes FileStore sources from the production object-store target, making Reef artifacts unable to build that legacy backend.",
        )
    if path == "src/librbd/CMakeLists.txt":
        return affect(
            "BUILDGRAPH-001, RBDAPI-001, RBDCRYPT-001",
            "Ships the target librbd 1.18 implementation, new encryption sources, and PMDK target linkage used by the reviewed RBD client paths.",
        )
    if path == "src/rgw/CMakeLists.txt" or path.startswith(
        "src/rgw/driver/dbstore/"
    ):
        return affect(
            "BUILDGRAPH-001",
            "Changes the production RGW executable/library/source graph, optional backends/frontends, tools, and install targets included in the rollout artifact.",
        )
    if path == "src/tools/rbd_mirror/CMakeLists.txt":
        return affect(
            "BUILDGRAPH-001, RBDMIRROR-001",
            "Changes the rbd-mirror target linkage that delivers the reviewed target replay/metric behavior.",
        )
    if path == "src/tools/rbd_wnbd/CMakeLists.txt":
        return affect(
            "BUILDGRAPH-001, RBDMAP-001",
            "Changes the Windows RBD mapping target dependencies used to deliver WNBD resize and WMI behavior.",
        )

    if path.endswith("CMakeLists.txt") or path == "src/CMakeLists.txt":
        return affect(
            "BUILDGRAPH-001",
            "Changes a production target/source/link/install graph; custom builds can omit or alter target behavior if they reuse Quincy cache/manifests.",
        )

    raise RuntimeError(f"owner 13 has an unreviewed row: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 227:
        raise RuntimeError(f"owner 13 expected 227 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 13 CSV contains duplicate paths")

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
        f"Classified owner 13: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
