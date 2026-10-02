"""Record inspected cephadm host, placement, transport and OSD runtime changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "08-cephadm-orchestrator.csv"
affect = {
    "src/pybind/mgr/cephadm/inventory.py": (
        "ADM-003;ADM-004;ADM-005",
        "HostCache now reads legacy inline devices and writes device chunks in separate config keys; also persists agent metadata state and supplies draining/unreachable host sets to placement.",
    ),
    "src/pybind/mgr/cephadm/migrations.py": (
        "ADM-004",
        "Scheduler 0-to-1 placement migration now passes both unreachable and draining host sets to HostAssignment, changing conversion when a host has _no_schedule.",
    ),
    "src/pybind/mgr/cephadm/schedule.py": (
        "ADM-004",
        "Explicit placement recognizes draining hosts as known but excludes them from candidate slots; related-service preference and loopback placement also change scheduling.",
    ),
    "src/pybind/mgr/cephadm/agent.py": (
        "ADM-005",
        "New optional cephadm agent endpoint validates host/keyring/counter and receives metadata, which can gate service spec application while metadata is stale.",
    ),
    "src/pybind/mgr/cephadm/services/osd.py": (
        "ADM-006",
        "OSD spec deployment now gathers per-host async ceph-volume work and applies async timeout handling to create, preview and zap calls.",
    ),
    "src/pybind/mgr/cephadm/ssh.py": (
        "ADM-007",
        "New asyncssh transport manages per-host connections, command execution, SCP and timeout/error propagation for cephadm remote operations.",
    ),
    "src/pybind/mgr/cephadm/offline_watcher.py": (
        "ADM-007",
        "Offline host probe changes from remoto through CephadmServe to SSHManager.check_execute_command, sharing target transport/error handling.",
    ),
}
trivial = {
    "src/pybind/mgr/cephadm/tests/test_agent.py": "T08-agent-tests: New unit coverage for agent service-discovery output; test-only code does not alter deployed agent or upgrade orchestration.",
    "src/pybind/mgr/cephadm/tests/test_migration.py": "T08-migration-test: Adds agent metadata fixture call to the existing scheduler migration test; no deployed migration logic changes in this file.",
    "src/pybind/mgr/cephadm/tests/test_scheduling.py": "T08-scheduling-tests: Updates HostAssignment test signatures and adds draining-host placement cases; regression coverage, not a changed production acceptance selector.",
    "src/pybind/mgr/cephadm/tests/test_ssh.py": "T08-ssh-tests: New unit tests simulate asyncssh connection-error variants; no production transport or suite selection changes in this file.",
}
selected = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name not in selected:
        continue
    if name in affect:
        ids, reason = affect[name]
        assert row["upgrade_impact"] in ("", "affect"), name
        assert row["finding_id"] in ("", ids), name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = ids
        row["impact_reason"] = f"{ids}: {reason}"
    else:
        assert row["upgrade_impact"] in ("", "trivial"), name
        assert not row["finding_id"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
