#!/usr/bin/env python3
"""Explicitly authorized, isolated staging fault drills; never alter live Ceph.

The only Docker mutations are stop/start of the exact API, PostgreSQL and
executor container IDs resolved from the verified staging project. A finally
block restarts each container even if an assertion fails. Credentials and
database connection strings are consumed privately and never reported.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import time
from pathlib import Path
from uuid import UUID

from production_acceptance import (
    AcceptanceError, Client, DAEMON_KEY, STAGING_PROJECT, canonical_bytes, expect_status,
    load_accounts, utc_now, validate_observation, validate_target,
)

SERVICES = {"api", "postgres", "executor"}
CONTAINER_ID = re.compile(r"^[a-f0-9]{64}$")
INSPECTION_FORMAT = (
    '{"id":{{json .Id}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"running":{{json .State.Running}}}'
)
SNAPSHOT_CODE = r'''
import hashlib,json,sys
import psycopg
from psycopg.rows import dict_row
from app.config import get_settings
from app.modules.as_is.service import encoded
try:
    with psycopg.connect(get_settings().database_url,row_factory=dict_row,connect_timeout=10) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        collections=conn.execute('SELECT * FROM as_is_collections ORDER BY id').fetchall()
        events=conn.execute('SELECT * FROM as_is_collection_events ORDER BY id').fetchall()
        valid=all(hashlib.sha256(encoded(row['payload'])).hexdigest()==row['sha256'] for row in collections)
        registry=[{k:v for k,v in row.items() if k!='payload'} for row in collections]
        def digest(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False,default=str).encode()).hexdigest()
        print(json.dumps({'collection_count':len(collections),'audit_count':len(events),'collection_registry_sha256':digest(registry),'audit_checkpoint_sha256':digest(events),'canonical_payloads_valid':valid}))
except Exception:
    print(json.dumps({'error_code':'READ_ONLY_DB_SNAPSHOT_FAILED'}))
    sys.exit(1)
'''


def validate_runtime_payload(payload, project):
    if (not isinstance(project, str) or not STAGING_PROJECT.fullmatch(project)
            or not isinstance(payload, dict) or payload.get("environment") != "production"
            or payload.get("deployment_scope") != "staging"
            or payload.get("deployment_id") != project
            or payload.get("console_read_only") is not True
            or payload.get("ceph_mutations_enabled") is not False):
        raise AcceptanceError("EXPLICIT_PRODUCTION_READONLY_STAGING_REQUIRED")
    features = payload.get("features")
    if not isinstance(features, dict) or any(features.get(key) is not False
            for key in ("lab", "legacy_rgw", "legacy_rbd")):
        raise AcceptanceError("MUTATION_FEATURES_NOT_DISABLED")


def validate_inspection(row, project, service):
    if (not isinstance(service, str) or service not in SERVICES
            or not isinstance(project, str) or not STAGING_PROJECT.fullmatch(project)
            or not isinstance(row, dict)
            or row.get("project") != project or row.get("service") != service
            or not isinstance(row.get("id"), str) or not CONTAINER_ID.fullmatch(row["id"])
            or type(row.get("running")) is not bool):
        raise AcceptanceError("EXACT_STAGING_CONTAINER_IDENTITY_REQUIRED")
    return row["id"]


class DockerTarget:
    def __init__(self, project):
        if not isinstance(project, str) or not STAGING_PROJECT.fullmatch(project):
            raise AcceptanceError("EXPLICIT_STAGING_PROJECT_REQUIRED")
        self.project = project
        self.ids = {}

    def command(self, arguments, *, timeout=25):
        try:
            result = subprocess.run(["docker", *arguments], capture_output=True,
                                    text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise AcceptanceError("BOUNDED_DOCKER_COMMAND_FAILED") from None
        if result.returncode or len(result.stdout.encode()) > 256 * 1024:
            raise AcceptanceError("DOCKER_COMMAND_FAILED")
        return result.stdout

    def inspect(self, container_id):
        try:
            return json.loads(self.command(["inspect", "--format", INSPECTION_FORMAT, container_id]))
        except (ValueError, TypeError):
            raise AcceptanceError("INVALID_SAFE_DOCKER_INSPECTION") from None

    def resolve(self, service):
        if service not in SERVICES:
            raise AcceptanceError("FAULT_SERVICE_NOT_ALLOWED")
        candidates = self.command(["ps", "-aq", "--filter",
            f"label=com.docker.compose.project={self.project}", "--filter",
            f"label=com.docker.compose.service={service}"]).split()
        if len(candidates) != 1 or not re.fullmatch(r"[a-f0-9]{12,64}", candidates[0]):
            raise AcceptanceError("UNIQUE_STAGING_CONTAINER_REQUIRED")
        row = self.inspect(candidates[0])
        container_id = validate_inspection(row, self.project, service)
        if row["running"] is not True:
            raise AcceptanceError("STAGING_CONTAINER_MUST_START_RUNNING")
        self.ids[service] = container_id
        return container_id

    def checked_id(self, container_id, service):
        if self.ids.get(service) != container_id:
            raise AcceptanceError("CONTAINER_NOT_RESOLVED_BY_THIS_DRILL")
        row = self.inspect(container_id)
        if validate_inspection(row, self.project, service) != container_id:
            raise AcceptanceError("STAGING_CONTAINER_ID_CHANGED")
        return container_id

    def stop(self, container_id, service):
        self.checked_id(container_id, service)
        self.command(["stop", "--time", "1", container_id], timeout=20)

    def start(self, container_id, service):
        self.checked_id(container_id, service)
        self.command(["start", container_id], timeout=20)

    def snapshot(self, api_id):
        self.checked_id(api_id, "api")
        try:
            row = json.loads(self.command(["exec", api_id, "python", "-c", SNAPSHOT_CODE], timeout=25))
        except (ValueError, TypeError):
            raise AcceptanceError("INVALID_READ_ONLY_DB_SNAPSHOT") from None
        if (not isinstance(row, dict) or row.get("canonical_payloads_valid") is not True
                or any(type(row.get(key)) is not int or row[key] < 0
                       for key in ("collection_count", "audit_count"))
                or any(not isinstance(row.get(key), str) or not CONTAINER_ID.fullmatch(row[key])
                       for key in ("collection_registry_sha256", "audit_checkpoint_sha256"))):
            raise AcceptanceError("READ_ONLY_DB_SNAPSHOT_INVALID")
        return row


class FaultDrill:
    def __init__(self, args, client, account, docker):
        self.args, self.client, self.account, self.docker = args, client, account, docker
        self.ids = {}
        self.stopped = {}
        self.faults = []
        self.observe_payload = {"daemon_keys": args.daemon_key, "deep": False}

    def verify_marker(self):
        response = self.client.request("GET", "/api/runtime-config", self.account)
        expect_status(response, 200)
        validate_runtime_payload(response.json(), self.args.staging_project)
        return response.summary()

    def wait_ready(self):
        deadline = time.monotonic() + self.args.recovery_seconds
        attempts = []
        while True:
            response = self.client.request("GET", "/api/ready", self.account)
            attempts.append(response.summary())
            if response.status == 200 and response.json().get("ready") is True:
                return {"status": "PASS", "attempts": attempts}
            if time.monotonic() >= deadline:
                raise AcceptanceError("STAGING_READINESS_DID_NOT_RECOVER")
            time.sleep(.5)

    def restore(self, service, container_id):
        # The API may be stopped, making a new HTTP marker read impossible.
        # Recovery uses the previously verified marker and immutable original
        # ID, while rechecking exact project/service labels before every start.
        self.docker.start(container_id, service)
        self.stopped.pop(container_id, None)

    def fresh(self):
        requested = utc_now()
        response = self.client.request("POST", "/api/v1/as-is/observe", self.account, self.observe_payload)
        expect_status(response, 200)
        observation = validate_observation(response.json(), self.args.expected_fsid,
            self.args.daemon_key, requested, [])
        return {"http": response.summary(), **observation}

    @staticmethod
    def assertion(row, name, condition, detail):
        row["checks"].append({"name": name, "status": "PASS" if condition else "FAIL", "details": detail})

    def run_fault(self, service):
        started = time.monotonic()
        row = {"service": service, "started_at": utc_now(), "checks": []}
        container_id = self.ids[service]
        baseline = None
        request_pool = None
        request_future = None
        try:
            row["marker_before_stop"] = self.verify_marker()
            baseline = self.docker.snapshot(self.ids["api"])
            row["before"] = baseline
            if service == "api":
                request_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                request_future = request_pool.submit(self.client.request, "POST",
                    "/api/v1/as-is/observe", self.account, self.observe_payload)
                time.sleep(.5)
                if request_future.done():
                    raise AcceptanceError("LIVE_REQUEST_COMPLETED_BEFORE_API_FAULT")
            # Register recovery before invoking Docker: even a partial stop
            # command failure must not leave this exact container stopped.
            self.stopped[container_id] = service
            self.docker.stop(container_id, service)
            if service == "api":
                interrupted = request_future.result(timeout=self.args.timeout_seconds + 5)
                self.assertion(row, "inflight_live_request_interrupted",
                    interrupted.status is None or interrupted.status in {502, 503, 504}, interrupted.summary())
                down = self.client.request("GET", "/api/ready", self.account)
                self.assertion(row, "api_unavailable_is_not_ready",
                    down.status is None or down.status in {502, 503, 504}, down.summary())
            else:
                down = self.client.request("GET", "/api/ready", self.account)
                ready_payload = down.json() if down.status == 503 else {}
                expected_dependency = "database" if service == "postgres" else "ceph_executor"
                self.assertion(row, "dependency_not_ready",
                    down.status == 503 and ready_payload.get("ready") is False
                    and expected_dependency in ready_payload.get("blocking_dependencies", []),
                    {**down.summary(), "expected_dependency": expected_dependency})
                if service == "executor":
                    failed = self.client.request("POST", "/api/v1/as-is/observe", self.account, self.observe_payload)
                    self.assertion(row, "failed_source_is_bounded_not_stale_success",
                        failed.status in {503, 504} and failed.summary()["error_code"] is not None,
                        failed.summary())
                else:
                    failed = self.client.request("GET", "/api/v1/as-is/collections", self.account)
                    self.assertion(row, "history_failure_has_defined_diagnostic_not_empty_success",
                        failed.status is not None and 500 <= failed.status <= 599
                        and failed.summary()["error_code"] not in {None, "NON_JSON_RESPONSE"}, failed.summary())
        except AcceptanceError as exc:
            row["checks"].append({"name": "fault_operation", "status": "FAIL", "error_code": str(exc)})
        except Exception as exc:
            row["checks"].append({"name": "fault_operation", "status": "FAIL",
                                  "error_code": "FAULT_EXCEPTION_" + type(exc).__name__.upper()})
        finally:
            if container_id in self.stopped:
                try:
                    self.restore(service, container_id)
                    row["container_restarted"] = True
                except AcceptanceError as exc:
                    row["checks"].append({"name": "mandatory_container_restore", "status": "FAIL", "error_code": str(exc)})
            if request_pool:
                request_pool.shutdown(wait=True)
        if not self.stopped:
            try:
                row["recovery"] = self.wait_ready()
                row["marker_after_restore"] = self.verify_marker()
                recovered = self.docker.snapshot(self.ids["api"])
                row["after_restore"] = recovered
                self.assertion(row, "history_and_audit_unchanged", baseline == recovered,
                               {"identical": baseline == recovered})
                row["fresh_recovery"] = self.fresh()
                after_fresh = self.docker.snapshot(self.ids["api"])
                row["after_fresh"] = after_fresh
                self.assertion(row, "live_reads_never_auto_save_collections_or_audit", baseline == after_fresh,
                               {"identical": baseline == after_fresh})
            except AcceptanceError as exc:
                row["checks"].append({"name": "recovery", "status": "FAIL", "error_code": str(exc)})
        row.update(status="PASS" if row["checks"] and all(check["status"] == "PASS" for check in row["checks"]) else "FAIL",
                   duration_seconds=round(time.monotonic() - started, 4))
        self.faults.append(row)
        return row

    def run(self):
        started = time.monotonic()
        started_at = utc_now()
        initial = self.verify_marker()
        self.ids = {service: self.docker.resolve(service) for service in ("api", "postgres", "executor")}
        expect_status(self.client.request("GET", "/api/ready", self.account), 200)
        try:
            for service in ("executor", "postgres", "api"):
                self.run_fault(service)
                if self.stopped:
                    break
        finally:
            for container_id, service in list(self.stopped.items()):
                try:
                    self.restore(service, container_id)
                except AcceptanceError:
                    pass
        return {"kind": "PRODUCTION_STAGING_FAULT_DRILL", "started_at": started_at,
                "status": "PASS" if len(self.faults) == 3 and all(row["status"] == "PASS" for row in self.faults) and not self.stopped else "FAIL",
                "deployment_id": self.args.staging_project, "initial_marker": initial,
                "faults": self.faults, "http_events": self.client.events,
                "containers_still_requiring_restore": sorted(self.stopped.values()),
                "duration_seconds": round(time.monotonic() - started, 4),
                "threshold_policy": "PROPOSED_NOT_APPROVED_SLO",
                "not_production_signoff": True,
                "limitations": ["No remote SSH process cancellation or slow/lost SSH network was exercised.",
                    "No Ceph daemon, localhost lab deployment or unrelated container was changed.",
                    "Recovery starts rely on the pre-fault verified marker and rechecked exact original container labels/IDs."]}


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--base-url", required=True)
    command.add_argument("--staging-project", required=True)
    command.add_argument("--ca-file", required=True, type=Path)
    command.add_argument("--auth-user-file", required=True, type=Path)
    command.add_argument("--expected-fsid", required=True)
    command.add_argument("--daemon-key", required=True, action="append")
    command.add_argument("--allow-staging-faults", action="store_true")
    command.add_argument("--timeout-seconds", type=float, default=90)
    command.add_argument("--recovery-seconds", type=float, default=90)
    command.add_argument("--report", required=True, type=Path)
    return command


def validate_args(args):
    args.base_url = validate_target(args.base_url, args.staging_project)
    if not args.allow_staging_faults:
        raise AcceptanceError("EXPLICIT_STAGING_FAULT_AUTHORIZATION_REQUIRED")
    if not 30 <= args.timeout_seconds <= 120 or not 30 <= args.recovery_seconds <= 120:
        raise AcceptanceError("FAULT_TIMEOUT_MUST_BE_BOUNDED")
    if not 1 <= len(args.daemon_key) <= 2 or len(set(args.daemon_key)) != len(args.daemon_key) or any(not DAEMON_KEY.fullmatch(key) for key in args.daemon_key):
        raise AcceptanceError("ONE_OR_TWO_EXPLICIT_DAEMONS_REQUIRED")
    try:
        args.expected_fsid = str(UUID(args.expected_fsid))
    except (ValueError, TypeError):
        raise AcceptanceError("EXPECTED_FSID_REQUIRED") from None
    if args.report.exists():
        raise AcceptanceError("REFUSING_TO_OVERWRITE_FAULT_REPORT")


def main(argv=None):
    args = parser().parse_args(argv)
    report = {"kind": "PRODUCTION_STAGING_FAULT_DRILL", "status": "FAIL", "not_production_signoff": True}
    try:
        validate_args(args)
        accounts = load_accounts(args.auth_user_file, None, None, "admin")
        client = Client(args.base_url, args.ca_file, args.timeout_seconds)
        report = FaultDrill(args, client, accounts["admin"], DockerTarget(args.staging_project)).run()
    except AcceptanceError as exc:
        report["error_code"] = str(exc)
    except Exception as exc:
        report["error_code"] = "FAULT_EXCEPTION_" + type(exc).__name__.upper()
    if args.report.exists():
        print(json.dumps({"status": "FAIL", "error_code": "REFUSING_TO_OVERWRITE_FAULT_REPORT"}))
        return 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(canonical_bytes(report) + b"\n")
    print(json.dumps({"status": report["status"], "report": str(args.report)}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
