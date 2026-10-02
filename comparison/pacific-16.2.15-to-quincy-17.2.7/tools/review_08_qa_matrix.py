"""Classify inspected cephadm QA harness, selectors and acceptance recipes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "08-cephadm-orchestrator.csv"
affect = {
    "qa/tasks/cephadm.conf": ("ADM-015", "QA cluster defaults drop MON file logging option, update EC profile syntax, and select high_recovery_ops mClock profile; changes test environment."),
    "qa/tasks/cephadm.py": ("ADM-015", "Teuthology cephadm task now pulls image before bootstrap, changes host-add shell origin, and adds CephFS/iSCSI setup; changes test setup path."),
    "qa/tasks/cephadm_cases/test_cli.py": ("ADM-015", "CLI test waits until stopped OSD is no longer reported running before restarting it, changing test synchronization and acceptance."),
    "qa/suites/orch/cephadm/orchestrator_cli/0-random-distro$": ("ADM-015", "Orchestrator CLI distro selector changes from smoke-relative link to shared container-host distro matrix."),
    "qa/suites/orch/cephadm/orchestrator_cli/agent": ("ADM-015", "New selector includes both agent on/off variants in orchestrator CLI test matrix."),
    "qa/suites/orch/cephadm/osds/0-distro": ("ADM-015", "OSD suite distro selector changes to shared container-host matrix."),
    "qa/suites/orch/cephadm/smoke-roleless/0-distro": ("ADM-015", "Roleless smoke distro selector changes to shared container-host matrix."),
    "qa/suites/orch/cephadm/smoke-singlehost/.qa": ("ADM-015", "R100 empty marker was paired with old workunits/0-distro/.qa; source marker removed while single-host smoke marker appears, not a logical code move."),
    "qa/suites/orch/cephadm/smoke-singlehost/0-distro$": ("ADM-015", "Old single-host distro selector removed as random shared-distro selector is introduced."),
    "qa/suites/orch/cephadm/smoke-singlehost/0-random-distro$": ("ADM-015", "Single-host smoke now uses shared container-host random distro selector."),
    "qa/suites/orch/cephadm/smoke/0-distro": ("ADM-015", "Smoke suite gains direct shared container-host distro selector."),
    "qa/suites/orch/cephadm/smoke/distro": ("ADM-015", "Old local smoke distro selector removed after shared selector added."),
    "qa/suites/orch/cephadm/thrash/0-distro": ("ADM-015", "Thrash suite distro selector changes to shared container-host matrix."),
    "qa/suites/orch/cephadm/with-work/0-distro": ("ADM-015", "With-work suite distro selector changes to shared container-host matrix."),
    "qa/suites/orch/cephadm/workunits/0-distro": ("ADM-015", "Workunit suite gains shared container-host distro selector."),
    "qa/suites/orch/cephadm/workunits/0-distro/centos_8.stream_container_tools.yaml": ("ADM-015", "Old pinned CentOS stream distro selector removed from workunit suite."),
    "qa/suites/orch/cephadm/workunits/agent": ("ADM-015", "New selector includes agent on/off matrix in cephadm workunits."),
    "qa/suites/orch/cephadm/mgr-nfs-upgrade/0-centos_8.stream_container_tools.yaml": ("ADM-015", "R100 empty selector paired with old dashboard distro entry; target changes mgr-NFS-upgrade distro selection, not a logical code move."),
    "qa/suites/orch/cephadm/dashboard/0-distro/ignorelist_health.yaml": ("ADM-016", "Dashboard E2E suite health ignorelist selector removed with old dashboard test suite."),
    "qa/suites/orch/cephadm/dashboard/task/test_e2e.yaml": ("ADM-016", "Old cephadm dashboard E2E task, roles and health ignorelist removed from suite coverage."),
    "qa/suites/orch/cephadm/mgr-nfs-upgrade/1-start.yaml": ("ADM-016", "NFS upgrade start recipe removes slow-request/PG/MDS/OSD health log ignorelist, changing test acceptance."),
    "qa/suites/orch/cephadm/orchestrator_cli/orchestrator_cli.yaml": ("ADM-016", "CLI recipe adds POOL_APP_NOT_ENABLED to log ignorelist, changing tolerated health output."),
    "qa/suites/orch/cephadm/thrash/2-thrash.yaml": ("ADM-016", "Thrash recipe removes MON/OSD/PG and other health log ignorelist entries, changing accepted output."),
    "qa/suites/orch/cephadm/workunits/task/test_nfs.yaml": ("ADM-016", "NFS workunit removes MDS/stray-daemon health log ignorelist, changing accepted output."),
    "qa/suites/orch/cephadm/workunits/task/test_orch_cli.yaml": ("ADM-016", "Orchestrator CLI workunit removes MON/OSD/paused health log ignorelist, changing accepted output."),
    "qa/suites/orch/cephadm/workunits/task/test_orch_cli_mon.yaml": ("ADM-016", "MON CLI workunit removes MON/MGR/quorum health log ignorelist, changing accepted output."),
    "qa/workunits/cephadm/test_dashboard_e2e.sh": ("ADM-016", "Cypress config keys change and setup no longer disables device monitoring or deletes metrics pool; changes E2E test preconditions."),
    "qa/workunits/cephadm/test_cephadm.sh": ("ADM-010;ADM-016", "Cephadm workunit defaults to Quincy image instead of Pacific, removes --with-exporter bootstrap and exporter health checks."),
    "qa/suites/orch/cephadm/with-work/tasks/rotate-keys.yaml": ("ADM-017", "New work recipe rotates OSD/MGR auth keys and waits for each key change; adds key-rotation acceptance coverage."),
    "qa/suites/orch/cephadm/workunits/task/test_rgw_multisite.yaml": ("ADM-017", "New RGW multisite recipe validates realm token JSON, endpoint and credentials after cephadm setup."),
    "qa/suites/orch/cephadm/thrash-old-clients/1-install/luminous-v1only.yaml": ("ADM-018", "Removes Luminous msgr1-only old-client install variant from cephadm thrash coverage."),
    "qa/suites/orch/cephadm/thrash-old-clients/1-install/luminous.yaml": ("ADM-018", "Removes Luminous old-client install variant from cephadm thrash coverage."),
    "qa/suites/orch/cephadm/thrash-old-clients/1-install/mimic-v1only.yaml": ("ADM-018", "Removes Mimic msgr1-only old-client install variant from cephadm thrash coverage."),
    "qa/suites/orch/cephadm/thrash-old-clients/1-install/mimic.yaml": ("ADM-018", "Removes Mimic old-client install variant from cephadm thrash coverage."),
    "qa/suites/orch/cephadm/thrash-old-clients/distro$/ubuntu_18.04.yaml": ("ADM-018", "Removes Ubuntu 18.04 selector tied to legacy-client cephadm thrash suite."),
}
special_old = {
    "qa/suites/orch/cephadm/smoke-singlehost/.qa": "qa/suites/orch/cephadm/workunits/0-distro/.qa",
    "qa/suites/orch/cephadm/mgr-nfs-upgrade/0-centos_8.stream_container_tools.yaml": "qa/suites/orch/cephadm/dashboard/0-distro/centos_8.stream_container_tools.yaml",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in affect} == set(affect)
for row in rows:
    name = row["path"]
    if name not in affect:
        continue
    assert not row["upgrade_impact"], name
    if name in special_old:
        assert row["status"] == "R" and row["old_path"] == special_old[name], name
    ids, reason = affect[name]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = ids
    row["impact_reason"] = f"{ids}: {reason}"
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
