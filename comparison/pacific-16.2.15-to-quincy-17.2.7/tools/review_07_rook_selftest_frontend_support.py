"""Classify Rook runtime, MGR selftest, frontend style and Jest support rows."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, path: str) -> str:
    return git("show", f"{tag}:{path}").stdout


def target_only(commit: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, "v16.2.15", check=False).returncode != 0
    assert git("merge-base", "--is-ancestor", commit, "v17.2.7", check=False).returncode == 0


rook_module_path = "src/pybind/mgr/rook/module.py"
rook_cluster_path = "src/pybind/mgr/rook/rook_cluster.py"
rook_gitlink_path = "src/pybind/mgr/rook/rook-client-python"
rook_test_path = "src/pybind/mgr/rook/tests/test_placement.py"
selftest_path = "src/pybind/mgr/selftest/module.py"

base_rook_module = show("v16.2.15", rook_module_path)
target_rook_module = show("v17.2.7", rook_module_path)
target_rook_cluster = show("v17.2.7", rook_cluster_path)
assert "drive_group_interval" not in base_rook_module
assert "drive_group_interval" in target_rook_module
assert "default=300.0" in target_rook_module
assert 'self.get_store("drive_group_map")' in target_rook_module
assert 'self.set_store("drive_group_map", json.dumps(json_drive_group_map))' in target_rook_module
assert "self._apply_drivegroups(list(self._drive_group_map.values()))" in target_rook_module
assert "def apply_drivegroups" in target_rook_module
assert "def remove_osds" in target_rook_module
assert "def zap_device" in target_rook_module
assert "def apply_rbd_mirror" in target_rook_module
assert "storage_class" not in base_rook_module
assert "default='local'" in target_rook_module
assert "class DefaultFetcher" in target_rook_cluster
assert "class LSOFetcher" in target_rook_cluster
assert "class PDFetcher" in target_rook_cluster
assert "def get_discovered_devices" in target_rook_cluster
assert "def add_osds" in target_rook_cluster
assert "def remove_osds" in target_rook_cluster
assert "def create_zap_job" in target_rook_cluster
assert 'image="rook/ceph:master"' in target_rook_cluster
assert "def placement_spec_to_node_selector" in target_rook_cluster
assert "def add_host_label" in target_rook_cluster
assert "def remove_host_label" in target_rook_cluster
assert "rgw_realm = zone['metadata']['name']" in base_rook_module
assert "svc = 'rgw.' + zone['metadata']['name']" in target_rook_module
assert "if 'pool' in nfs['spec']['rados']" in target_rook_module
assert "service_type == 'osd' or service_type is None" in target_rook_module
assert "service_type == 'rbd-mirror' or service_type is None" in target_rook_module
for commit in (
    "c1dbce81c0cf2ec2d44b94007208a4930d6329c5",
    "4b9134c355a85075767d83ef7ec4d577c43294a1",
    "cf494274b02bbe6d13d41cae485600c3c0d5b7a1",
    "606b0519043120084dc30e4cc9936fa94fdb0926",
):
    target_only(commit)

base_tree = git("ls-tree", "v16.2.15", rook_gitlink_path).stdout
target_tree = git("ls-tree", "v17.2.7", rook_gitlink_path).stdout
assert "0b46d500a741afabe5c4efd1bb07e6f8903f0ef0" in base_tree
assert "82673cd7c7a3f4919b98706985ff27e57d2c1b94" in target_tree
assert git("cat-file", "-e", "0b46d500a741^{commit}", check=False).returncode != 0
assert git("cat-file", "-e", "82673cd7c7a^{commit}", check=False).returncode != 0
assert "rook-client-python.git" in show("v17.2.7", ".gitmodules")
assert "from .rook_client.ceph import cephcluster as ccl" in target_rook_cluster

target_selftest = show("v17.2.7", selftest_path)
assert "@CLICommand('mgr self-test eval')" in target_selftest
assert "InteractiveInterpreter(dict(mgr=self))" in target_selftest
assert "self.remote(\"influx\", \"self_test\")" in target_selftest
assert "tasks.mgr.test_module_selftest" in show(
    "v17.2.7", "src/pybind/mgr/dashboard/run-backend-api-tests.sh"
)
assert "default='mgr self-test eval'" in show("v17.2.7", "src/pybind/ceph_mgr_repl.py")
target_only("2f1dd0ce9f69fa59075a3f1744819f83a85561a5")

target_jest = show("v17.2.7", "src/pybind/mgr/dashboard/frontend/jest.config.cjs")
target_tsconfig_app = show("v17.2.7", "src/pybind/mgr/dashboard/frontend/tsconfig.app.json")
assert '"**/*.spec.ts"' in target_jest
assert '"src/main.ts"' in target_tsconfig_app
assert '"src/**/*.d.ts"' in target_tsconfig_app

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}

style_prefix = "MGR-FRONTEND-STYLE-SUPPORT-02:"
unit_prefix = "MGR-FRONTEND-UNIT-SUPPORT-03:"
frontend_prefix = "src/pybind/mgr/dashboard/frontend/"
style_paths = {
    row["path"]
    for row in rows
    if row["path"].startswith(frontend_prefix)
    and row["path"].endswith(".scss")
    and (not row["upgrade_impact"] or row["impact_reason"].startswith(style_prefix))
}
unit_paths = {
    row["path"]
    for row in rows
    if row["path"].startswith(frontend_prefix)
    and row["path"].endswith(".spec.ts")
    and (not row["upgrade_impact"] or row["impact_reason"].startswith(unit_prefix))
}
assert len(style_paths) == 32
assert len(unit_paths) == 54
for path in style_paths:
    target = show("v17.2.7", path)
    assert "function " not in target and "@Component" not in target, path
for path in unit_paths:
    target = show("v17.2.7", path)
    assert "describe(" in target or "it(" in target or "TestBed" in target, path

style_reason = (
    style_prefix
    + " Changes only SCSS presentation/layout/accessibility for Dashboard v3, "
    "navigation, tables and Formly/CRUD widgets, including four empty R100 "
    "rename-heuristic markers; it does not change API data, health semantics, "
    "cluster state or a rollout command."
)
unit_reason = (
    unit_prefix
    + " Adds or adjusts Jest component/pipe/service assertions. Target Jest "
    "discovers these files with **/*.spec.ts while the production application "
    "starts from src/main.ts; the tests corroborate already reviewed Dashboard "
    "behavior but are not an upgrade recipe or runtime path."
)

trivial_rows = {path: style_reason for path in style_paths}
trivial_rows.update({path: unit_reason for path in unit_paths})
trivial_rows[rook_test_path] = (
    "MGR-053-SUPPORT: Adds unit coverage for Rook PlacementSpec-to-node-selector "
    "conversion; the general MGR tox configuration excludes the rook tree, and "
    "the test does not mutate Kubernetes or run during cluster upgrade."
)

affect_rows = {
    rook_module_path: (
        "MGR-053;MGR-054",
        "MGR-053: Rook gains storage-class-backed device inventory, persisted "
        "drive groups re-applied every drive_group_interval, and explicit OSD "
        "apply/remove/zap plus rbd-mirror operations. MGR-054: its service "
        "inventory/naming, placement, host-label and NFS/RGW handling also change.",
    ),
    rook_cluster_path: (
        "MGR-053;MGR-054",
        "MGR-053: Adds Kubernetes PV/LSO/physical-device fetchers and CR/job "
        "mutators for OSD create/remove/zap. MGR-054: applies placement/replica "
        "settings and changes Rook filesystem, object-store, NFS, host-label and "
        "service-description behavior.",
    ),
    rook_gitlink_path: (
        "MGR-053;MGR-054",
        "MGR-053/MGR-054: Changes the rook-client-python gitlink consumed by the "
        "Rook CRD runtime from 0b46d500a741 to 82673cd7c7a3. The submodule objects "
        "are absent locally, so its internal schema delta remains unverified and "
        "must be validated with the delivered source/package.",
    ),
    selftest_path: (
        "MGR-039",
        "MGR-039: Refactors the selftest command surface to CLICommand methods, "
        "changes remote-call coverage and adds mgr self-test eval used by "
        "ceph_mgr_repl; Dashboard backend QA explicitly runs module selftest, so "
        "the source validation path and accepted results change.",
    ),
}

assert len(trivial_rows) == 87
assert len(affect_rows) == 4
assert not (set(trivial_rows) & set(affect_rows))
for path, reason in trivial_rows.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial", path
        assert row["finding_id"] == "", path
        assert row["impact_reason"] == reason, path
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = reason

for path, (finding, reason) in affect_rows.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect", path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path
    else:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding
        row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
unclassified = sum(not row["upgrade_impact"] for row in rows)
assert affect >= 229 and trivial >= 296 and unclassified <= 201
print("Classified Rook/selftest/frontend support batch: 4 affect, 87 trivial")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
