"""Fault-drill scope checks run without Docker, HTTP, or a Ceph cluster."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "production_fault_drill.py"
if "production_acceptance" not in sys.modules:
    acceptance_spec = importlib.util.spec_from_file_location(
        "production_acceptance", SCRIPT.with_name("production_acceptance.py"))
    acceptance = importlib.util.module_from_spec(acceptance_spec)
    sys.modules[acceptance_spec.name] = acceptance
    acceptance_spec.loader.exec_module(acceptance)
acceptance = sys.modules["production_acceptance"]
spec = importlib.util.spec_from_file_location("production_fault_drill", SCRIPT)
drill = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = drill
spec.loader.exec_module(drill)

PROJECT = "storage-lab-console-staging-test"
CONTAINER_ID = "a123456789abcdef" * 4
FSID = "11111111-2222-4333-8444-555555555555"


def runtime_payload():
    return {
        "environment": "production",
        "deployment_scope": "staging",
        "deployment_id": PROJECT,
        "console_read_only": True,
        "ceph_mutations_enabled": False,
        "features": {
            "lab": False,
            "legacy_rgw": False,
            "legacy_rbd": False,
            # This gates the collector, not permission to mutate Ceph.
            "upgrade": True,
        },
    }


def inspection(**changes):
    result = {"id": CONTAINER_ID, "project": PROJECT, "service": "api", "running": True}
    result.update(changes)
    return result


def response(payload, *, status=200):
    return acceptance.Response(status, {}, acceptance.canonical_bytes(payload), .01)


class FakeDocker:
    """In-memory fault state only; never invokes the Docker executable."""

    def __init__(self):
        self.ids = {"api": "a" * 64, "postgres": "b" * 64, "executor": "c" * 64}
        self.stopped = {}
        self.calls = []
        self.snapshot_count = 0
        self.snapshot_error_at = None
        self.stop_error = None
        self.restore_failures = 0
        self.snapshot_value = {
            "collection_count": 2,
            "audit_count": 2,
            "collection_registry_sha256": "d" * 64,
            "audit_checkpoint_sha256": "e" * 64,
            "canonical_payloads_valid": True,
        }

    def resolve(self, service):
        self.calls.append(("resolve", service))
        return self.ids[service]

    def snapshot(self, api_id):
        if api_id != self.ids["api"]:
            raise AssertionError("test attempted an unexpected API container")
        self.snapshot_count += 1
        if self.snapshot_count == self.snapshot_error_at:
            raise drill.AcceptanceError("SIMULATED_DB_SNAPSHOT_FAILED")
        return copy.deepcopy(self.snapshot_value)

    def stop(self, container_id, service):
        if self.ids.get(service) != container_id:
            raise AssertionError("test attempted an unexpected container stop")
        self.calls.append(("stop", container_id, service))
        # Model a partial stop before an exception to exercise finally recovery.
        self.stopped[container_id] = service
        if self.stop_error:
            raise self.stop_error

    def start(self, container_id, service):
        if self.ids.get(service) != container_id:
            raise AssertionError("test attempted an unexpected container start")
        self.calls.append(("start", container_id, service))
        if self.restore_failures:
            self.restore_failures -= 1
            raise drill.AcceptanceError("SIMULATED_CONTAINER_RESTORE_FAILED")
        self.stopped.pop(container_id, None)


class FakeClient:
    def __init__(self, docker):
        self.docker = docker
        self.calls = []
        self.events = []
        self.false_ready_while_down = False
        self.ready_error_while_down = None
        self.marker = runtime_payload()

    def request(self, method, path, account, payload=None):
        self.calls.append((method, path))
        down = set(self.docker.stopped.values())
        if path == "/api/runtime-config":
            result = response(self.marker)
        elif path == "/api/ready":
            if down and self.ready_error_while_down:
                raise self.ready_error_while_down
            if down and not self.false_ready_while_down:
                dependencies = ["database" if service == "postgres" else "ceph_executor"
                                for service in sorted(down)]
                result = response({"ready": False, "blocking_dependencies": dependencies}, status=503)
            else:
                result = response({"ready": True})
        elif path == "/api/v1/as-is/collections":
            result = response({"detail": {"code": "DATABASE_UNAVAILABLE"}}, status=503)
        elif path == "/api/v1/as-is/observe":
            if "executor" in down:
                result = response({"detail": {"code": "EXECUTOR_UNAVAILABLE"}}, status=503)
            else:
                at = acceptance.utc_now()
                result = response({
                    "kind": "LIVE_OBSERVATION", "id": "test-observation", "fsid": FSID,
                    "started_at": at, "completed_at": at, "quality": "PARTIAL",
                    "freshness": {"mode": "READ_ON_REQUEST"},
                    "requested_daemon_keys": ["osd.2"], "missing_daemon_keys": [],
                    "daemons": [{"key": "osd.2", "type": "osd", "metrics": []}],
                })
        else:
            raise AssertionError("test attempted an unexpected HTTP request")
        self.events.append({"method": method, "path": path, **result.summary()})
        return result


def fake_drill():
    docker = FakeDocker()
    client = FakeClient(docker)
    args = SimpleNamespace(
        staging_project=PROJECT, daemon_key=["osd.2"], expected_fsid=FSID,
        timeout_seconds=.1, recovery_seconds=0,
    )
    account = acceptance.Account("admin", "test-admin", "private-password-not-in-report")
    runner = drill.FaultDrill(args, client, account, docker)
    runner.ids = docker.ids.copy()
    return runner, client, docker


class RuntimeMarkerTests(unittest.TestCase):
    def test_valid_read_only_staging_allows_upgrade_collector(self):
        for upgrade in (True, False):
            with self.subTest(upgrade=upgrade):
                payload = runtime_payload()
                payload["features"]["upgrade"] = upgrade
                self.assertIsNone(drill.validate_runtime_payload(payload, PROJECT))

    def test_all_scope_and_safety_markers_are_required(self):
        for key in ("environment", "deployment_scope", "deployment_id", "console_read_only",
                    "ceph_mutations_enabled", "features"):
            with self.subTest(key=key):
                payload = runtime_payload()
                del payload[key]
                with self.assertRaises(drill.AcceptanceError):
                    drill.validate_runtime_payload(payload, PROJECT)

    def test_target_must_be_exact_production_staging_project(self):
        for key, value in (
            ("environment", "lab"),
            ("environment", "Production"),
            ("deployment_scope", "production"),
            ("deployment_id", "storage-lab-console-local"),
            ("deployment_id", PROJECT + "-other"),
            ("deployment_id", PROJECT + " "),
        ):
            with self.subTest(key=key, value=value):
                payload = runtime_payload()
                payload[key] = value
                with self.assertRaises(drill.AcceptanceError):
                    drill.validate_runtime_payload(payload, PROJECT)

    def test_nonstaging_project_is_rejected_even_when_payload_matches(self):
        for project in ("storage-lab-console-local", "storage-lab-console-production", "", None, 1):
            with self.subTest(project=project):
                payload = runtime_payload()
                payload["deployment_id"] = project
                with self.assertRaises(drill.AcceptanceError):
                    drill.validate_runtime_payload(payload, project)

    def test_read_only_and_mutation_markers_require_exact_booleans(self):
        for key, values in (
            ("console_read_only", (False, 1, "true", None)),
            ("ceph_mutations_enabled", (True, 0, "false", None)),
        ):
            for value in values:
                with self.subTest(key=key, value=value):
                    payload = runtime_payload()
                    payload[key] = value
                    with self.assertRaises(drill.AcceptanceError):
                        drill.validate_runtime_payload(payload, PROJECT)

    def test_all_legacy_and_lab_features_must_be_present(self):
        for key in ("lab", "legacy_rgw", "legacy_rbd"):
            with self.subTest(key=key):
                payload = runtime_payload()
                del payload["features"][key]
                with self.assertRaises(drill.AcceptanceError):
                    drill.validate_runtime_payload(payload, PROJECT)

    def test_legacy_and_lab_features_require_boolean_false(self):
        for key in ("lab", "legacy_rgw", "legacy_rbd"):
            for value in (True, 0, "false", None):
                with self.subTest(key=key, value=value):
                    payload = runtime_payload()
                    payload["features"][key] = value
                    with self.assertRaises(drill.AcceptanceError):
                        drill.validate_runtime_payload(payload, PROJECT)

    def test_nonobject_payload_or_features_is_rejected(self):
        for payload in (None, [], "production", 1):
            with self.subTest(payload=payload), self.assertRaises(drill.AcceptanceError):
                drill.validate_runtime_payload(payload, PROJECT)
        for features in (None, [], "false", 0):
            with self.subTest(features=features):
                payload = runtime_payload()
                payload["features"] = features
                with self.assertRaises(drill.AcceptanceError):
                    drill.validate_runtime_payload(payload, PROJECT)


class ContainerScopeTests(unittest.TestCase):
    def test_only_exact_labelled_api_db_executor_containers_are_allowed(self):
        for service in ("api", "postgres", "executor"):
            for running in (True, False):
                with self.subTest(service=service, running=running):
                    row = inspection(service=service, running=running)
                    self.assertEqual(drill.validate_inspection(row, PROJECT, service), CONTAINER_ID)

    def test_unsupported_services_cannot_be_stopped_even_with_matching_labels(self):
        for service in ("ingress", "capacity-collector", "traffic", "osdmap", "", "api ", None, [], {}):
            with self.subTest(service=service), self.assertRaises(drill.AcceptanceError):
                drill.validate_inspection(inspection(service=service), PROJECT, service)

    def test_matching_labels_do_not_authorize_a_nonstaging_project(self):
        for project in ("storage-lab-console-local", "storage-lab-console-production", None, 1):
            with self.subTest(project=project), self.assertRaises(drill.AcceptanceError):
                drill.validate_inspection(inspection(project=project), project, "api")

    def test_project_and_service_labels_must_match_exactly(self):
        for row in (
            inspection(project="storage-lab-console-local"),
            inspection(project=PROJECT + "-other"),
            inspection(project=PROJECT + " "),
            inspection(service="executor"),
            inspection(service="API"),
            inspection(service="api "),
        ):
            with self.subTest(row=row), self.assertRaises(drill.AcceptanceError):
                drill.validate_inspection(row, PROJECT, "api")

    def test_container_id_is_full_lowercase_hex_without_shell_or_prefix_forms(self):
        for value in (
            CONTAINER_ID[:12], CONTAINER_ID[:-1], CONTAINER_ID + "a", CONTAINER_ID.upper(),
            "g" * 64, "storage-lab-console-staging-api", "--all", "", None,
            CONTAINER_ID + "\n", " " + CONTAINER_ID,
        ):
            with self.subTest(value=value), self.assertRaises(drill.AcceptanceError):
                drill.validate_inspection(inspection(id=value), PROJECT, "api")

    def test_container_running_marker_requires_boolean_not_truthiness(self):
        for value in (1, 0, "true", "false", None, [], {}):
            with self.subTest(value=value), self.assertRaises(drill.AcceptanceError):
                drill.validate_inspection(inspection(running=value), PROJECT, "api")

    def test_container_id_labels_and_running_marker_are_required(self):
        for key in ("id", "project", "service", "running"):
            with self.subTest(key=key):
                row = inspection()
                del row[key]
                with self.assertRaises(drill.AcceptanceError):
                    drill.validate_inspection(row, PROJECT, "api")

    def test_inspection_must_be_an_object(self):
        for row in (None, [], "api", 1):
            with self.subTest(row=row), self.assertRaises(drill.AcceptanceError):
                drill.validate_inspection(row, PROJECT, "api")


class DockerCommandGuardTests(unittest.TestCase):
    def target(self, row=None):
        class RecordingTarget(drill.DockerTarget):
            def __init__(self):
                super().__init__(PROJECT)
                self.commands = []
                self.row = row if row is not None else inspection()
                self.ids["api"] = CONTAINER_ID

            def inspect(self, container_id):
                return self.row

            def command(self, arguments, **kwargs):
                self.commands.append(arguments)
                return ""

        return RecordingTarget()

    def test_docker_target_constructor_requires_staging_project(self):
        for project in ("storage-lab-console-local", "storage-lab-console-production", None, [], 1):
            with self.subTest(project=project), self.assertRaises(drill.AcceptanceError):
                drill.DockerTarget(project)

    def test_unresolved_or_different_id_never_reaches_stop_command(self):
        for container_id in ("b" * 64, "--all", CONTAINER_ID[:12]):
            with self.subTest(container_id=container_id):
                target = self.target()
                with self.assertRaisesRegex(drill.AcceptanceError, "CONTAINER_NOT_RESOLVED_BY_THIS_DRILL"):
                    target.stop(container_id, "api")
                self.assertEqual(target.commands, [])

    def test_changed_labels_or_changed_resolved_id_never_reaches_mutation(self):
        for row in (inspection(project="storage-lab-console-local"),
                    inspection(service="executor"), inspection(id="b" * 64)):
            with self.subTest(row=row):
                target = self.target(row)
                for operation in (target.stop, target.start):
                    with self.assertRaises(drill.AcceptanceError):
                        operation(CONTAINER_ID, "api")
                self.assertEqual(target.commands, [])

    def test_guarded_start_and_stop_use_only_original_full_id(self):
        target = self.target()
        target.stop(CONTAINER_ID, "api")
        target.row["running"] = False
        target.start(CONTAINER_ID, "api")
        self.assertEqual(target.commands, [
            ["stop", "--time", "1", CONTAINER_ID], ["start", CONTAINER_ID],
        ])

    def test_resolve_requires_unique_original_running_container(self):
        for candidates, row in (
            ("", inspection()),
            (CONTAINER_ID[:12] + "\n" + "b" * 12, inspection()),
            ("--all", inspection()),
            (CONTAINER_ID[:12], inspection(project="storage-lab-console-local")),
            (CONTAINER_ID[:12], inspection(running=False)),
        ):
            with self.subTest(candidates=candidates, row=row):
                target = self.target(row)
                target.command = lambda _arguments, **_kwargs: candidates
                target.ids.clear()
                with self.assertRaises(drill.AcceptanceError):
                    target.resolve("api")
                self.assertEqual(target.ids, {})

    def test_snapshot_requires_valid_hashes_and_canonical_payloads(self):
        baseline = FakeDocker().snapshot_value
        for key, value in (
            ("canonical_payloads_valid", False),
            ("canonical_payloads_valid", 1),
            ("collection_registry_sha256", "d" * 63),
            ("audit_checkpoint_sha256", "e" * 63),
            ("collection_registry_sha256", "D" * 64),
        ):
            with self.subTest(key=key, value=value):
                payload = baseline.copy()
                payload[key] = value
                target = self.target()
                target.command = lambda _arguments, **_kwargs: json.dumps(payload)
                with self.assertRaises(drill.AcceptanceError):
                    target.snapshot(CONTAINER_ID)

    def test_snapshot_counts_are_nonnegative_exact_integers(self):
        baseline = FakeDocker().snapshot_value
        for key in ("collection_count", "audit_count"):
            for value in (-1, True, 1.0, "2", None):
                with self.subTest(key=key, value=value):
                    payload = baseline.copy()
                    payload[key] = value
                    target = self.target()
                    target.command = lambda _arguments, **_kwargs: json.dumps(payload)
                    with self.assertRaises(drill.AcceptanceError):
                        target.snapshot(CONTAINER_ID)
        target = self.target()
        target.command = lambda _arguments, **_kwargs: json.dumps(baseline)
        self.assertEqual(target.snapshot(CONTAINER_ID), baseline)


class FinallyRecoveryTests(unittest.TestCase):
    def test_executor_fault_restores_original_container_and_preserves_history(self):
        runner, client, docker = fake_drill()
        result = runner.run_fault("executor")
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["container_restarted"])
        self.assertEqual(result["before"], result["after_restore"])
        self.assertEqual(result["before"], result["after_fresh"])
        self.assertEqual(runner.stopped, {})
        self.assertEqual(docker.stopped, {})
        self.assertEqual(docker.calls, [
            ("stop", "c" * 64, "executor"), ("start", "c" * 64, "executor"),
        ])
        self.assertNotIn("private-password-not-in-report", json.dumps(result))

    def test_false_ready_assertion_still_restores_container_and_records_failure(self):
        runner, client, docker = fake_drill()
        client.false_ready_while_down = True
        result = runner.run_fault("postgres")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["container_restarted"])
        checks = {row["name"]: row for row in result["checks"]}
        self.assertEqual(checks["dependency_not_ready"]["status"], "FAIL")
        self.assertEqual(docker.stopped, {})
        self.assertEqual(runner.stopped, {})

    def test_http_exception_after_stop_restores_without_reporting_exception_secrets(self):
        runner, client, docker = fake_drill()
        client.ready_error_while_down = RuntimeError("password=not-for-the-report")
        result = runner.run_fault("executor")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["container_restarted"])
        self.assertIn("FAULT_EXCEPTION_RUNTIMEERROR", json.dumps(result))
        self.assertNotIn("not-for-the-report", json.dumps(result))
        self.assertEqual(docker.stopped, {})

    def test_partial_stop_error_is_registered_before_stop_and_recovered_finally(self):
        runner, client, docker = fake_drill()
        docker.stop_error = drill.AcceptanceError("SIMULATED_PARTIAL_STOP")
        result = runner.run_fault("executor")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["container_restarted"])
        self.assertEqual(docker.stopped, {})
        self.assertEqual(runner.stopped, {})
        self.assertEqual(docker.calls[-1], ("start", "c" * 64, "executor"))

    def test_snapshot_failure_before_stop_never_mutates_a_container(self):
        runner, client, docker = fake_drill()
        docker.snapshot_error_at = 1
        result = runner.run_fault("executor")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(docker.calls, [])
        self.assertEqual(docker.stopped, {})
        self.assertNotIn("container_restarted", result)

    def test_snapshot_failure_after_restore_does_not_leave_container_stopped(self):
        runner, client, docker = fake_drill()
        docker.snapshot_error_at = 2
        result = runner.run_fault("executor")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["container_restarted"])
        self.assertIn("SIMULATED_DB_SNAPSHOT_FAILED", json.dumps(result))
        self.assertEqual(docker.stopped, {})
        self.assertEqual(runner.stopped, {})

    def test_outer_run_retries_failed_finally_restore_before_returning(self):
        runner, client, docker = fake_drill()
        docker.restore_failures = 1
        result = runner.run()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["containers_still_requiring_restore"], [])
        self.assertEqual(docker.stopped, {})
        self.assertEqual(runner.stopped, {})
        starts = [call for call in docker.calls if call[0] == "start"]
        self.assertEqual(starts, [("start", "c" * 64, "executor")] * 2)
        self.assertNotIn("private-password-not-in-report", json.dumps(result))

    def test_invalid_runtime_marker_aborts_before_any_container_stop(self):
        runner, client, docker = fake_drill()
        client.marker["deployment_scope"] = "production"
        with self.assertRaises(drill.AcceptanceError):
            runner.run()
        self.assertEqual(docker.calls, [])


if __name__ == "__main__":
    unittest.main()
