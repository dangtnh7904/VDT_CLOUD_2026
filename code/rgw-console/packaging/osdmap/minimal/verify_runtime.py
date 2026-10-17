"""Build-time ELF closure/provenance validation, without inventing RPM entries."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

DONOR = "quay.io/ceph/ceph:v16.2.15@sha256:f15b41add2c01a65229b0db515d2dd57925636ea39678ccc682a49e2e9713d98"
BASE = "registry.access.redhat.com/ubi8/ubi-minimal:8.10@sha256:9ba99bcb387bdb7203f6d778a081950832a5fc500824431d10ec9d3ceacf949f"
EXPECTED = {
    "/usr/bin/osdmaptool": ("ceph-base", "c1532cfd43e6a0cfab5c6a3bd3da405ac7224606646f9351fe34bf5fb2ed1fe0"),
    "/usr/bin/crushtool": ("ceph-base", "187ab0d81224f4e692a4376b728a86f380dffa599529bd7b9749389a086952ce"),
    "/usr/lib64/ceph/libceph-common.so.2": ("librados2", "e6a4768ebf2e3836c7d38258840b27620bb0ea6bf1070fe90be635ce899462b9"),
}
OUT = Path("/usr/share/osdmap-preview")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=20,
                          env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "HOME": "/nonexistent"}).stdout


def main():
    copied = []
    for path, (package, expected) in EXPECTED.items():
        observed = sha256(path)
        if observed != expected:
            raise RuntimeError("Copied Ceph file hash does not match the tested donor")
        copied.append({"path": path, "sha256": observed, "donor_package": package,
                       "donor_epoch": "2", "donor_version": "16.2.15", "donor_release": "0.el8",
                       "source_rpm": "ceph-16.2.15-0.el8.src.rpm", "architecture": "x86_64"})
    version = run(["/usr/bin/osdmaptool", "--version"]).strip()
    if version != "ceph version 16.2.15 (618f440892089921c3e944a991122ddc44e60516) pacific (stable)":
        raise RuntimeError("Copied tool reports an untested release or commit")

    # ldd resolves direct and transitive ELF dependencies. These are the tested
    # fixed binaries, not browser uploads or arbitrary caller-supplied paths.
    dependencies = {}
    for executable in EXPECTED:
        output = run(["/usr/bin/ldd", executable])
        if "not found" in output:
            raise RuntimeError("ELF runtime dependency is missing")
        for line in output.splitlines():
            match = re.search(r"(?:=>\s+)?(/[^\s]+)\s+\(", line)
            if not match:
                continue
            resolved = str(Path(match.group(1)).resolve(strict=True))
            if resolved in EXPECTED:
                dependencies[resolved] = {"kind": "COPIED_CEPH", "sha256": sha256(resolved)}
                continue
            owner = run(["/usr/bin/rpm", "-qf", "--qf", "%{NAME}\t%{EPOCHNUM}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\t%{LICENSE}\n", resolved]).strip()
            if not owner or "\n" in owner:
                raise RuntimeError("OS dependency must have one genuine RPM owner")
            name, epoch, ver, release, arch, license_name = owner.split("\t")
            if name.startswith("ceph") or name.startswith("librados"):
                raise RuntimeError("Unexpected donor-package registration in fresh UBI runtime")
            dependencies[resolved] = {"kind": "UBI_RPM", "sha256": sha256(resolved), "name": name,
                                      "epoch": epoch, "version": ver, "release": release,
                                      "architecture": arch, "license": license_name}
    inventory = run(["/usr/bin/rpm", "-qa", "--qf", "%{NAME}\t%{EPOCHNUM}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\n"])
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"kind": "EXTRACTED_CEPH_WITH_UBI_RUNTIME", "approved_for_production": False,
                "donor_image": DONOR, "runtime_base": BASE, "tool_version": version,
                "copied_files": copied, "elf_dependency_closure": dependencies,
                "rpm_inventory": sorted(inventory.splitlines()),
                "limitations": ["Copied Ceph components remain version 16.2.15; newer OS packages do not fix their code.",
                                "Copied Ceph files are not installed RPMs. Scan both the actual image and this explicit component SBOM.",
                                "ELF ldd closure does not prove every optional dynamically loaded backend is exercised."]}
    (OUT / "dependency-closure.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    # An explicit source-component SBOM complements the image's real RPM SBOM.
    # The comment declares a partial extraction; this is not a forged RPM DB.
    files, packages, relationships = [], [], []
    for index, entry in enumerate(copied):
        file_id = "SPDXRef-CephFile{}".format(index)
        package_id = "SPDXRef-CephBaseExtracted" if entry["donor_package"] == "ceph-base" else "SPDXRef-LibradosExtracted"
        files.append({"SPDXID": file_id, "fileName": entry["path"], "checksums": [{"algorithm": "SHA256", "checksumValue": entry["sha256"]}],
                      "licenseConcluded": "NOASSERTION", "copyrightText": "NOASSERTION"})
        relationships.append({"spdxElementId": package_id, "relationshipType": "CONTAINS", "relatedSpdxElement": file_id})
    for name, identifier in (("ceph-base", "SPDXRef-CephBaseExtracted"), ("librados2", "SPDXRef-LibradosExtracted")):
        packages.append({"SPDXID": identifier, "name": name, "versionInfo": "16.2.15-0.el8", "filesAnalyzed": False,
                         "downloadLocation": "https://download.ceph.com/rpm-16.2.15/el8/x86_64/",
                         "sourceInfo": "Selected ELF files extracted unchanged from " + DONOR + "; original source RPM ceph-16.2.15-0.el8.src.rpm",
                         "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION", "copyrightText": "NOASSERTION",
                         "comment": "Partial file extraction, not an installed RPM. See dependency-closure.json and /usr/share/licenses/copied-ceph.",
                         "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                                           "referenceLocator": "pkg:rpm/centos/{}@16.2.15-0.el8?arch=x86_64&epoch=2".format(name)},
                                          {"referenceCategory": "SECURITY", "referenceType": "cpe23Type",
                                           "referenceLocator": "cpe:2.3:a:ceph:ceph:16.2.15:*:*:*:*:*:*:*"}]})
        relationships.append({"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": identifier})
    sbom = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": "Copied Ceph 16.2.15 offline tool components",
            "documentNamespace": "https://storage-lab-console.invalid/spdx/copied-ceph-16.2.15-" + EXPECTED["/usr/bin/osdmaptool"][1],
            "creationInfo": {"creators": ["Tool: storage-lab-osdmap-minimal-build"], "created": "2026-10-12T00:00:00Z"},
            "packages": packages, "files": files, "relationships": relationships,
            "comment": "Complementary extracted-file inventory only. The full image scan must also retain the actual UBI RPM package inventory."}
    (OUT / "copied-ceph.spdx.json").write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"copied_elf_files_verified": len(copied), "closure_entries": len(dependencies),
                      "runtime_rpm_count": len(inventory.splitlines()), "production_approved": False}))


if __name__ == "__main__":
    main()
