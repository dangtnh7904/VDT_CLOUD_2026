"""Verify remaining RGW documentation and legacy/general QA support rows."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


def is_ancestor(commit: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, tag],
        check=False,
    )
    assert result.returncode in (0, 1)
    return result.returncode == 0


commits = {
    "config_confval": "8b16defd4fce54dad599d5f2b3d32d163dcf1e30",
    "civetweb_remove": "46c0292870ce9483ddf15bcaf2dcc9554dfb48a0",
    "multisite_api_name": "53ae4f325560bc961885373d46c57e5050e40c7c",
    "inline_data": "ae1c2689cda6a19b4540fc3e2530f5b364cd7d4f",
    "s3_headers_doc": "ba99aa3a8a8449fd90b45c712aa7c5c714d58d53",
    "rgw_module_qa": "5a41b5c62724b610f47b9bc428d0d8928c58d603",
}
for commit in commits.values():
    assert not is_ancestor(commit, "v16.2.15")
    assert is_ancestor(commit, "v17.2.7")

# The large config-reference diff converts hand-maintained option blocks to
# confval directives and documents options whose runtime rows are reviewed
# separately. It does not itself alter generated defaults or daemon code.
base_config = show("v16.2.15", "doc/radosgw/config-ref.rst")
target_config = show("v17.2.7", "doc/radosgw/config-ref.rst")
assert ".. confval:: rgw_frontends" not in base_config
assert ".. confval:: rgw_frontends" in target_config
for option in (
    "rgw_multipart_min_part_size",
    "rgw_crypt_sse_s3_backend",
    "rgw_scheduler_type",
):
    assert f".. confval:: {option}" in target_config

base_frontends = show("v16.2.15", "doc/radosgw/frontends.rst")
target_frontends = show("v17.2.7", "doc/radosgw/frontends.rst")
assert "Civetweb\n========" in base_frontends
assert "Civetweb\n========" not in target_frontends
assert "Beast\n=====" in base_frontends and "Beast\n=====" in target_frontends

base_multisite = show("v16.2.15", "doc/radosgw/multisite.rst")
target_multisite = show("v17.2.7", "doc/radosgw/multisite.rst")
api_name_command = "radosgw-admin zonegroup modify --api-name=<name> --rgw-zonegroup=<name>"
assert api_name_command not in base_multisite
assert api_name_command in target_multisite

base_placement = show("v16.2.15", "doc/radosgw/placement.rst")
target_placement = show("v17.2.7", "doc/radosgw/placement.rst")
assert '"inline_data": true' not in base_placement
assert '"inline_data": true' in target_placement
assert "--placement-inline-data" in target_placement

base_role = show("v16.2.15", "doc/radosgw/role.rst")
target_role = show("v17.2.7", "doc/radosgw/role.rst")
assert "radosgw-admin role rm --role-name" in base_role
assert "radosgw-admin role delete --role-name" in target_role
assert "radosgw-admin role policy delete" in target_role

base_s3 = show("v16.2.15", "doc/radosgw/s3.rst")
target_s3 = show("v17.2.7", "doc/radosgw/s3.rst")
for header in ("Server", "x-amz-delete-marker", "x-amz-version-id"):
    assert f"**{header}**" in base_s3
    assert f"**{header}**" not in target_s3
assert "**x-amz-id-2**" in base_s3 and "**x-amz-id-2**" in target_s3

# The old teuthology subtree is not an upgrade recipe. The Civetweb-named
# task is renamed to a generic default-frontend task, while two misleadingly
# named FastCGI files only update their external s3tests branch. The new module
# invokes realm bootstrap for cephadm QA but has no old/new binary transition.
for path in (
    "qa/suites/teuthology/rgw/tasks/s3tests-fastcgi.yaml",
    "qa/suites/teuthology/rgw/tasks/s3tests-fcgi.yaml",
):
    base = show("v16.2.15", path)
    target = show("v17.2.7", path)
    assert "force-branch: ceph-pacific" in base
    assert "force-branch: ceph-master" in target
    assert base.replace("force-branch: ceph-pacific", "force-branch: ceph-master") == target

base_civetweb_task = show("v16.2.15", "qa/suites/teuthology/rgw/tasks/s3tests-civetweb.yaml")
target_generic_task = show("v17.2.7", "qa/suites/teuthology/rgw/tasks/s3tests.yaml")
assert "force-branch: ceph-pacific" in base_civetweb_task
assert "force-branch: ceph-master" in target_generic_task
assert "civetweb" not in target_generic_task.lower()
assert "upgrade-task" not in target_generic_task

rgw_module = show("v17.2.7", "qa/tasks/rgw_module.py")
assert "def apply(ctx, config):" in rgw_module
assert "'ceph', 'rgw', 'realm', 'bootstrap'" in rgw_module
assert "upgrade" not in rgw_module.lower()


new_rows = {
    "doc/radosgw/config-ref.rst": (
        "trivial",
        "",
        "RGW-DOC-CONFVAL-01: Reworks the RGW option reference around confval directives and documents target options/defaults; runtime configuration semantics remain owned by their source/config rows and no upgrade procedure is added here.",
    ),
    "doc/radosgw/frontends.rst": (
        "trivial",
        "RGW-004",
        "RGW-004 support: Removes the deprecated Civetweb documentation after that frontend is removed from target code; the document does not independently change listener selection or rollout behavior.",
    ),
    "doc/radosgw/multisite.rst": (
        "trivial",
        "",
        "RGW-MULTISITE-DOC-01: Clarifies zonegroup isolation, config references and single-site-to-multisite api_name setup; it is general topology guidance, not a Pacific-to-Quincy upgrade or rollback recipe.",
    ),
    "doc/radosgw/placement.rst": (
        "trivial",
        "",
        "RGW-PLACEMENT-DOC-01: Documents the explicit inline_data placement option and edits SDK wording; the document itself does not alter placement metadata, object layout or upgrade execution.",
    ),
    "doc/radosgw/role.rst": (
        "trivial",
        "RGW-030",
        "RGW-030 support: Corrects role/policy delete command examples and spelling; it does not implement role metadata synchronization, forwarding or an upgrade validation path.",
    ),
    "doc/radosgw/s3.rst": (
        "trivial",
        "",
        "RGW-S3-DOC-HEADERS-01: Corrects the unsupported-response-header list for behavior already present elsewhere; this documentation-only commit changes no wire response or client acceptance gate.",
    ),
    "qa/suites/teuthology/rgw/tasks/s3tests-fastcgi.yaml": (
        "trivial",
        "CFG-008",
        "CFG-008 support: The legacy Apache/mod_fastcgi task keeps its existing frontend configuration; the only net change selects the ceph-master external s3tests branch and adds no version-upgrade step.",
    ),
    "qa/suites/teuthology/rgw/tasks/s3tests-fcgi.yaml": (
        "trivial",
        "CFG-008",
        "CFG-008 support: The legacy Apache/mod_proxy_fcgi task keeps its existing frontend configuration; only the external test branch changes, without validating a Pacific-to-Quincy transition.",
    ),
    "qa/suites/teuthology/rgw/tasks/s3tests.yaml": (
        "trivial",
        "RGW-004",
        "RGW-004 support: Rename detection maps the old Civetweb-named task to a generic default-frontend s3tests task; it runs one target branch and contains no mixed-version, rollback or upgrade task.",
    ),
    "qa/tasks/rgw_module.py": (
        "trivial",
        "",
        "RGW-RGWAM-QA-01: Adds a cephadm QA helper that applies `ceph rgw realm bootstrap` specs, but no owned suite path here transitions old/new RGW artifacts or changes the upgrade acceptance gate.",
    ),
}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for path, (impact, finding, reason) in new_rows.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified remaining RGW docs/legacy QA cluster: 10 trivial")
