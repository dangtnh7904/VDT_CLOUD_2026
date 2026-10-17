#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 08 cephadm/orchestrator rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "08-cephadm-orchestrator.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


PRODUCTION: dict[str, tuple[str, str, str]] = {
    "src/cephadm/build.py": affect(
        "ADMEXEC-001",
        "Adds the target cephadm zipapp build path and embedded dependency handling; the delivered cephadm artifact and its hash are part of daemon deployment compatibility.",
    ),
    "src/cephadm/build.sh": affect(
        "ADMEXEC-001",
        "Builds the target cephadm executable through the new zipapp workflow, changing how the deployment artifact is assembled and verified.",
    ),
    "src/cephadm/cephadm.py": affect(
        "ADMEXEC-001, ADMIMAGE-001, ADMSSH-001, ADMSVC-001",
        "Replaces the cephadm entry point and changes atomic config writes, deploy/redeploy/reconfig behavior, image defaults, signed-SSH handling, systemd relationships, and existing service deployment paths.",
    ),
    "src/pybind/mgr/cephadm/agent.py": affect(
        "ADMAGENT-001, ADMHOST-001",
        "Changes agent message, metadata, TLS, and host-refresh behavior used when the cephadm agent is enabled; agent reachability and reconcile inputs differ.",
    ),
    "src/pybind/mgr/cephadm/exchange.py": affect(
        "ADMAGENT-001",
        "Adds the target agent message exchange used by the cephadm HTTP endpoint, changing the enabled agent control path.",
    ),
    "src/pybind/mgr/cephadm/http_server.py": affect(
        "ADMAGENT-001, ADMMON-001",
        "Introduces the target HTTPS server for cephadm agents and service discovery; endpoint, certificate, and availability behavior differ when those paths are enabled.",
    ),
    "src/pybind/mgr/cephadm/inventory.py": affect(
        "ADMHOST-001, ADMMIG-001",
        "Separates daemon drain from config/keyring drain labels, changes host eligibility/event handling, and queues RGW spec migration while loading persisted orchestrator state.",
    ),
    "src/pybind/mgr/cephadm/migrations.py": affect(
        "ADMMIG-001",
        "Advances the orchestrator schema migration from 5 to 6 and rewrites legacy RGW frontend strings into type plus extra arguments, mutating persisted service specs on the first target manager.",
    ),
    "src/pybind/mgr/cephadm/module.py": affect(
        "ADMEXEC-001, ADMIMAGE-001, ADMAGENT-001, ADMMON-001",
        "Changes cephadm artifact hashing and command handling, default registries and service images, agent/HTTP configuration, service registration, and monitoring security options in the active manager module.",
    ),
    "src/pybind/mgr/cephadm/schedule.py": affect(
        "ADMSCHED-001",
        "Makes label and host-pattern placement constraints intersect and changes filtering inputs, so an existing spec can reconcile to a different eligible host set.",
    ),
    "src/pybind/mgr/cephadm/serve.py": affect(
        "ADMEXEC-001, ADMHOST-001, ADMSCHED-001",
        "Changes the cephadm reconcile loop, host refresh/failure handling, daemon actions, and placement application that run continuously during and after rollout.",
    ),
    "src/pybind/mgr/cephadm/service_discovery.py": affect(
        "ADMMON-001",
        "Adds the HTTP service-discovery source consumed by target Prometheus configuration, replacing static target material for an existing monitoring deployment.",
    ),
    "src/pybind/mgr/cephadm/services/cephadmservice.py": affect(
        "ADMMIG-001, ADMAGENT-001, ADMSVC-001",
        "Changes shared daemon preparation plus existing RGW and agent configuration, including migrated RGW frontend arguments and target endpoint/certificate data.",
    ),
    "src/pybind/mgr/cephadm/services/ingress.py": affect(
        "ADMSVC-001",
        "Changes HAProxy and keepalived preparation for existing ingress specs, including address/interface and health-check inputs used during reconcile.",
    ),
    "src/pybind/mgr/cephadm/services/iscsi.py": affect(
        "ADMSVC-001",
        "Changes existing iSCSI daemon configuration and deployment integration, including the target tcmu-runner supervision path.",
    ),
    "src/pybind/mgr/cephadm/services/monitoring.py": affect(
        "ADMMON-001, ADMIMAGE-001",
        "Changes existing Prometheus, Alertmanager, Grafana, Loki, and node-exporter configuration, image selection, discovery, and optional TLS/basic-auth behavior.",
    ),
    "src/pybind/mgr/cephadm/services/nfs.py": affect(
        "ADMSVC-001",
        "Changes the generated configuration and dependencies for existing NFS deployments, including id mapping and ingress-aware settings.",
    ),
    "src/pybind/mgr/cephadm/services/osd.py": affect(
        "ADMOSD-001, ADMHOST-001",
        "Changes DriveGroup-to-ceph-volume deployment and host-drain/reconcile behavior for managed OSD daemons; device activation inputs and daemon placement can differ.",
    ),
    "src/pybind/mgr/cephadm/ssh.py": affect(
        "ADMSSH-001, ADMHOST-001",
        "Adds signed SSH certificate support, changes file transfer and timeout/error classification, and can mark a host offline through a different failure path.",
    ),
    "src/pybind/mgr/cephadm/ssl_cert_utils.py": affect(
        "ADMAGENT-001, ADMMON-001",
        "Adds certificate generation used by the target agent and secure monitoring endpoints; certificate identity and renewal state become rollout prerequisites when enabled.",
    ),
    "src/pybind/mgr/cephadm/templates/services/alertmanager/alertmanager.yml.j2": affect(
        "ADMMON-001",
        "Changes the rendered Alertmanager configuration for an existing monitoring service during target reconcile.",
    ),
    "src/pybind/mgr/cephadm/templates/services/alertmanager/web.yml.j2": affect(
        "ADMMON-001",
        "Adds the Alertmanager web TLS/basic-auth configuration rendered when secure monitoring is enabled.",
    ),
    "src/pybind/mgr/cephadm/templates/services/grafana/ceph-dashboard.yml.j2": affect(
        "ADMMON-001",
        "Changes the provisioned Grafana dashboard provider used when an existing Grafana daemon is reconciled.",
    ),
    "src/pybind/mgr/cephadm/templates/services/grafana/grafana.ini.j2": affect(
        "ADMMON-001",
        "Changes target Grafana protocol, security, and datasource-related settings rendered for an existing monitoring stack.",
    ),
    "src/pybind/mgr/cephadm/templates/services/ingress/haproxy.cfg.j2": affect(
        "ADMSVC-001",
        "Changes HAProxy health checks, bind/stats addresses, and TCP defaults for an existing ingress deployment.",
    ),
    "src/pybind/mgr/cephadm/templates/services/ingress/keepalived.conf.j2": affect(
        "ADMSVC-001",
        "Changes keepalived interface/VIP rendering and script-security behavior for an existing ingress deployment.",
    ),
    "src/pybind/mgr/cephadm/templates/services/loki.yml.j2": affect(
        "ADMMON-001",
        "Changes Loki storage schema to the target configuration, including a date-gated TSDB v13 period used by an existing logging stack.",
    ),
    "src/pybind/mgr/cephadm/templates/services/nfs/ganesha.conf.j2": affect(
        "ADMSVC-001",
        "Changes generated Ganesha NFS settings, including NLM and ingress-aware host configuration, on service reconcile.",
    ),
    "src/pybind/mgr/cephadm/templates/services/node-exporter/web.yml.j2": affect(
        "ADMMON-001",
        "Adds the node-exporter web TLS/basic-auth configuration rendered for existing exporters when secure monitoring is enabled.",
    ),
    "src/pybind/mgr/cephadm/templates/services/prometheus/prometheus.yml.j2": affect(
        "ADMMON-001",
        "Moves target discovery for an existing Prometheus deployment toward cephadm HTTP service discovery and changes scrape security inputs.",
    ),
    "src/pybind/mgr/cephadm/templates/services/prometheus/web.yml.j2": affect(
        "ADMMON-001",
        "Adds the Prometheus web TLS/basic-auth configuration rendered when secure monitoring is enabled.",
    ),
    "src/pybind/mgr/cephadm/upgrade.py": affect(
        "ADMUPGRADE-001, ADMIMAGE-001",
        "Changes daemon type/order and image identity during upgrade and adds optional MDS filesystem fail/join sequencing; availability and selection behavior differ by service and option.",
    ),
    "src/pybind/mgr/cephadm/utils.py": affect(
        "ADMUPGRADE-001, ADMHOST-001",
        "Changes daemon image/type classifications and special host-label semantics consumed by upgrade ordering, drain, and reconcile decisions.",
    ),
}


TRIVIAL_EXACT = {
    "src/cephadm/.gitignore",
    "src/cephadm/containers/keepalived/README.md",
    "src/cephadm/samples/custom_container.json",
    "src/cephadm/samples/nfs.json",
    "src/cephadm/tox.ini",
    "src/pybind/mgr/cephadm/Vagrantfile",
    "src/pybind/mgr/cephadm/autotune.py",
    "src/pybind/mgr/cephadm/configchecks.py",
    "src/pybind/mgr/cephadm/services/jaeger.py",
    "src/pybind/mgr/cephadm/services/node_proxy.py",
    "src/pybind/mgr/cephadm/services/nvmeof.py",
    "src/pybind/mgr/cephadm/templates/services/nvmeof/ceph-nvmeof.conf.j2",
    "src/pybind/mgr/cephadm/tuned_profiles.py",
    "src/pybind/mgr/cephadm/vagrant.config.example.json",
}


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    if path.startswith("doc/"):
        return trivial(
            "ADM-DOC: documentation-only row; it describes target operation but does not itself execute or validate the upgrade path."
        )
    if path.startswith("qa/"):
        return trivial(
            "ADM-QA: suite, task, or workunit definition only; it is useful validation evidence but is not an executed acceptance result for this comparison."
        )
    if path.startswith("src/cephadm/box/"):
        return trivial(
            "ADM-DEV: cephadm developer-box/container harness only; it is outside the packaged cluster rollout and daemon reconcile path."
        )
    if path.startswith("src/cephadm/tests/") or path.startswith(
        "src/pybind/mgr/cephadm/tests/"
    ):
        return trivial(
            "ADM-TEST: unit-test or fixture row only; it supports nearby findings but is not an executed result or production runtime path."
        )
    if path in TRIVIAL_EXACT:
        if path.endswith("autotune.py"):
            return trivial(
                "ADM-OPTIN: only adds a memory floor for the target-only NVMe-oF service; an inherited Quincy deployment has no existing daemon on this path."
            )
        if any(name in path for name in ("jaeger.py", "node_proxy.py", "nvmeof.py", "services/nvmeof/")):
            return trivial(
                "ADM-OPTIN: target-only service implementation/template; it is not instantiated by upgrading an inherited Quincy service spec without an explicit new opt-in."
            )
        if path.endswith("configchecks.py") or path.endswith("tuned_profiles.py"):
            return trivial(
                "ADM-CODE: helper/cache-access cleanup only in this row; no upgrade, placement, daemon lifecycle, or rendered service contract changes."
            )
        return trivial(
            "ADM-SUPPORT: developer metadata, example, sample, README, or tox/Vagrant support only; it is not consumed by an inherited production rollout."
        )

    try:
        return PRODUCTION[path]
    except KeyError as error:
        raise RuntimeError(f"owner 08 has an unreviewed row: {path!r}") from error


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 189:
        raise RuntimeError(f"owner 08 expected 189 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 08 CSV contains duplicate paths")

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
        f"Classified owner 08: affect={affect_count} "
        f"trivial={trivial_count} unclassified=0"
    )


if __name__ == "__main__":
    main()
