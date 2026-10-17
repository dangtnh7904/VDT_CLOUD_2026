"""Classify the final Dashboard frontend rows for the MGR owner."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"
frontend = "src/pybind/mgr/dashboard/frontend/src/app/"
frontend_src = "src/pybind/mgr/dashboard/frontend/src/"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, relative: str) -> str:
    return git("show", f"{tag}:{frontend}{relative}").stdout


def target_only(commit: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, "v16.2.15", check=False).returncode != 0
    assert git("merge-base", "--is-ancestor", commit, "v17.2.7", check=False).returncode == 0


for commit in (
    "3374c905b278f37425790a3cc81650f1f7c9376e",  # daemon logs/Loki
    "957c9c304bca8ef8416041f96b0e2d5bb0f0a0dc",  # Grafana datasource
    "4d91a3d4936fbe099a82b56426d5d7c18e05d9de",  # CRUSH rule schema
    "ad3b4d3c30009d8bd5bcfa97d5607a1dd759d79b",  # RBD mirroring UI
    "60b12ca22cc7ef2ce0ea7c8f973676dd17502849",  # service running/size
    "0c48ef019c9497edf4367f21f934692be2bd1e08",  # service pagination
    "77bddba9c9b5ce87850defb94beb0f8e0489853d",  # real disabled action
):
    target_only(commit)

base_crush = show("v16.2.15", "shared/models/crush-rule.ts")
target_crush = show("v17.2.7", "shared/models/crush-rule.ts")
for field in ("max_size", "min_size", "ruleset"):
    assert field in base_crush and field not in target_crush
assert "type: number" in target_crush

target_services = show("v17.2.7", "ceph/cluster/services/services.component.html")
assert '[serverSide]="true"' in target_services
assert '[count]="count"' in target_services
assert "value.running == 0 || value.size == 0" in target_services

base_mirroring = show("v16.2.15", "shared/api/rbd-mirroring.service.ts")
target_mirroring = show("v17.2.7", "shared/api/rbd-mirroring.service.ts")
assert "getPeerForPool" not in base_mirroring
assert "getPeerForPool(poolName: string)" in target_mirroring
assert "api/block/mirroring/pool/${poolName}/peer" in target_mirroring

base_navigation = show("v16.2.15", "core/navigation/navigation/navigation.component.html")
target_navigation = show("v17.2.7", "core/navigation/navigation/navigation.component.html")
assert "activeAlerts" in base_navigation
assert "activeCriticalAlerts" in target_navigation
assert "activeWarningAlerts" in target_navigation

base_actions = show("v16.2.15", "shared/datatable/table-actions/table-actions.component.html")
target_actions = show("v17.2.7", "shared/datatable/table-actions/table-actions.component.html")
assert '[disabled]="disableSelectionAction(currentAction)"' not in base_actions
assert '[disabled]="disableSelectionAction(currentAction)"' in target_actions

target_logs = show("v17.2.7", "ceph/cluster/logs/logs.component.ts")
assert "getDaemons('loki')" in target_logs
assert "getDaemons('promtail')" in target_logs
assert "data.length > 0 && data[0].status === 1" in target_logs

target_grafana = show("v17.2.7", "shared/components/grafana/grafana.component.ts")
assert "this.type === 'metrics' ? 'Dashboard1' : 'Loki'" in target_grafana
assert "this.baseUrl.slice(0, -2)" in target_grafana
assert 'this.type === \'metrics\'' in target_grafana

metric_consumers = {
    "ceph/cephfs/cephfs-tabs/cephfs-tabs.component.html",
    "ceph/cluster/hosts/host-details/host-details.component.html",
    "ceph/cluster/osd/osd-details/osd-details.component.html",
    "ceph/cluster/osd/osd-list/osd-list.component.html",
    "ceph/pool/pool-details/pool-details.component.html",
    "ceph/pool/pool-list/pool-list.component.html",
    "ceph/rgw/rgw-daemon-details/rgw-daemon-details.component.html",
    "ceph/rgw/rgw-daemon-list/rgw-daemon-list.component.html",
}
for relative in metric_consumers:
    assert '[type]="\'metrics\'"' in show("v17.2.7", relative), relative

affect_map = {
    "shared/models/crush-rule.ts": (
        "MGR-019",
        "MGR-019: Dashboard CRUSH-rule model removes max_size/min_size/ruleset and adds type, matching the Quincy API-v2 contract used by pool/rule inventory; mixed active MGR versions can therefore expose different JSON shapes.",
    ),
    "ceph/cluster/services/services.component.html": (
        "MGR-017",
        "MGR-017: The services table now uses server-side count/pagination and exposes running/desired size with a zero-instance warning, changing the orchestrator inventory and degraded-service signal used during rollout.",
    ),
    "shared/api/rbd-mirroring.service.ts": (
        "MGR-055",
        "MGR-055: Dashboard adds the pool-wide RBD mirror-peer GET consumed by the Quincy mirroring/snapshot eligibility gates; peer discovery and available actions can differ with the active MGR/API version.",
    ),
    "core/navigation/navigation/navigation.component.html": (
        "MGR-056",
        "MGR-056: The navigation badge switches from aggregate activeAlerts to separate critical/warning counters; those counters are populated from the previous refresh array, so the stop/go alert summary can lag one polling cycle.",
    ),
    "shared/datatable/table-actions/table-actions.component.html": (
        "MGR-058",
        "MGR-058: Table actions now set the native disabled attribute in addition to a CSS class, preventing click/router activation for actions that the selection gate marks disabled across rollout inventory tables.",
    ),
}

observability_paths = {
    "ceph/cluster/logs/logs.component.html",
    "ceph/cluster/logs/logs.component.ts",
    "shared/components/grafana/grafana.component.ts",
    *metric_consumers,
}
observability_reason = (
    "MGR-059: Dashboard adds a daemon-log tab gated by one-shot Loki/Promtail daemon status and changes Grafana URL construction to select Loki for logs versus Dashboard1 for explicit metrics consumers. Missing services, stale status or URL/datasource mismatch can remove rollout logs or performance panels."
)
for relative in observability_paths:
    affect_map[relative] = ("MGR-059", observability_reason)

trivial_admin = {
    "app-routing.module.ts",
    "ceph/cephfs/cephfs-form/cephfs-form.component.ts",
    "ceph/cluster/create-cluster/create-cluster-review.component.html",
    "ceph/cluster/create-cluster/create-cluster-review.component.ts",
    "ceph/cluster/create-cluster/create-cluster.component.html",
    "ceph/cluster/create-cluster/create-cluster.component.ts",
    "ceph/cluster/hosts/host-form/host-form.component.ts",
    "ceph/cluster/osd/osd-devices-selection-groups/osd-devices-selection-groups.component.html",
    "ceph/cluster/osd/osd-devices-selection-modal/osd-devices-selection-modal.component.html",
    "ceph/cluster/osd/osd-form/osd-form.component.html",
    "ceph/cluster/services/service-form/service-form.component.html",
    "ceph/cluster/services/service-form/service-form.component.ts",
    "ceph/nfs/nfs-form-client/nfs-form-client.component.html",
    "ceph/nfs/nfs-form/nfs-form.component.html",
    "ceph/pool/erasure-code-profile-form/erasure-code-profile-form-modal.component.html",
    "ceph/pool/pool-form/pool-form.component.html",
    "ceph/pool/pool-form/pool-form.component.ts",
    "ceph/rgw/rgw-user-details/rgw-user-details.component.html",
    "ceph/rgw/rgw-user-form/rgw-user-form.component.html",
    "ceph/rgw/rgw-user-list/rgw-user-list.component.html",
    "ceph/rgw/rgw-user-tabs/rgw-user-tabs.component.html",
    "ceph/rgw/rgw-user-tabs/rgw-user-tabs.component.ts",
    "core/auth/user-list/user-list.component.html",
    "core/auth/user-list/user-list.component.ts",
    "shared/api/ceph-user.service.ts",
}
trivial_admin_reason = (
    "Endpoint diff belongs to an explicit Dashboard create/edit/detail workflow for cluster, host, OSD, service, NFS, pool, RGW or Ceph users. It is reached only after an administrator opens/submits that workflow; no automatic daemon restart, data conversion or rollout gate is introduced."
)

trivial_presentation = {
    "ceph/cluster/crushmap/crushmap.component.html",
    "ceph/cluster/services/service-daemon-list/service-daemon-list.component.html",
    "ceph/shared/device-list/device-list.component.html",
    "ceph/shared/smart-list/smart-list.component.html",
    "core/context/context.component.html",
    "core/context/context.component.ts",
    "core/error/error.component.ts",
    "core/layouts/workbench-layout/workbench-layout.component.html",
    "core/layouts/workbench-layout/workbench-layout.component.ts",
    "core/navigation/navigation/navigation.component.ts",
    "shared/components/cd-label/color-class-from-text.pipe.ts",
    "shared/components/grafana/grafana.component.html",
    "shared/components/language-selector/language-selector.component.html",
    "shared/datatable/table-key-value/table-key-value.component.html",
}
trivial_presentation_reason = (
    "Endpoint changes are presentation/navigation/accessibility text, classes, titles or wrapper markup only. They do not alter the backing request, daemon state, stored data or the rollout decision signal; Grafana URL/datasource logic is separately classified in MGR-059."
)

trivial_framework = {
    "shared/components/confirmation-modal/confirmation-modal.component.html",
    "shared/components/confirmation-modal/confirmation-modal.component.ts",
    "shared/components/form-button-panel/form-button-panel.component.html",
    "shared/components/form-button-panel/form-button-panel.component.ts",
    "shared/components/modal/modal.component.html",
    "shared/components/select/select.component.html",
    "shared/components/submit-button/submit-button.component.ts",
    "shared/datatable/crud-table/crud-table.component.html",
    "shared/datatable/crud-table/crud-table.component.ts",
    "shared/directives/auth-storage.directive.ts",
    "shared/directives/directives.module.ts",
    "shared/directives/form-loading.directive.ts",
    "shared/models/crud-table-metadata.ts",
    "shared/services/crud-form-adapter.service.ts",
    "shared/services/data-gateway.service.ts",
    "shared/services/task-message.service.ts",
    "shared/shared.module.ts",
}
trivial_framework_reason = (
    "Generic Dashboard CRUD/form/directive plumbing is activated by an explicit page action and only adapts schema, validation, permission display, task messages or module registration. No endpoint evidence connects it to automatic upgrade execution or stop/go collection."
)

trivial_build_test = {
    "polyfills.ts",
    "setupJest.ts",
    "testing/unit-test-helper.ts",
}
trivial_build_test_reason = (
    "Frontend polyfill/Jest or unit-test support only; it does not execute in the deployed Dashboard rollout path or create an independent production compatibility gate."
)

trivial_map = {}
for paths, reason in (
    (trivial_admin, trivial_admin_reason),
    (trivial_presentation, trivial_presentation_reason),
    (trivial_framework, trivial_framework_reason),
):
    for relative in paths:
        trivial_map[frontend + relative] = reason
for relative in trivial_build_test:
    trivial_map[frontend_src + relative] = trivial_build_test_reason

affect_full = {frontend + relative: value for relative, value in affect_map.items()}
assert len(affect_full) == 16
assert len(trivial_map) == 59
assert not (set(affect_full) & set(trivial_map))

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
blank = {row["path"] for row in rows if not row["upgrade_impact"]}
expected = set(affect_full) | set(trivial_map)
assert blank <= expected, (len(blank), blank - expected)
assert all(row["upgrade_impact"] for row in rows if row["path"] not in expected)

for path, (finding_id, reason) in affect_full.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect", path
        assert row["finding_id"] == finding_id, path
        assert row["impact_reason"] == reason, path
    else:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding_id
        row["impact_reason"] = reason

for path, reason in trivial_map.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial", path
        assert row["finding_id"] == "", path
        assert row["impact_reason"] == reason, path
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
unclassified = sum(not row["upgrade_impact"] for row in rows)
assert (affect, trivial, unclassified) == (287, 439, 0)
print("Classified final Dashboard frontend batch: 16 affect, 59 trivial")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
