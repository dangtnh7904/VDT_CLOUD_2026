#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 07 MGR/modules/monitoring rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "07-mgr-modules-monitoring.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


AFFECT_EXACT: dict[str, tuple[str, str, str]] = {
    "monitoring/ceph-mixin/alerts.jsonnet": affect(
        "MGRMON-001",
        "Changes the source definitions used to generate target monitoring alerts; alert identity and stop/go signal behavior can differ after monitoring assets are redeployed.",
    ),
    "monitoring/ceph-mixin/config.libsonnet": affect(
        "MGRMON-001",
        "Adds and changes alert thresholds consumed by generated monitoring rules; the target firing set differs for deployments using the bundled mixin.",
    ),
    "monitoring/ceph-mixin/prometheus_alerts.libsonnet": affect(
        "MGRMON-001",
        "Changes existing alert expressions and adds hardware/RBD/NVMe-oF rules in the canonical mixin source; maintenance stop/go signals can differ.",
    ),
    "monitoring/ceph-mixin/prometheus_alerts.yml": affect(
        "MGRMON-001",
        "Changes the deployable Prometheus alert rules, including existing pool-growth matching and new health signals; alert firing behavior differs after rollout.",
    ),
    "monitoring/snmp/CEPH-MIB.txt": affect(
        "MGRMON-001",
        "Extends the Ceph SNMP notification OID contract used by alert receivers; imported MIB and trap decoding must match the target rules.",
    ),
    "monitoring/snmp/CEPH-PROMETHEUS-ALERT-MIB.txt": affect(
        "MGRMON-001",
        "Deletes the legacy Prometheus alert MIB, changing the packaged SNMP decoder contract for deployments that still import it.",
    ),
    "src/mgr/ActivePyModules.cc": affect(
        "MGRCORE-001, MGRDB-001",
        "Copies config before Python formatting to avoid a GIL/config-lock deadlock and changes named client registration used by libcephsqlite reconnects.",
    ),
    "src/mgr/ActivePyModules.h": affect(
        "MGRDB-001",
        "Carries the replace-aware manager client-registration contract used when libcephsqlite reconnects after manager failover or database recovery.",
    ),
    "src/mgr/BaseMgrModule.cc": affect(
        "MGRDB-001, MGRCORE-001",
        "Changes Python completion error propagation and exposes named/replace-aware client registration required by the target manager database recovery path.",
    ),
    "src/mgr/DaemonServer.cc": affect(
        "MGRCORE-001, MGRMETRIC-001",
        "Changes daemon report/auth handling, removes the pre-Mimic scrub fallback, and resolves RGW daemon identity differently for performance queries.",
    ),
    "src/mgr/Mgr.cc": affect(
        "MGRCORE-001, MGRDB-001, MGRMETRIC-001",
        "Replaces the libcephsqlite client registration and clears stale health metrics for out/down OSDs, changing failover recovery and health telemetry.",
    ),
    "src/mgr/MgrClient.cc": affect(
        "MGRMETRIC-001",
        "Stops sending labeled perf counters through the manager report path; target observability relies on the separate ceph-exporter path for those counters.",
    ),
    "src/mgr/MgrStandby.cc": affect(
        "MGRCORE-001",
        "Uses a random messenger nonce for the standby manager instead of the process-derived nonce, changing connection identity at target restart/failover.",
    ),
    "src/mgr/PyModuleRegistry.h": affect(
        "MGRDB-001",
        "Adds replace semantics for registered manager clients so a reopened libcephsqlite connection updates the address used for blocklisting.",
    ),
    "src/exporter/DaemonMetricCollector.cc": affect(
        "MGRMETRIC-001",
        "Moves ceph-exporter from legacy perf dump/schema to labeled counter dump/schema, changes labels/names, priority filtering, RGW identity, and long-running-average output.",
    ),
    "src/exporter/DaemonMetricCollector.h": affect(
        "MGRMETRIC-001",
        "Carries the new labeled-counter parsing and metric naming interface used by the target exporter collection loop.",
    ),
    "src/exporter/util.cc": affect(
        "MGRMETRIC-001",
        "Adds Prometheus metric-name normalization shared with the target manager module; exported series names can differ for punctuation and special characters.",
    ),
    "src/exporter/util.h": affect(
        "MGRMETRIC-001",
        "Exposes the target exporter metric-name normalization used by labeled counter collection.",
    ),
    "src/pybind/mgr/mgr_module.py": affect(
        "MGRDB-001, MGRCORE-001, MGROCH-001",
        "Changes manager SQLite schema execution to explicit statements/transactions with reconnect recovery, validates CLI input-file support, and updates orchestrator-facing client registration.",
    ),
    "src/pybind/mgr/mgr_util.py": affect(
        "MGRDB-001, MGRMON-001, MGRDEP-001",
        "Imports the new required bcrypt dependency, rejects expired/invalid TLS material more explicitly, and supports manager client re-registration and secure monitoring endpoints.",
    ),
    "src/pybind/mgr/object_format.py": affect(
        "MGRCLI-001",
        "Adds a status-string provider to formatted manager command responses; existing NFS and automation callers can observe different stderr/status output after module restart.",
    ),
    "src/pybind/mgr/orchestrator/_interface.py": affect(
        "MGROCH-001",
        "Changes orchestrator API signatures and daemon/host/service fields consumed by cephadm, Rook, Dashboard, and maintenance commands during mixed control-plane operation.",
    ),
    "src/pybind/mgr/orchestrator/module.py": affect(
        "MGROCH-001",
        "Changes existing host drain/remove and apply command semantics, including keep-conf/keyring and zap-device controls, input parsing, and upgrade/service-discovery command paths.",
    ),
    "src/pybind/mgr/requirements-required.txt": affect(
        "MGRDEP-001",
        "Adds bcrypt to the required manager Python environment; a target package or image missing it can fail imports before modules become active.",
    ),
    "src/pybind/mgr/balancer/module.py": affect(
        "MGRAUTO-001",
        "Changes automatic balancing time/day defaults and inclusive window logic; an enabled balancer can run during a different portion of the maintenance window.",
    ),
    "src/pybind/mgr/pg_autoscaler/module.py": affect(
        "MGRAUTO-001",
        "Pauses automatic PG adjustments while the norecover flag is set and changes pool/root accounting; stabilization work and progress events can differ during rollout.",
    ),
    "src/pybind/mgr/devicehealth/module.py": affect(
        "MGRDB-001",
        "Moves device-health storage to explicit SQLite transactions and adds database reconnect/retry handling; persisted SMART history and health commands behave differently after manager failover.",
    ),
    "src/pybind/mgr/influx/module.py": affect(
        "MGRMETRIC-001",
        "Uses the unlabeled perf-counter contract and skips a pool-removal race instead of failing collection; external maintenance telemetry can differ.",
    ),
    "src/pybind/mgr/k8sevents/module.py": affect(
        "MGRDEP-001, MGRMETRIC-001",
        "Adds compatibility for newer Kubernetes event model imports; enabled k8sevents delivery depends on the target client library and can change maintenance event visibility.",
    ),
    "src/pybind/mgr/prometheus/module.py": affect(
        "MGRMETRIC-001, MGRMON-001",
        "Defaults to excluding perf counters from mgr Prometheus output in favor of ceph-exporter, changes RGW identity mapping, and adds optional TLS for the monitoring endpoint.",
    ),
    "src/pybind/mgr/restful/api/perf.py": affect(
        "MGRMETRIC-001",
        "Moves the REST performance endpoint to the target unlabeled-counter contract, coupling API output to the mgr/exporter telemetry split.",
    ),
    "src/pybind/mgr/restful/module.py": affect(
        "MGRCLI-001",
        "Adds a 500-request retention limit that can trim the oldest unfinished REST command under load, changing automation visibility and completion tracking.",
    ),
    "src/pybind/mgr/stats/fs/perf_stats.py": affect(
        "MGRMETRIC-001",
        "Initializes target CephFS performance-report timing state used after module activation; CephFS client/rank telemetry continuity depends on this path.",
    ),
    "src/pybind/mgr/status/module.py": affect(
        "MGRCLI-001",
        "Changes existing status JSON, including standby-replay rank representation, and adds OSD JSON output; parsers used for validation can observe a schema difference.",
    ),
    "src/pybind/mgr/telegraf/module.py": affect(
        "MGRMETRIC-001",
        "Moves Telegraf collection to the target unlabeled perf-counter interface, tying its maintenance telemetry to the manager/exporter counter split.",
    ),
    "src/pybind/mgr/rbd_support/mirror_snapshot_schedule.py": affect(
        "MGRRBD-001",
        "Moves scheduling locks/state from class to module instance and changes asynchronous error detection; scheduled mirror snapshots can behave differently across reload/failover.",
    ),
    "src/pybind/mgr/rbd_support/perf.py": affect(
        "MGRRBD-001, MGRMETRIC-001",
        "Moves RBD performance query caches and synchronization objects from class scope to each module instance, changing state retained across module reload.",
    ),
    "src/pybind/mgr/rbd_support/trash_purge_schedule.py": affect(
        "MGRRBD-001",
        "Moves trash-purge scheduler locks/state to each module instance, changing scheduled cleanup continuity when the active manager reloads or fails over.",
    ),
    "src/pybind/mgr/rook/module.py": affect(
        "MGRROOK-001",
        "Changes the Rook orchestrator backend API and reconciliation behavior used by a Rook-managed cluster after the target manager becomes active.",
    ),
    "src/pybind/mgr/rook/rook_cluster.py": affect(
        "MGRROOK-001",
        "Reworks namespace, operator namespace, storage-class discovery, device inventory, placement, and service removal in the active Rook backend.",
    ),
    "src/pybind/mgr/dashboard/controllers/cluster.py": affect(
        "DASHUP-001",
        "Adds authenticated Dashboard endpoints that can list, start, pause, resume, stop, and query the cephadm upgrade state machine.",
    ),
    "src/pybind/mgr/dashboard/services/orchestrator.py": affect(
        "DASHUP-001",
        "Adds the Dashboard-to-orchestrator bridge for upgrade control operations and capability checks.",
    ),
    "src/pybind/mgr/dashboard/controllers/perf_counters.py": affect(
        "MGRMETRIC-001, DASHOBS-001",
        "Moves the Dashboard perf-counter API to the target unlabeled-counter contract; displayed validation metrics depend on the exporter split.",
    ),
    "src/pybind/mgr/dashboard/controllers/prometheus.py": affect(
        "MGRMON-001, DASHOBS-001",
        "Adds cephadm secure-monitoring credentials and CA verification to Dashboard Prometheus/Alertmanager proxy requests.",
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/app-routing.module.ts": affect(
        "DASHUP-001",
        "Registers the target Dashboard upgrade and progress routes guarded by the cephadm orchestrator backend.",
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/cluster/cluster.module.ts": affect(
        "DASHUP-001",
        "Loads the target Dashboard upgrade controls and progress components into the shipped cluster module.",
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/core/navigation/navigation/navigation.component.html": affect(
        "DASHUP-001",
        "Exposes the new upgrade control path in Dashboard navigation for users with config-option permission.",
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/shared/api/upgrade.service.ts": affect(
        "DASHUP-001",
        "Implements browser calls for list/start/pause/resume/stop/status and filters registry versions before an operator can start an upgrade.",
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/dashboard/health/health.component.ts": affect(
        "DASHOBS-001",
        "Changes Dashboard capacity threshold/color calculation and chart data, which can alter an operator's visual stop/go signal after manager upgrade.",
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/shared/api/prometheus.service.ts": affect(
        "DASHOBS-001",
        "Changes Dashboard Prometheus polling and time-window handling used by maintenance graphs.",
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/shared/components/grafana/grafana.component.ts": affect(
        "DASHOBS-001",
        "Changes Grafana availability acceptance and Explore URL format, affecting embedded monitoring access when anonymous Grafana access is disabled.",
    ),
    "src/pybind/mgr/dashboard/frontend/src/app/shared/services/prometheus-alert.service.ts": affect(
        "DASHOBS-001",
        "Changes active/critical/warning alert counting and ordering from the current alert set; Dashboard stop/go alert summaries can differ.",
    ),
}


DASHBOARD_UPGRADE_PREFIX = (
    "src/pybind/mgr/dashboard/frontend/src/app/ceph/cluster/upgrade/"
)


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if path in AFFECT_EXACT:
        return AFFECT_EXACT[path]

    if path.startswith("monitoring/ceph-mixin/dashboards/"):
        return affect(
            "MGRMON-001",
            "Changes the canonical Grafana mixin source used to render target cluster, host, OSD, pool, RBD, or RGW validation dashboards.",
        )
    if path.startswith("monitoring/ceph-mixin/dashboards_out/"):
        return affect(
            "MGRMON-001",
            "Changes a deployable generated Grafana dashboard consumed by the target monitoring stack; displayed rollout metrics or queries can differ.",
        )
    if path.startswith(DASHBOARD_UPGRADE_PREFIX):
        if path.endswith(".spec.ts") or path.endswith(".scss"):
            return trivial(
                "DASHUP-SUPPORT: unit-test or empty/style-only companion for the new Dashboard upgrade path; it does not independently execute upgrade control."
            )
        return affect(
            "DASHUP-001",
            "Implements the target Dashboard upgrade start/progress/pause/resume/stop user path; it can issue or interpret orchestrator upgrade actions when used.",
        )

    if path.startswith("doc/") or path == "monitoring/snmp/README.md":
        return trivial(
            "MGR-DOC: documentation-only row; it describes target behavior but does not execute or validate this upgrade."
        )
    if path.startswith("qa/"):
        return trivial(
            "MGR-QA: QA task or test definition only; it supports nearby findings but is not an executed acceptance result for this comparison."
        )
    if (
        "/tests/" in path
        or "/test_" in path
        or path.endswith(".spec.ts")
        or "/cypress/" in path
        or "/ci/" in path
        or path.endswith("tox.ini")
        or path.endswith("requirements-test.txt")
        or path.endswith("requirements-lint.txt")
        or path.endswith("run-backend-api-tests.sh")
        or path.endswith("run-frontend-e2e-tests.sh")
        or path.endswith("run-frontend-unittests.sh")
    ):
        return trivial(
            "MGR-TEST: unit/E2E/CI fixture, runner, or test dependency only; it was inspected as support but was not executed and is not a production control path."
        )

    if path.startswith("monitoring/ceph-mixin/"):
        return trivial(
            "MGRMON-BUILD: mixin build, lint, tox, or alert-test support only; deployable rule/dashboard changes are classified separately."
        )

    if path.startswith("src/pybind/mgr/dashboard/frontend/"):
        return trivial(
            "DASH-UI: screened Angular feature, style, localization, type, test-support, or dependency-bundle change outside the explicit upgrade-control and stop/go observability paths."
        )
    if path.startswith("src/pybind/mgr/dashboard/"):
        return trivial(
            "DASH-BACKEND: screened target management API/auth/refactor or feature change with no demonstrated effect on this hop's upgrade execution, continuity, rollback, or acceptance."
        )

    if path == "src/ceph_mgr.cc" or path.startswith("src/mgr/"):
        return trivial(
            "MGR-CODE: mechanical include/type/formatter/cache or unused interface support in this row; no independent upgrade, failover, state, or telemetry behavior was demonstrated."
        )
    if path == "src/exporter/ceph_exporter.cc":
        return trivial(
            "MGR-CODE: command help wording only; exporter collection, labels, and metric output are unchanged by this row."
        )
    if path.startswith("src/pybind/mgr/"):
        return trivial(
            "MGR-FEATURE: screened normal target feature, output/refactor, type annotation, optional-module, or developer dependency change without a demonstrated causal path for this version hop."
        )

    raise RuntimeError(f"owner 07 has an unreviewed row: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 670:
        raise RuntimeError(f"owner 07 expected 670 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 07 CSV contains duplicate paths")

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
        f"Classified owner 07: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
