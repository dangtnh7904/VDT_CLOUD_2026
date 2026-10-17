"""Classify RGW multisite QA loader and IAM role sync test changes."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
loader_paths = {
    "qa/tasks/rgw_multisite_tests.py",
    "qa/suites/rgw/multisite/realms/two-zonegroup.yaml",
}
role_paths = {
    "src/test/rgw/rgw_multi/conn.py",
    "src/test/rgw/rgw_multi/multisite.py",
    "src/test/rgw/rgw_multi/tests.py",
    "src/test/rgw/rgw_multi/zone_cloud.py",
    "src/test/rgw/rgw_multi/zone_es.py",
    "src/test/rgw/rgw_multi/zone_rados.py",
    "src/test/rgw/test_multi.py",
}


def show(tag, path):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True, encoding="utf-8")


runner_old = show("v16.2.15", "qa/tasks/rgw_multisite_tests.py")
runner_new = show("v17.2.7", "qa/tasks/rgw_multisite_tests.py")
assert "from tasks.rgw_multi import multisite, tests" in runner_old
assert "from tasks.rgw_multi import multisite, tests" not in runner_new
assert "self.config.get('branch')" in runner_new
assert "self.ctx.config.get('suite_path')" in runner_new
assert "fetch_repo(repo, branch)" in runner_new
assert "workingDir=self.module_path" in runner_new
assert "--caps', 'roles=*'" in runner_new

realm_old = show("v16.2.15", "qa/suites/rgw/multisite/realms/two-zonegroup.yaml")
realm_new = show("v17.2.7", "qa/suites/rgw/multisite/realms/two-zonegroup.yaml")
assert "rgw-multisite-tests:" not in realm_old
assert "rgw-multisite-tests:\n    args: [tests.py]" in realm_new

checks = {
    "src/test/rgw/rgw_multi/conn.py": "def get_gateway_iam_connection(",
    "src/test/rgw/rgw_multi/multisite.py": "self.iam_conn = get_gateway_iam_connection(",
    "src/test/rgw/rgw_multi/tests.py": "def test_role_sync():",
    "src/test/rgw/rgw_multi/zone_cloud.py": "def create_role(self, path, rolename, policy_document, tag_list):",
    "src/test/rgw/rgw_multi/zone_es.py": "def create_role(self, path, rolename, policy_document, tag_list):",
    "src/test/rgw/rgw_multi/zone_rados.py": "def check_role_eq(self, zone_conn, role_name):",
    "src/test/rgw/test_multi.py": "'--caps', 'roles=*'",
}
for path, new_fragment in checks.items():
    assert new_fragment not in show("v16.2.15", path), path
    assert new_fragment in show("v17.2.7", path), path
tests = show("v17.2.7", "src/test/rgw/rgw_multi/tests.py")
assert "zonegroup_meta_checkpoint(zonegroup)" in tests
assert "check_role_eq(source_conn, target_conn, role)" in tests
assert "eq(r1['get_role_response']['get_role_result']['role']['role_id'], r2['get_role_response']['get_role_result']['role']['role_id'])" in show("v17.2.7", "src/test/rgw/rgw_multi/zone_rados.py")

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in loader_paths | role_paths:
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source in loader_paths:
        row.update(
            upgrade_impact="affect", finding_id="RGW-016",
            impact_reason="RGW-016: Multisite QA now imports rgw_multi tests from suite_path or an override branch and runs nose in that directory; two-zonegroup selects tests.py explicitly, changing actual acceptance coverage.")
    else:
        row.update(
            upgrade_impact="affect", finding_id="RGW-017",
            impact_reason="RGW-017: RGW multisite test code adds IAM role creation and cross-zone metadata assertions or grants the test user roles capability; selected test suites can now pass/fail on role sync.")

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(loader_paths)} multisite loader rows and {len(role_paths)} role test rows affect")
