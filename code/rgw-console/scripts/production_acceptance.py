#!/usr/bin/env python3
"""Bounded COREreadonly acceptance checks against an explicitly marked staging API.

This client never runs Docker, SSH, Ceph commands or database statements. HTTPS
verification cannot be disabled. Saved test collections require a separate flag;
cleanup soft-deletes only IDs created by this invocation. Operational restart and
restore drills are performed separately by the deployment operator.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import math
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


DAEMON_KEY = re.compile(r"^(mon|mgr|osd|rgw|mds)\.[A-Za-z0-9_.-]{1,128}$")
ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
STAGING_PROJECT = re.compile(r"^storage-lab-console-staging(?:[-A-Za-z0-9_.]{0,80})$")
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class AcceptanceError(ValueError):
    """A stable, safe-to-report failure without remote response bodies."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def reject_constant(_value: str):
    raise ValueError("JSON_NONFINITE_NUMBER")


def read_json(content: bytes) -> Any:
    try:
        return json.loads(content, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AcceptanceError("INVALID_JSON_RESPONSE") from exc


def safe_error_code(payload: Any) -> str | None:
    detail = payload.get("detail", payload) if isinstance(payload, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else None
    return code if isinstance(code, str) and ERROR_CODE.fullmatch(code) else None


def validate_target(base_url: str, staging_project: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise AcceptanceError("INVALID_TARGET_PORT") from exc
    if (parsed.scheme != "https" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or (port is not None and not 1 <= port <= 65535)):
        raise AcceptanceError("TARGET_REQUIRES_HTTPS_LOOPBACK_WITHOUT_CREDENTIALS")
    if not STAGING_PROJECT.fullmatch(staging_project):
        raise AcceptanceError("EXPLICIT_STAGING_PROJECT_REQUIRED")
    return base_url.rstrip("/")


@dataclass(frozen=True, repr=False)
class Account:
    role: str
    username: str
    password: str

    def header(self) -> str:
        encoded = base64.b64encode(f"{self.username}:{self.password}".encode()).decode("ascii")
        return "Basic " + encoded


def read_password(path: Path) -> str:
    try:
        if not path.is_file() or path.stat().st_size > 4096:
            raise AcceptanceError("INVALID_PASSWORD_FILE")
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeError) as exc:
        raise AcceptanceError("PASSWORD_FILE_UNAVAILABLE") from exc
    if not value or "\n" in value or "\r" in value or "\0" in value:
        raise AcceptanceError("INVALID_PASSWORD_FILE")
    return value


def make_account(role: str, username: str, password: str) -> Account:
    if not isinstance(role, str) or role not in {"viewer", "operator", "admin"}:
        raise AcceptanceError("INVALID_ACCOUNT_ROLE")
    if (not isinstance(username, str) or not username or len(username) > 128
            or ":" in username or any(ord(char) < 32 for char in username)):
        raise AcceptanceError("INVALID_ACCOUNT_USERNAME")
    return Account(role, username, password)


def load_accounts(path: Path | None, username: str | None, password_file: Path | None,
                  role: str) -> dict[str, Account]:
    if path is None:
        if not username or password_file is None:
            raise AcceptanceError("CREDENTIAL_FILE_REQUIRED")
        return {role: make_account(role, username, read_password(password_file))}
    if username or password_file:
        raise AcceptanceError("CHOOSE_ONE_CREDENTIAL_FILE_FORMAT")
    try:
        if path.stat().st_size > 64 * 1024:
            raise AcceptanceError("ACCOUNT_FILE_TOO_LARGE")
        data = read_json(path.read_bytes())
    except OSError as exc:
        raise AcceptanceError("ACCOUNT_FILE_UNAVAILABLE") from exc
    rows = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
        raise AcceptanceError("INVALID_ACCOUNT_FILE")
    result: dict[str, Account] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"role", "username", "password_file"}:
            raise AcceptanceError("ACCOUNT_FILE_REQUIRES_PASSWORD_FILE_REFERENCES")
        if not isinstance(row["password_file"], str):
            raise AcceptanceError("INVALID_PASSWORD_FILE_REFERENCE")
        secret_path = Path(row["password_file"])
        if not secret_path.is_absolute():
            secret_path = path.parent / secret_path
        account = make_account(row["role"], row["username"], read_password(secret_path))
        if account.role in result:
            raise AcceptanceError("DUPLICATE_ACCOUNT_ROLE")
        result[account.role] = account
    if role not in result:
        raise AcceptanceError("REQUESTED_ACCOUNT_ROLE_MISSING")
    return result


@dataclass
class Response:
    status: int | None
    headers: dict[str, str]
    content: bytes
    elapsed_seconds: float
    error: str | None = None

    def json(self) -> Any:
        return read_json(self.content)

    def summary(self) -> dict[str, Any]:
        code = self.error
        if code is None and self.content:
            try:
                code = safe_error_code(self.json())
            except AcceptanceError:
                code = "NON_JSON_RESPONSE" if self.status != 200 else None
        return {"http_status": self.status, "error_code": code,
                "duration_seconds": round(self.elapsed_seconds, 4),
                "response_bytes": len(self.content)}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not follow any redirect with an Authorization header, even loopback.
        return None


class Client:
    def __init__(self, base_url: str, ca_file: Path, timeout: float):
        self.base_url = base_url
        self.timeout = timeout
        self.context = ssl.create_default_context(cafile=str(ca_file))
        self.events: list[dict] = []
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPSHandler(context=self.context))

    def remember(self, method: str, path: str, response: Response) -> Response:
        self.events.append({"method": method, "path": path.split("?", 1)[0], **response.summary()})
        return response

    def request(self, method: str, path: str, account: Account | None,
                payload: dict | None = None, *, extra_headers: dict | None = None) -> Response:
        if not path.startswith("/api/") or "\r" in path or "\n" in path:
            raise AcceptanceError("INVALID_API_PATH")
        headers = {"Accept": "application/json", "X-Console-Request": "1"}
        if account:
            headers["Authorization"] = account.header()
        headers.update(extra_headers or {})
        body = canonical_bytes(payload) if payload is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=body,
                                         headers=headers, method=method)
        start = time.monotonic()
        try:
            try:
                stream = self.opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                stream = exc
            with stream:
                content = stream.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    return self.remember(method, path, Response(stream.code, {}, b"", time.monotonic() - start,
                                                               "RESPONSE_TOO_LARGE"))
                response_headers = {key.lower(): value for key, value in stream.headers.items()}
                return self.remember(method, path, Response(stream.code, response_headers, content, time.monotonic() - start))
        except (TimeoutError, socket.timeout):
            return self.remember(method, path, Response(None, {}, b"", time.monotonic() - start, "CLIENT_TIMEOUT"))
        except ssl.SSLError:
            return self.remember(method, path, Response(None, {}, b"", time.monotonic() - start, "TLS_VERIFICATION_FAILED"))
        except urllib.error.URLError as exc:
            error = "TLS_VERIFICATION_FAILED" if isinstance(exc.reason, ssl.SSLError) else "NETWORK_UNAVAILABLE"
            return self.remember(method, path, Response(None, {}, b"", time.monotonic() - start, error))
        except OSError:
            return self.remember(method, path, Response(None, {}, b"", time.monotonic() - start, "NETWORK_UNAVAILABLE"))

    def abort_observation(self, account: Account, payload: dict, delay_seconds: float) -> dict:
        parsed = urllib.parse.urlsplit(self.base_url)
        body = canonical_bytes(payload)
        host_header = parsed.netloc
        lines = ["POST /api/v1/as-is/observe HTTP/1.1", f"Host: {host_header}",
                 "Content-Type: application/json", "X-Console-Request: 1",
                 f"Authorization: {account.header()}", f"Content-Length: {len(body)}",
                 "Connection: close", "", ""]
        start = time.monotonic()
        # TLS handshake is verified before sending any credentials.
        with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=self.timeout) as raw:
            with self.context.wrap_socket(raw, server_hostname=parsed.hostname) as connection:
                connection.sendall("\r\n".join(lines).encode("ascii") + body)
                time.sleep(delay_seconds)
                # Deliberately disconnect before reading the HTTP response. This
                # proves client behavior, not that a server-side slot was freed.
        return {"request_sent": True, "connection_closed_without_reading_response": True,
                "duration_seconds": round(time.monotonic() - start, 4)}


def expect_status(response: Response, status: int, code: str | None = None) -> None:
    if response.error or response.status != status:
        raise AcceptanceError(f"HTTP_EXPECTED_{status}_GOT_{response.status or 'NO_RESPONSE'}")
    if code is not None and safe_error_code(response.json()) != code:
        raise AcceptanceError("UNEXPECTED_DENIAL_CODE")


def verified_export(response: Response) -> dict:
    expect_status(response, 200)
    checksum = hashlib.sha256(response.content).hexdigest()
    if response.headers.get("x-export-sha256") != checksum:
        raise AcceptanceError("EXPORT_SHA256_MISMATCH")
    if not response.headers.get("content-disposition", "").startswith("attachment;"):
        raise AcceptanceError("EXPORT_ATTACHMENT_HEADER_MISSING")
    if response.headers.get("cache-control") != "no-store":
        raise AcceptanceError("EXPORT_CACHE_POLICY_INVALID")
    payload = response.json()
    if not isinstance(payload, dict):
        raise AcceptanceError("EXPORT_INVALID_OBJECT")
    return payload


def timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise AcceptanceError("INVALID_OBSERVATION_TIMESTAMP") from exc


def validate_observation(payload: Any, expected_fsid: str, daemon_keys: list[str],
                         requested_at: str, required_metrics: list[str]) -> dict:
    if not isinstance(payload, dict) or payload.get("kind") != "LIVE_OBSERVATION":
        raise AcceptanceError("LIVE_OBSERVATION_REQUIRED")
    if payload.get("fsid") != expected_fsid:
        raise AcceptanceError("FSID_MISMATCH")
    start, complete = timestamp(payload.get("started_at")), timestamp(payload.get("completed_at"))
    if complete < start or (timestamp(requested_at) - start).total_seconds() > 5:
        raise AcceptanceError("OBSERVATION_PREDATES_REQUEST")
    if (start - datetime.now(timezone.utc)).total_seconds() > 5:
        raise AcceptanceError("OBSERVATION_TIME_IN_FUTURE")
    if payload.get("freshness", {}).get("mode") != "READ_ON_REQUEST":
        raise AcceptanceError("READ_ON_REQUEST_REQUIRED")
    rows = payload.get("daemons")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise AcceptanceError("INVALID_DAEMON_ROWS")
    keys = [row.get("key") for row in rows]
    if (any(not isinstance(key, str) or not DAEMON_KEY.fullmatch(key) for key in keys)
            or len(keys) != len(set(keys)) or set(keys) != set(daemon_keys) or payload.get("missing_daemon_keys")):
        raise AcceptanceError("DAEMON_SCOPE_MISMATCH")
    if set(payload.get("requested_daemon_keys", [])) != set(daemon_keys):
        raise AcceptanceError("REQUESTED_DAEMON_SCOPE_MISMATCH")
    valid_metrics: set[str] = set()
    for row in rows:
        if row.get("type") != row["key"].split(".", 1)[0]:
            raise AcceptanceError("DAEMON_TYPE_MISMATCH")
        for metric in row.get("metrics", []):
            if not isinstance(metric, dict) or metric.get("quality") != "VALID":
                continue
            value = metric.get("value")
            if value is None or (isinstance(value, float) and not math.isfinite(value)):
                raise AcceptanceError("VALID_METRIC_VALUE_INVALID")
            if not metric.get("unit") or metric.get("kind") not in {"gauge", "counter", "rate"}:
                raise AcceptanceError("VALID_METRIC_UNIT_OR_KIND_MISSING")
            timestamp(metric.get("observed_at"))
            if metric.get("kind") == "rate" and not (
                    isinstance(metric.get("window_seconds"), (int, float))
                    and not isinstance(metric.get("window_seconds"), bool)
                    and math.isfinite(metric["window_seconds"]) and metric["window_seconds"] > 0):
                raise AcceptanceError("RATE_WINDOW_MISSING")
            valid_metrics.add(metric.get("metric_id"))
    if set(required_metrics) - valid_metrics:
        raise AcceptanceError("REQUIRED_METRICS_UNAVAILABLE")
    return {"observation_id": payload.get("id"), "quality": payload.get("quality"),
            "daemon_count": len(rows), "started_at": payload["started_at"],
            "completed_at": payload["completed_at"], "valid_metric_count": len(valid_metrics),
            "required_metrics": required_metrics}


def validate_saved(payload: Any, expected_fsid: str, daemon_keys: list[str]) -> str:
    if not isinstance(payload, dict) or payload.get("kind") != "AS_IS_COLLECTION":
        raise AcceptanceError("SAVED_COLLECTION_REQUIRED")
    if payload.get("fsid") != expected_fsid or set(payload.get("requested_daemon_keys", [])) != set(daemon_keys):
        raise AcceptanceError("SAVED_SCOPE_MISMATCH")
    try:
        collection_id = str(UUID(payload["id"]))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise AcceptanceError("INVALID_COLLECTION_ID") from exc
    original = {key: value for key, value in payload.items()
                if key not in {"sha256", "deleted_at", "artifact", "historical"}}
    if hashlib.sha256(canonical_bytes(original)).hexdigest() != payload.get("sha256"):
        raise AcceptanceError("SAVED_COLLECTION_SHA256_MISMATCH")
    if payload.get("artifact", {}).get("verified") is not True:
        raise AcceptanceError("SAVED_ARTIFACT_NOT_VERIFIED")
    return collection_id


def percentile95(values: list[float]) -> float | None:
    return sorted(values)[max(0, math.ceil(len(values) * .95) - 1)] if values else None


class Harness:
    def __init__(self, args, client: Client, accounts: dict[str, Account]):
        self.args, self.client, self.accounts = args, client, accounts
        self.account = accounts[args.auth_role]
        self.run_id = str(uuid4())
        self.created_ids: list[str] = []
        self.checks: list[dict] = []
        self.observe_payload = {"daemon_keys": args.daemon_key, "deep": False}

    def check(self, name, operation):
        start = time.monotonic()
        try:
            detail = operation()
            self.checks.append({"name": name, "status": "PASS", "details": detail,
                                "duration_seconds": round(time.monotonic() - start, 4)})
            return detail
        except AcceptanceError as exc:
            self.checks.append({"name": name, "status": "FAIL", "error_code": str(exc),
                                "duration_seconds": round(time.monotonic() - start, 4)})
            raise
        except Exception as exc:
            # Retain a stable local classification, never an exception message
            # containing SQL, URLs or source payloads. A malformed server schema
            # must still leave a report rather than terminating without evidence.
            code = "CHECK_EXCEPTION_" + type(exc).__name__.upper()
            self.checks.append({"name": name, "status": "FAIL", "error_code": code,
                                "duration_seconds": round(time.monotonic() - start, 4)})
            raise AcceptanceError(code) from None

    def runtime(self) -> dict:
        response = self.client.request("GET", "/api/runtime-config", self.account)
        expect_status(response, 200)
        payload = response.json()
        if (not isinstance(payload, dict) or payload.get("environment") != "production"
                or payload.get("deployment_scope") != "staging"
                or payload.get("deployment_id") != self.args.staging_project
                or payload.get("console_read_only") is not True):
            raise AcceptanceError("TARGET_IS_NOT_EXPLICIT_PRODUCTION_READONLY_STAGING")
        if any(payload.get("features", {}).get(key) is not False
               for key in ("upgrade", "lab", "legacy_rgw", "legacy_rbd")):
            raise AcceptanceError("MUTATION_FEATURES_NOT_DISABLED")
        role = payload.get("console_role")
        if role is not None and role != self.account.role:
            raise AcceptanceError("AUTHENTICATED_ROLE_MISMATCH")
        ready = self.client.request("GET", "/api/ready", self.account)
        expect_status(ready, 200)
        if ready.json().get("ready") is not True:
            raise AcceptanceError("TARGET_NOT_READY")
        return {"application_version": payload.get("application_version"),
                "environment": "production", "deployment_scope": "staging",
                "deployment_id": self.args.staging_project, "console_read_only": True,
                "role_verified": role is not None, "http": response.summary()}

    def guard(self) -> dict:
        unauthenticated = self.client.request("GET", "/api/runtime-config", None)
        expect_status(unauthenticated, 401, "CONSOLE_AUTH_REQUIRED")
        wrong = make_account(self.account.role, self.account.username, "invalid-" + str(uuid4()))
        bad_auth = self.client.request("GET", "/api/runtime-config", wrong)
        expect_status(bad_auth, 401, "CONSOLE_AUTH_REQUIRED")
        bad_origin = self.client.request("POST", "/api/v1/as-is/observe", self.account,
                                        self.observe_payload, extra_headers={"Origin": "https://rejected.invalid"})
        expect_status(bad_origin, 403, "CONSOLE_CSRF_REJECTED")
        mutation = self.client.request("POST", "/api/jobs", self.account, {})
        expect_status(mutation, 403, "CONSOLE_READ_ONLY")
        return {"unauthenticated": unauthenticated.summary(), "wrong_password": bad_auth.summary(),
                "bad_origin": bad_origin.summary(), "ceph_mutation_guard": mutation.summary()}

    def fresh(self, export=False, account=None) -> dict:
        requested = utc_now()
        response = self.client.request("POST", "/api/v1/as-is/export" if export else "/api/v1/as-is/observe",
                                       account or self.account, self.observe_payload)
        payload = verified_export(response) if export else response.json() if response.status == 200 else {}
        expect_status(response, 200)
        detail = validate_observation(payload, self.args.expected_fsid, self.args.daemon_key,
                                      requested, self.args.required_metric)
        return {**detail, "http": response.summary(),
                **({"export_sha256": hashlib.sha256(response.content).hexdigest()} if export else {})}

    def role_guards(self) -> dict:
        details = {}
        dummy_collection = "/api/v1/as-is/collections/00000000-0000-4000-8000-000000000000"
        if "viewer" in self.accounts:
            viewer = self.accounts["viewer"]
            response = self.client.request("POST", "/api/v1/as-is/observe", viewer, self.observe_payload)
            expect_status(response, 200)
            save = self.client.request("POST", "/api/v1/as-is/collections", viewer, {})
            expect_status(save, 403, "CONSOLE_ROLE_FORBIDDEN")
            delete = self.client.request("DELETE", dummy_collection, viewer)
            expect_status(delete, 403, "CONSOLE_ROLE_FORBIDDEN")
            details["viewer"] = {"read": response.summary(), "save_denied": save.summary(),
                                  "delete_denied": delete.summary()}
        if "operator" in self.accounts:
            delete = self.client.request("DELETE", dummy_collection, self.accounts["operator"])
            expect_status(delete, 403, "CONSOLE_ROLE_FORBIDDEN")
            details["operator"] = {"delete_denied": delete.summary()}
        if set(self.accounts) != {"viewer", "operator", "admin"}:
            details["coverage"] = "SINGLE_OR_PARTIAL_ACCOUNT_ROLE_COVERAGE"
        return details

    def collections(self) -> dict:
        ids, created = [], []
        writer = self.accounts.get("operator", self.account)
        for number in (1, 2):
            response = self.client.request("POST", "/api/v1/as-is/collections", writer,
                {"daemon_keys": self.args.daemon_key, "phase": "BEFORE",
                 "note": f"PRODUCTION_ACCEPTANCE_VALIDATION_ONLY_NO_UPGRADE:{self.run_id}:{number}"},
                extra_headers={"Idempotency-Key": f"acceptance-{self.run_id}-{number}"})
            expect_status(response, 201)
            payload = response.json()
            # Track an actual new ID before other verification so cleanup remains
            # possible if the payload's checksum is faulty.
            try:
                candidate = str(UUID(payload.get("id")))
            except (TypeError, ValueError, AttributeError):
                raise AcceptanceError("INVALID_CREATED_COLLECTION_ID") from None
            self.created_ids.append(candidate)
            collection_id = validate_saved(payload, self.args.expected_fsid, self.args.daemon_key)
            if payload.get("actor") != writer.username:
                raise AcceptanceError("COLLECTION_AUDIT_ACTOR_MISMATCH")
            ids.append(collection_id)
            created.append({"id": collection_id, "sha256": payload["sha256"],
                            "http": response.summary()})
        history = []
        for kind in sorted({key.split(".", 1)[0] for key in self.args.daemon_key}):
            query = urllib.parse.urlencode({"daemon_type": kind, "q": self.run_id, "limit": 10})
            response = self.client.request("GET", "/api/v1/as-is/collections?" + query, self.account)
            expect_status(response, 200)
            if {row.get("id") for row in response.json().get("items", [])} != set(ids):
                raise AcceptanceError("MIXED_COLLECTION_HISTORY_FILTER_MISMATCH")
            key = next(key for key in self.args.daemon_key if key.startswith(kind + "."))
            projection_query = urllib.parse.urlencode({"daemon_type": kind, "daemon_key": key})
            exported = self.client.request("GET", f"/api/v1/as-is/collections/{ids[0]}/export?" + projection_query,
                                           self.account)
            projected = verified_export(exported)
            if (projected.get("kind") != "FILTERED_AS_IS_EXPORT"
                    or [row.get("key") for row in projected.get("daemons", [])] != [key]
                    or projected.get("source_sha256") != created[0]["sha256"]):
                raise AcceptanceError("EXACT_DAEMON_PROJECTION_MISMATCH")
            history.append({"daemon_type": kind, "matching_created_ids": ids,
                            "projection_sha256": hashlib.sha256(exported.content).hexdigest(),
                            "http": response.summary()})
        kind = self.args.comparison_daemon_type or self.args.daemon_key[0].split(".", 1)[0]
        keys = [key for key in self.args.daemon_key if key.startswith(kind + ".")]
        if not keys:
            raise AcceptanceError("COMPARISON_TYPE_NOT_IN_SELECTED_SCOPE")
        compare = {"collection_a_id": ids[0], "collection_b_id": ids[1],
                   "daemon_type": kind, "daemon_keys": keys}
        response = self.client.request("POST", "/api/v1/as-is/compare", self.account, compare)
        expect_status(response, 200)
        comparison = response.json()
        if (comparison.get("kind") != "AS_IS_COMPARISON" or comparison.get("daemon_type") != kind
                or {row.get("key") for row in comparison.get("rows", [])} != set(keys)
                or comparison.get("fsid") != self.args.expected_fsid):
            raise AcceptanceError("COMPARISON_SCOPE_MISMATCH")
        exported = self.client.request("POST", "/api/v1/as-is/compare/export", self.account, compare)
        export_payload = verified_export(exported)
        if export_payload != comparison:
            raise AcceptanceError("COMPARISON_EXPORT_CHANGED_SAVED_DATA")
        other = next((key for key in self.args.daemon_key if not key.startswith(kind + ".")), None)
        cross_type = None
        if other:
            denial = self.client.request("POST", "/api/v1/as-is/compare", self.account,
                                         {**compare, "daemon_keys": [other]})
            expect_status(denial, 422, "COMPARISON_SCOPE_MISMATCH")
            cross_type = denial.summary()
        return {"created": created, "history_and_exact_projection": history,
                "same_type_comparison": response.summary(),
                "comparison_export_sha256": hashlib.sha256(exported.content).hexdigest(),
                "cross_type_denial": cross_type,
                "mixed_type_coverage": other is not None,
                "phases_are_test_metadata_only": True}

    def load(self) -> dict:
        def one(worker):
            rows = []
            for iteration in range(self.args.load_iterations):
                requested = utc_now()
                is_export = iteration % 2 == 1
                response = self.client.request("POST", "/api/v1/as-is/export" if is_export else "/api/v1/as-is/observe",
                                               self.account, self.observe_payload)
                record = {"worker": worker, "iteration": iteration, **response.summary()}
                if response.status == 200 and not response.error:
                    try:
                        payload = verified_export(response) if is_export else response.json()
                        validate_observation(payload, self.args.expected_fsid, self.args.daemon_key,
                                             requested, self.args.required_metric)
                        record["scope_and_freshness_verified"] = True
                    except AcceptanceError as exc:
                        record["error_code"] = str(exc)
                rows.append(record)
            return rows
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.args.load_workers) as pool:
            records = [row for group in pool.map(one, range(self.args.load_workers)) for row in group]
        busy = [row for row in records if row["http_status"] == 429 and row["error_code"] == "COLLECTION_BUSY"]
        successful = [row for row in records if row["http_status"] == 200 and row.get("scope_and_freshness_verified")]
        errors = len(records) - len(busy) - len(successful)
        p95 = percentile95([row["duration_seconds"] for row in successful])
        detail = {"requests": records, "total_requests": len(records), "successful": len(successful),
                  "queue_busy": len(busy), "unexpected_errors": errors,
                  "unexpected_error_ratio": errors / len(records),
                  "queue_busy_ratio": len(busy) / len(records), "p95_success_seconds": p95,
                  "policy_status": "PROPOSED_NOT_APPROVED_SLO"}
        self.load_details = detail
        if (detail["unexpected_error_ratio"] > self.args.max_error_ratio
                or detail["queue_busy_ratio"] > self.args.max_busy_ratio
                or p95 is None or p95 > self.args.max_p95_seconds):
            raise AcceptanceError("LOAD_ACCEPTANCE_THRESHOLD_EXCEEDED")
        return detail

    def abort_recovery(self) -> dict:
        try:
            abort = self.client.abort_observation(self.account, self.observe_payload, self.args.abort_after_seconds)
        except (OSError, ValueError):
            raise AcceptanceError("CLIENT_ABORT_SEND_FAILED") from None
        recovered = self.fresh()
        return {"client": abort, "fresh_request_after_disconnect": recovered,
                "server_slot_release_inferred_from_fresh_request": True,
                "server_disconnect_event_not_directly_observed": True}

    def cleanup(self) -> dict:
        if not self.created_ids:
            return {"soft_deleted_created_ids": []}
        if "admin" not in self.accounts:
            raise AcceptanceError("ADMIN_REQUIRED_TO_CLEAN_CREATED_COLLECTIONS")
        removed = []
        for collection_id in self.created_ids:
            response = self.client.request("DELETE", "/api/v1/as-is/collections/" + collection_id,
                                           self.accounts["admin"])
            expect_status(response, 200)
            if response.json().get("status") != "DELETED":
                raise AcceptanceError("CREATED_COLLECTION_SOFT_DELETE_FAILED")
            removed.append(collection_id)
        return {"soft_deleted_created_ids": removed, "preexisting_collections_touched": False}

    def run(self) -> dict:
        started = utc_now()
        try:
            self.check("staging_target_and_readiness", self.runtime)
            self.check("authentication_origin_and_ceph_guard", self.guard)
            self.check("fresh_observation", self.fresh)
            self.check("fresh_export_and_sha256", lambda: self.fresh(export=True))
            self.check("role_boundaries", self.role_guards)
            if self.args.allow_staging_metadata_writes:
                self.check("saved_collections_history_projection_comparison", self.collections)
            else:
                self.checks.append({"name": "saved_collections_history_projection_comparison",
                                    "status": "NOT_RUN", "reason": "STAGING_METADATA_WRITES_NOT_AUTHORIZED"})
            self.check("bounded_concurrent_load", self.load)
            if self.args.test_client_abort:
                self.check("client_disconnect_and_recovery", self.abort_recovery)
            else:
                self.checks.append({"name": "client_disconnect_and_recovery", "status": "NOT_RUN"})
        except AcceptanceError:
            pass  # Report the precise failed check; do not continue dependent writes.
        finally:
            if self.args.cleanup_created and self.created_ids:
                try:
                    self.check("cleanup_only_created_collections", self.cleanup)
                except AcceptanceError:
                    pass
        status = "FAIL" if any(check["status"] == "FAIL" for check in self.checks) else (
            "PARTIAL" if any(check["status"] == "NOT_RUN" for check in self.checks) else "PASS")
        return {"schema_version": 1, "kind": "CORE_READONLY_STAGING_ACCEPTANCE", "run_id": self.run_id,
                "started_at": started, "completed_at": utc_now(), "status": status,
                "not_a_production_signoff": True,
                "configuration": {"base_url": self.args.base_url, "staging_project": self.args.staging_project,
                    "tls_verification": "REQUIRED_WITH_SUPPLIED_CA", "roles_present": sorted(self.accounts),
                    "selected_daemon_count": len(self.args.daemon_key),
                    "selected_daemon_types": sorted({key.split(".", 1)[0] for key in self.args.daemon_key}),
                    "expected_fsid_sha256": hashlib.sha256(self.args.expected_fsid.encode()).hexdigest(),
                    "metadata_writes_authorized": self.args.allow_staging_metadata_writes,
                    "load_workers": self.args.load_workers, "load_iterations": self.args.load_iterations,
                    "thresholds": {"max_error_ratio": self.args.max_error_ratio,
                                   "max_busy_ratio": self.args.max_busy_ratio,
                                   "max_p95_seconds": self.args.max_p95_seconds,
                                   "policy_status": "PROPOSED_NOT_APPROVED_SLO"}},
                "checks": self.checks, "created_collection_ids": self.created_ids,
                "http_requests": getattr(self.client, "events", []),
                **({"load_failure_details": self.load_details} if hasattr(self, "load_details")
                   and any(c["name"] == "bounded_concurrent_load" and c["status"] == "FAIL" for c in self.checks) else {}),
                "not_covered": ["trusted_certificate_on_target_devices", "remote_linux_host_acceptance",
                    "operator_controlled_restart_fault_drills", "database_and_evidence_restore_drill",
                    "scheduled_backup_and_alert_delivery", "image_signature_and_supply_chain_policy",
                    "sustained_load_at_an_approved_production_SLO", "OSDMap_worker_acceptance"]}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    command.add_argument("--base-url", required=True, help="HTTPS localhost/127.0.0.1/[::1] staging ingress")
    command.add_argument("--ca-file", required=True, type=Path, help="Trusted staging CA/certificate PEM; verification is mandatory")
    command.add_argument("--staging-project", required=True, help="Exact runtime deployment_id, beginning storage-lab-console-staging")
    command.add_argument("--auth-user-file", type=Path, help='Private JSON: {"accounts":[{"role":"admin","username":"...","password_file":"..."}]}')
    command.add_argument("--auth-username", help="Compatibility single Basic username")
    command.add_argument("--auth-password-file", type=Path, help="Compatibility private single Basic password file")
    command.add_argument("--auth-role", choices=("viewer", "operator", "admin"), default="admin")
    command.add_argument("--expected-fsid", required=True)
    command.add_argument("--daemon-key", action="append", required=True, help="Explicit known daemon key; repeat for a mixed collection")
    command.add_argument("--required-metric", action="append", default=[], help="Metric ID required to be VALID with unit/time; repeat")
    command.add_argument("--comparison-daemon-type", choices=("mon", "mgr", "osd", "rgw", "mds"))
    command.add_argument("--allow-staging-metadata-writes", action="store_true", help="Create exactly two validation-only As-is collections")
    command.add_argument("--cleanup-created", action="store_true", help="Soft-delete only collections created by this run; admin account required")
    command.add_argument("--load-workers", type=int, default=2)
    command.add_argument("--load-iterations", type=int, default=2)
    command.add_argument("--max-error-ratio", type=float, default=0)
    command.add_argument("--max-busy-ratio", type=float, default=0)
    command.add_argument("--max-p95-seconds", type=float, default=60)
    command.add_argument("--timeout-seconds", type=float, default=420, help="Includes bounded deep collection time, default 420 seconds")
    command.add_argument("--test-client-abort", action="store_true")
    command.add_argument("--abort-after-seconds", type=float, default=.25)
    command.add_argument("--report", required=True, type=Path)
    return command


def validate_args(args) -> None:
    args.base_url = validate_target(args.base_url, args.staging_project)
    try:
        args.expected_fsid = str(UUID(args.expected_fsid))
    except ValueError as exc:
        raise AcceptanceError("EXPECTED_FSID_MUST_BE_UUID") from exc
    if (not 1 <= len(args.daemon_key) <= 10 or len(args.daemon_key) != len(set(args.daemon_key))
            or any(not DAEMON_KEY.fullmatch(key) for key in args.daemon_key)):
        raise AcceptanceError("ONE_TO_TEN_UNIQUE_EXPLICIT_DAEMON_KEYS_REQUIRED")
    if not 1 <= args.load_workers <= 8 or not 1 <= args.load_iterations <= 100:
        raise AcceptanceError("LOAD_LIMIT_REQUIRES_1_TO_8_WORKERS_AND_1_TO_100_ITERATIONS")
    if args.load_workers * args.load_iterations > 200:
        raise AcceptanceError("LOAD_REQUEST_COUNT_MUST_NOT_EXCEED_200")
    if any(not math.isfinite(value) or not 0 <= value <= 1
           for value in (args.max_error_ratio, args.max_busy_ratio)):
        raise AcceptanceError("ERROR_AND_BUSY_RATIOS_REQUIRE_ZERO_TO_ONE")
    if (not math.isfinite(args.max_p95_seconds) or not .1 <= args.max_p95_seconds <= 600
            or not math.isfinite(args.timeout_seconds) or not 5 <= args.timeout_seconds <= 600
            or not math.isfinite(args.abort_after_seconds) or not .05 <= args.abort_after_seconds <= 2):
        raise AcceptanceError("INVALID_BOUNDED_TIMEOUT")
    if args.cleanup_created and not args.allow_staging_metadata_writes:
        raise AcceptanceError("CLEANUP_REQUIRES_EXPLICIT_STAGING_METADATA_WRITE_FLAG")


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        validate_args(args)
        accounts = load_accounts(args.auth_user_file, args.auth_username, args.auth_password_file, args.auth_role)
        if args.cleanup_created and "admin" not in accounts:
            raise AcceptanceError("ADMIN_REQUIRED_TO_CLEAN_CREATED_COLLECTIONS")
        client = Client(args.base_url, args.ca_file, args.timeout_seconds)
        report = Harness(args, client, accounts).run()
    except (AcceptanceError, OSError, ssl.SSLError) as exc:
        code = str(exc) if isinstance(exc, AcceptanceError) else "LOCAL_CONFIGURATION_OR_CA_UNAVAILABLE"
        report = {"schema_version": 1, "kind": "CORE_READONLY_STAGING_ACCEPTANCE",
                  "status": "FAIL", "not_a_production_signoff": True, "error_code": code,
                  "completed_at": utc_now(), "checks": []}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(canonical_bytes(report) + b"\n")
    # Never print remote payloads or credentials; the report contains summaries.
    print(json.dumps({"status": report["status"], "report": str(args.report),
                      "failed_checks": [check["name"] for check in report["checks"] if check["status"] == "FAIL"]}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
