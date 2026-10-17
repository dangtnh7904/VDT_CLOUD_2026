"""Classify a reviewed Dashboard backend and MGR RGW control-plane batch."""

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


future_import_paths = {
    "src/pybind/mgr/dashboard/grafana.py",
    "src/pybind/mgr/dashboard/plugins/__init__.py",
    "src/pybind/mgr/dashboard/plugins/interfaces.py",
    "src/pybind/mgr/dashboard/plugins/lru_cache.py",
    "src/pybind/mgr/dashboard/rest_client.py",
    "src/pybind/mgr/dashboard/security.py",
    "src/pybind/mgr/dashboard/services/__init__.py",
    "src/pybind/mgr/dashboard/services/access_control.py",
    "src/pybind/mgr/dashboard/services/auth.py",
    "src/pybind/mgr/dashboard/services/cephfs.py",
    "src/pybind/mgr/dashboard/services/iscsi_cli.py",
    "src/pybind/mgr/dashboard/services/iscsi_client.py",
    "src/pybind/mgr/dashboard/services/iscsi_config.py",
    "src/pybind/mgr/dashboard/services/progress.py",
    "src/pybind/mgr/dashboard/tests/helper.py",
    "src/pybind/mgr/dashboard/tests/test_access_control.py",
    "src/pybind/mgr/dashboard/tests/test_api_auditing.py",
    "src/pybind/mgr/dashboard/tests/test_ceph_service.py",
    "src/pybind/mgr/dashboard/tests/test_controllers.py",
    "src/pybind/mgr/dashboard/tests/test_exceptions.py",
    "src/pybind/mgr/dashboard/tests/test_feature_toggles.py",
    "src/pybind/mgr/dashboard/tests/test_home.py",
    "src/pybind/mgr/dashboard/tests/test_notification.py",
    "src/pybind/mgr/dashboard/tests/test_plugin_debug.py",
    "src/pybind/mgr/dashboard/tests/test_rbd_service.py",
    "src/pybind/mgr/dashboard/tests/test_settings.py",
    "src/pybind/mgr/dashboard/tests/test_task.py",
    "src/pybind/mgr/dashboard/tests/test_tools.py",
    "src/pybind/mgr/dashboard/tests/test_versioning.py",
    "src/pybind/mgr/dashboard/tools.py",
}
assert len(future_import_paths) == 30
for path in future_import_paths:
    diff = git("diff", "--unified=0", "v16.2.15..v17.2.7", "--", path).stdout
    changed = [
        line for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert changed == ["-from __future__ import absolute_import"], (path, changed)

module_path = "src/pybind/mgr/dashboard/module.py"
settings_path = "src/pybind/mgr/dashboard/settings.py"
base_module = show("v16.2.15", module_path)
target_module = show("v17.2.7", module_path)
base_settings = show("v16.2.15", settings_path)
target_settings = show("v17.2.7", settings_path)
assert "if Settings.UNSAFE_TLS_v1_2:" in base_module
assert "context.minimum_version = ssl.TLSVersion.TLSv1_2" in base_module
assert "context.minimum_version = ssl.TLSVersion.TLSv1_3" in target_module
assert "Settings.UNSAFE_TLS_v1_2" not in target_module
assert "UNSAFE_TLS_v1_2 = Setting(False, [bool])" in base_settings
assert "UNSAFE_TLS_v1_2" not in target_settings
assert "frontend/dist" in target_module and "../../../../build" in target_module
target_only("f7ce917207726603efe467fd84b7f031962e7398")

sso_path = "src/pybind/mgr/dashboard/services/sso.py"
base_sso = show("v16.2.15", sso_path)
target_sso = show("v17.2.7", sso_path)
assert base_sso.index("if cmd['prefix'] == 'dashboard sso disable':") < base_sso.index(
    "if not python_saml_imported:"
)
assert target_sso.index("if not python_saml_imported:", target_sso.index("def handle_sso_command")) < target_sso.index(
    "if cmd['prefix'] == 'dashboard sso disable':"
)
assert "sp_x_509_cert, err = _try_read_file(sp_x_509_cert_path)" in target_sso
assert "sp_private_key, err = _try_read_file(sp_private_key_path)" in target_sso
target_only("805195b90c322c0a900ec088c34c6811b1a8225d")

rgw_module_path = "src/pybind/mgr/rgw/module.py"
assert git("cat-file", "-e", f"v16.2.15:{rgw_module_path}", check=False).returncode != 0
target_rgw_module = show("v17.2.7", rgw_module_path)
for command in (
    "rgw admin",
    "rgw realm bootstrap",
    "rgw realm zone-creds create",
    "rgw realm zone-creds remove",
    "rgw realm tokens",
    "rgw zone modify",
    "rgw zone create",
    "rgw realm reconcile",
):
    assert f"@CLICommand('{command}'" in target_rgw_module
assert "Cephadm is not available" in target_rgw_module
assert "RGWAM(self.env).realm_bootstrap" in target_rgw_module
assert "RGWAM(self.env).zone_create" in target_rgw_module
target_only("52c5cff6e18cff841219ad02e40c5d8698ea4ad4")
target_only("6f506f186cfaea1c65e1a6e5e929ed2d6474841b")

requirements = {
    "src/pybind/mgr/dashboard/requirements-lint.txt": "jsonschema==4.16.0",
    "src/pybind/mgr/dashboard/requirements-test.txt": "jsonschema==4.16.0",
    "src/pybind/mgr/dashboard/requirements.txt": "jsonpatch",
}
for path, needle in requirements.items():
    assert needle not in show("v16.2.15", path)
    assert needle in show("v17.2.7", path)
assert "natsort" in show("v17.2.7", "src/pybind/mgr/dashboard/requirements.txt")
target_tox = show("v17.2.7", "src/pybind/mgr/dashboard/tox.ini")
assert "openapi-{check, fix, doc}" in target_tox
assert "OPENAPI_FILE=openapi.yaml" in target_tox
assert "check: diff {env:OPENAPI_FILE} {env:OPENAPI_FILE_TMP}" in target_tox
assert "application/vnd.ceph.api.v2.0+json" in show(
    "v17.2.7", "src/pybind/mgr/dashboard/openapi.yaml"
)

base_orchestrator = show("v16.2.15", "src/pybind/mgr/orchestrator/module.py")
target_orchestrator = show("v17.2.7", "src/pybind/mgr/orchestrator/module.py")
target_object_format = show("v17.2.7", "src/pybind/mgr/object_format.py")
for member in ("plain", "json", "json_pretty", "yaml", "xml_pretty", "xml"):
    assert f"    {member} =" in base_orchestrator
    assert f"    {member} =" in target_object_format
assert "from object_format import Format" in target_orchestrator
object_consumers = git(
    "grep", "-l", "from object_format import", "v17.2.7", "--", "src/pybind/mgr"
).stdout.splitlines()
assert object_consumers == ["v17.2.7:src/pybind/mgr/orchestrator/module.py"]

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}

trivial_rows = {
    **{
        path: (
            "MGR-PY3-ABSOLUTE-IMPORT-02: Removes only Python 2's future "
            "absolute_import directive; Python 3 import resolution and endpoint "
            "behavior are unchanged."
        )
        for path in future_import_paths
    },
    "src/pybind/mgr/dashboard/plugins/debug.py": (
        "MGR-PY3-TYPING-01: Removes the fallback for typing.no_type_check and imports "
        "the Python 3 typing symbol directly; supported target Python provides it and "
        "the plugin command/runtime logic is unchanged."
    ),
    "src/pybind/mgr/dashboard/plugins/plugin.py": (
        "MGR-PY3-TYPING-01: Removes the fallback for typing.no_type_check and imports "
        "the Python 3 typing symbol directly; supported target Python provides it and "
        "the plugin command/runtime logic is unchanged."
    ),
    "src/pybind/mgr/dashboard/model/__init__.py": (
        "MGR-PY-PACKAGE-MARKER-01: Adds only an encoding-comment package marker; it "
        "defines no model, command, option, state transition or validation gate."
    ),
    "src/pybind/mgr/dashboard/tests/test_sso.py": (
        "MGR-050-SUPPORT: Extends unit mocks for the SSO command refactor, including "
        "missing-file cases, but does not cover a missing certificate paired with a "
        "valid key and is not itself an executed upgrade step."
    ),
    "src/pybind/mgr/object_format.py": (
        "MGR-OBJECT-FORMAT-SUPPORT-01: Adds a general response-formatting framework, "
        "but the only bundled target consumer imports Format after the same six-value "
        "enum was moved out of orchestrator/module.py; the new decorators have no "
        "bundled endpoint caller in this comparison."
    ),
    "src/pybind/mgr/tests/test_object_format.py": (
        "MGR-OBJECT-FORMAT-SUPPORT-01: Unit-tests the new dormant response-formatting "
        "framework; it is not invoked by the upgrade and its only bundled production "
        "consumer uses the parity Format enum."
    ),
    "src/pybind/mgr/dashboard/tests/__init__.py": (
        "MGR-DASHBOARD-TEST-SUPPORT-02: Refactors controller-test waiting/status helpers "
        "and extends orchestrator mocks; it changes test scaffolding rather than the "
        "Dashboard server path or an identified rollout command."
    ),
    "src/pybind/mgr/dashboard/tests/test_osd.py": (
        "MGR-DASHBOARD-TEST-SUPPORT-02: Adds unit coverage for existing OSD scrub, "
        "create, mark, purge and reweight controller calls; no test is automatically "
        "executed by upgrading a cluster."
    ),
    "src/pybind/mgr/dashboard/tests/test_pool.py": (
        "MGR-DASHBOARD-TEST-SUPPORT-02: Adds mocked pool list/update coverage; it does "
        "not independently change pool state, controller runtime or the upgrade gate."
    ),
}

affect_rows = {
    module_path: (
        "MGR-047;MGR-049",
        "MGR-049: Removes the UNSAFE_TLS_v1_2 branch and always configures TLS 1.3, "
        "so a deployment that explicitly allowed TLS 1.2 can lose Dashboard clients "
        "after the active MGR moves to Quincy. MGR-047: also adds the build-tree "
        "frontend/dist fallback used by source-build validation.",
    ),
    settings_path: (
        "MGR-049",
        "MGR-049: Removes the persisted Dashboard UNSAFE_TLS_v1_2 setting from the "
        "target option schema, eliminating Pacific's opt-in TLS 1.2 compatibility path.",
    ),
    sso_path: (
        "MGR-050",
        "MGR-050: Moves the python3-saml dependency check ahead of disable/status/show "
        "and overwrites the certificate read error with the private-key read result, "
        "changing recovery commands when the dependency is absent and allowing the "
        "missing-cert/valid-key edge to proceed with an empty certificate.",
    ),
    "src/pybind/mgr/dashboard/requirements-lint.txt": (
        "MGR-052",
        "MGR-052: Adds pinned jsonschema to the Dashboard lint environment, changing "
        "dependency resolution for the Quincy validation gate.",
    ),
    "src/pybind/mgr/dashboard/requirements-test.txt": (
        "MGR-052",
        "MGR-052: Adds pinned jsonschema to the Dashboard unit-test environment, "
        "changing dependency resolution and schema checks in the Quincy gate.",
    ),
    "src/pybind/mgr/dashboard/requirements.txt": (
        "MGR-052",
        "MGR-052: Adds natsort and jsonpatch to the common Dashboard tox/backend-test "
        "environment; this changes source-build/API-test prerequisites but is not proof "
        "that a packaged production daemon installs them from this file.",
    ),
    "src/pybind/mgr/dashboard/run-frontend-e2e-tests.sh": (
        "MGR-047",
        "MGR-047: Activates nodeenv from dashboard/frontend/node-env instead of the "
        "Pacific path, so source-tree E2E setup follows the relocated frontend build "
        "and can fail if an existing pipeline still provisions the old location.",
    ),
    "src/pybind/mgr/dashboard/openapi.yaml": (
        "MGR-052",
        "MGR-052: Regenerates the committed OpenAPI snapshot for the changed Quincy "
        "endpoint/version surface; tox openapi-check diffs this file against generated "
        "output, so it is an explicit source-validation artifact rather than runtime "
        "proof that an external client is compatible.",
    ),
    "src/pybind/mgr/dashboard/tests/test_docs.py": (
        "MGR-052",
        "MGR-052: Expands EndpointDoc parsing tests used by the pytest/OpenAPI source "
        "gate; these cases can change gate results but do not run during daemon upgrade.",
    ),
    "src/pybind/mgr/rgw/__init__.py": (
        "MGR-051",
        "MGR-051: Registers the new Quincy mgr/rgw module entry point, making its RGW "
        "multisite administration commands available when the module is enabled.",
    ),
    rgw_module_path: (
        "MGR-051",
        "MGR-051: Adds opt-in MGR commands for radosgw-admin, realm bootstrap/tokens/" 
        "credentials/reconcile and zone create/modify; write commands can persist RGW "
        "multisite metadata and deploy daemons through cephadm, but are not automatic "
        "during upgrade.",
    ),
}

assert len(trivial_rows) == 39
assert len(affect_rows) == 11
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
assert affect >= 225 and trivial >= 209 and unclassified <= 292
print("Classified backend/control-plane batch: 11 affect, 39 trivial")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
