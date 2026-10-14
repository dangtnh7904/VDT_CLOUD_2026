"""Client safety checks run without an API, Docker or a Ceph cluster."""
from __future__ import annotations

import copy
import hashlib
from http.client import BadStatusLine, IncompleteRead
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "production_acceptance.py"
spec = importlib.util.spec_from_file_location("production_acceptance", SCRIPT)
acceptance = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = acceptance
spec.loader.exec_module(acceptance)
FSID = "11111111-2222-4333-8444-555555555555"
ID = "11111111-2222-4333-8444-555555555556"


def response(payload, *, status=200, headers=None):
    return acceptance.Response(status, headers or {}, acceptance.canonical_bytes(payload), .1)


def observation():
    at = acceptance.utc_now()
    return {"kind": "LIVE_OBSERVATION", "id": ID, "fsid": FSID,
            "started_at": at, "completed_at": at,
            "freshness": {"mode": "READ_ON_REQUEST"}, "quality": "PARTIAL",
            "missing_daemon_keys": [], "requested_daemon_keys": ["osd.2"],
            "daemons": [{"key": "osd.2", "type": "osd", "metrics": [
                {"metric_id": "osd.utilization_percent", "value": 20, "quality": "VALID",
                 "unit": "percent", "kind": "gauge", "observed_at": at}]}]}


def arguments(*extra):
    args = acceptance.parser().parse_args([
        "--base-url", "https://localhost:8446", "--ca-file", "test-ca.pem",
        "--staging-project", "storage-lab-console-staging-test", "--expected-fsid", FSID,
        "--daemon-key", "osd.2", "--auth-username", "test-admin",
        "--auth-password-file", "password.txt", "--report", "test-report.json", *extra])
    acceptance.validate_args(args)
    return args


class SafetyTests(unittest.TestCase):
    def test_http_protocol_failure_has_stable_code_no_remote_fragments(self):
        client = acceptance.Client.__new__(acceptance.Client)
        client.base_url = 'https://localhost:8446'
        client.timeout = 1
        client.events = []
        client.opener = Mock()
        client.opener.open.side_effect = BadStatusLine('fake-password-or-response')
        result = client.request('GET', '/api/ready', None)
        self.assertEqual(result.error, 'HTTP_PROTOCOL_INVALID')
        self.assertIsNone(result.status)
        self.assertEqual(result.content, b'')
        self.assertNotIn('fake-password', json.dumps(client.events))

    def test_incomplete_http_body_keeps_observed_status_without_partial_body(self):
        client = acceptance.Client.__new__(acceptance.Client)
        client.base_url = 'https://localhost:8446'
        client.timeout = 1
        client.events = []
        stream = Mock(code=503)
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=None)
        stream.read.side_effect = IncompleteRead(b'fake-private-partial-body')
        client.opener = Mock()
        client.opener.open.return_value = stream
        result = client.request('GET', '/api/ready', None)
        self.assertEqual(result.error, 'HTTP_PROTOCOL_INVALID')
        self.assertEqual(result.status, 503)
        self.assertEqual(result.content, b'')
        self.assertNotIn('fake-private', json.dumps(client.events))

    def test_failed_observation_keeps_source_codes_not_values_or_messages(self):
        payload = observation()
        payload['sources'] = {'ceph.osd_df': {'quality':'UNAVAILABLE','reason':'EXECUTOR_TIMEOUT','message':'password=secret'},
                              'prometheus': {'quality':'PARTIAL','reason':'https://private/secret','http_status':200}}
        payload['missing_daemon_keys'] = ['mon.example']
        payload['daemons'][0]['metrics'][0].update(quality='UNAVAILABLE',reason='EXECUTOR_TIMEOUT',value='password=secret')
        result = acceptance.observation_failure_diagnostics(payload, ['osd.utilization_percent'])
        self.assertEqual(result['nonvalid_sources'][0]['reason'],'EXECUTOR_TIMEOUT')
        self.assertEqual(result['missing_daemon_keys'],['mon.example'])
        self.assertNotIn('secret',json.dumps(result))
        self.assertNotIn('https',json.dumps(result))

    def test_failed_observation_malformed_rows_cannot_mask_original_failure(self):
        result = acceptance.observation_failure_diagnostics({'daemons':[None, {'key':'osd.2','metrics':{}}],
                                                               'sources':None,'missing_daemon_keys':None}, [])
        self.assertEqual(result['actual_daemon_keys'],['osd.2'])
        self.assertEqual(result['required_metric_quality'],[])

    def test_target_rejects_plain_http_remote_userinfo_or_nonstaging(self):
        for target in ("http://localhost:8446", "https://example.test", "https://user:secret@localhost",
                       "https://localhost/path", "https://localhost?secret=yes", "https://localhost:99999",
                       "https://127.0.0.1#secret"):
            with self.subTest(target=target), self.assertRaises(acceptance.AcceptanceError):
                acceptance.validate_target(target, "storage-lab-console-staging-test")
        with self.assertRaises(acceptance.AcceptanceError):
            acceptance.validate_target("https://localhost", "storage-lab-console-production")
        self.assertEqual(acceptance.validate_target("https://[::1]:8446/", "storage-lab-console-staging-test"),
                         "https://[::1]:8446")

    def test_no_redirect_can_leak_an_authorization_header(self):
        handler = acceptance.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://attacker.invalid"))

    def test_response_summary_never_contains_server_message_or_secret(self):
        result = response({"detail": {"code": "DATABASE_UNAVAILABLE", "message": "password=top-secret"}})
        self.assertEqual(result.summary()["error_code"], "DATABASE_UNAVAILABLE")
        self.assertNotIn("secret", json.dumps(result.summary()))
        result = response({"detail": {"code": "password=top-secret"}})
        self.assertIsNone(result.summary()["error_code"])

    def test_account_files_reference_separate_secrets_and_do_not_print_passwords(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "password.txt").write_text("private-account-password\n", encoding="utf-8")
            config = root / "accounts.json"
            config.write_text(json.dumps({"accounts": [{"role": "admin", "username": "test-admin",
                                                        "password_file": "password.txt"}]}), encoding="utf-8")
            accounts = acceptance.load_accounts(config, None, None, "admin")
            self.assertEqual(accounts["admin"].password, "private-account-password")
            self.assertNotIn("private-account-password", repr(accounts["admin"]))
            config.write_text(json.dumps({"accounts": [{"role": "admin", "username": "test-admin",
                                                        "password": "not-allowed"}]}), encoding="utf-8")
            with self.assertRaises(acceptance.AcceptanceError):
                acceptance.load_accounts(config, None, None, "admin")

    def test_duplicate_roles_and_conflicting_credential_forms_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "password.txt").write_text("private-account-password", encoding="utf-8")
            config = root / "accounts.json"
            row = {"role": "admin", "username": "test-admin", "password_file": "password.txt"}
            config.write_text(json.dumps({"accounts": [row, row]}), encoding="utf-8")
            with self.assertRaises(acceptance.AcceptanceError):
                acceptance.load_accounts(config, None, None, "admin")
            with self.assertRaises(acceptance.AcceptanceError):
                acceptance.load_accounts(config, "admin", root / "password.txt", "admin")

    def test_load_and_collection_limits_are_bounded(self):
        for options in (("--load-workers", "9"), ("--load-iterations", "101"),
                        ("--max-error-ratio", "nan"), ("--timeout-seconds", "601"),
                        ("--abort-after-seconds", "5"), ("--cleanup-created",)):
            with self.subTest(options=options), self.assertRaises(acceptance.AcceptanceError):
                arguments(*options)
        with self.assertRaises(acceptance.AcceptanceError):
            arguments("--daemon-key", "osd.2")

    def test_nonfinite_json_is_not_accepted(self):
        with self.assertRaises(acceptance.AcceptanceError):
            acceptance.read_json(b'{"value":NaN}')


class EvidenceTests(unittest.TestCase):
    def test_export_checks_the_received_bytes_and_attachment_headers(self):
        payload = observation()
        result = response(payload)
        result.headers = {"x-export-sha256": hashlib.sha256(result.content).hexdigest(),
                          "content-disposition": 'attachment; filename="test.json"',
                          "cache-control": "no-store"}
        self.assertEqual(acceptance.verified_export(result), payload)
        result.content += b" "
        with self.assertRaisesRegex(acceptance.AcceptanceError, "EXPORT_SHA256_MISMATCH"):
            acceptance.verified_export(result)

    def test_observation_requires_exact_scope_fsid_and_recent_source(self):
        payload = observation()
        requested = acceptance.utc_now()
        result = acceptance.validate_observation(payload, FSID, ["osd.2"], requested,
                                                 ["osd.utilization_percent"])
        self.assertEqual(result["daemon_count"], 1)
        for mutation in (
            lambda item: item.update(fsid="other"),
            lambda item: item.update(missing_daemon_keys=["osd.2"]),
            lambda item: item["daemons"].append(item["daemons"][0]),
            lambda item: item.update(requested_daemon_keys=["osd.3"]),
            lambda item: item["freshness"].update(mode="SNAPSHOT"),
            lambda item: item.update(started_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()),
            lambda item: item["daemons"][0]["metrics"][0].update(quality="STALE"),
        ):
            item = copy.deepcopy(payload)
            mutation(item)
            with self.assertRaises(acceptance.AcceptanceError):
                acceptance.validate_observation(item, FSID, ["osd.2"], requested,
                                                 ["osd.utilization_percent"])

    def test_rate_requires_positive_window_and_valid_timestamp(self):
        payload = observation()
        metric = payload["daemons"][0]["metrics"][0]
        metric.update(kind="rate")
        with self.assertRaisesRegex(acceptance.AcceptanceError, "RATE_WINDOW_MISSING"):
            acceptance.validate_observation(payload, FSID, ["osd.2"], acceptance.utc_now(), [])
        metric["window_seconds"] = 1
        acceptance.validate_observation(payload, FSID, ["osd.2"], acceptance.utc_now(), [])
        metric["observed_at"] = "2000-01-01"
        with self.assertRaises(acceptance.AcceptanceError):
            acceptance.validate_observation(payload, FSID, ["osd.2"], acceptance.utc_now(), [])

    def test_saved_collection_integrity_checks_parent_payload(self):
        payload = observation()
        payload.update(kind="AS_IS_COLLECTION", phase="BEFORE", actor="test-operator")
        checksum = hashlib.sha256(acceptance.canonical_bytes(payload)).hexdigest()
        payload.update(sha256=checksum, deleted_at=None, artifact={"verified": True}, historical=True)
        self.assertEqual(acceptance.validate_saved(payload, FSID, ["osd.2"]), ID)
        payload["phase"] = "AFTER"
        with self.assertRaisesRegex(acceptance.AcceptanceError, "SAVED_COLLECTION_SHA256_MISMATCH"):
            acceptance.validate_saved(payload, FSID, ["osd.2"])

    def test_p95_nearest_rank(self):
        self.assertIsNone(acceptance.percentile95([]))
        self.assertEqual(acceptance.percentile95([2, 1]), 2)
        self.assertEqual(acceptance.percentile95(list(range(1, 21))), 19)


class HarnessTests(unittest.TestCase):
    def test_collector_feature_is_not_mutation_authority_and_missing_gate_fails_closed(self):
        args = arguments()
        for mutation_gate in (False, True, None):
            class FakeClient:
                def request(self, method, path, account, payload=None, **kwargs):
                    if path == '/api/ready': return response({'ready': True})
                    return response({'environment': 'production', 'deployment_scope': 'staging',
                        'deployment_id': args.staging_project, 'console_read_only': True,
                        'ceph_mutations_enabled': mutation_gate, 'console_role': 'admin',
                        'features': {'upgrade': True, 'lab': False, 'legacy_rgw': False, 'legacy_rbd': False}})
            harness = acceptance.Harness(args, FakeClient(), {'admin': self.account()})
            with self.subTest(mutations=mutation_gate):
                if mutation_gate is False: self.assertTrue(harness.runtime()['console_read_only'])
                else:
                    with self.assertRaisesRegex(acceptance.AcceptanceError, 'MUTATION_FEATURES_NOT_DISABLED'): harness.runtime()

    def account(self):
        return acceptance.Account("admin", "test-admin", "secret-not-in-report")

    def test_incorrect_runtime_marker_stops_before_mutation_probe_or_collections(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, path, account, payload=None, **kwargs):
                self.calls.append((method, path))
                return response({"environment": "production", "deployment_scope": "production",
                                 "console_read_only": True})

        client = FakeClient()
        args = arguments("--allow-staging-metadata-writes")
        harness = acceptance.Harness(args, client, {"admin": self.account()})
        report = harness.run()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(client.calls, [("GET", "/api/runtime-config")])
        self.assertNotIn("secret-not-in-report", json.dumps(report))

    def test_cleanup_is_limited_to_run_ids_and_requires_admin(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, path, account, payload=None, **kwargs):
                self.calls.append((method, path))
                return response({"status": "DELETED"})

        client = FakeClient()
        harness = acceptance.Harness(arguments(), client, {"admin": self.account()})
        harness.created_ids = [ID]
        self.assertEqual(harness.cleanup()["soft_deleted_created_ids"], [ID])
        self.assertEqual(client.calls, [("DELETE", "/api/v1/as-is/collections/" + ID)])
        harness.accounts = {}
        with self.assertRaisesRegex(acceptance.AcceptanceError, "ADMIN_REQUIRED"):
            harness.cleanup()
        self.assertEqual(len(client.calls), 1)

    def test_load_retains_http_status_and_busy_separately_from_unexpected_errors(self):
        class FakeClient:
            def request(self, method, path, account, payload=None, **kwargs):
                return response({"detail": {"code": "COLLECTION_BUSY", "message": "private"}}, status=429)

        harness = acceptance.Harness(arguments(), FakeClient(), {"admin": self.account()})
        with self.assertRaisesRegex(acceptance.AcceptanceError, "LOAD_ACCEPTANCE_THRESHOLD_EXCEEDED"):
            harness.load()
        detail = harness.load_details
        self.assertEqual(detail["queue_busy"], 4)
        self.assertEqual(detail["unexpected_errors"], 0)
        self.assertTrue(all(row["http_status"] == 429 for row in detail["requests"]))
        self.assertNotIn("private", json.dumps(detail))


if __name__ == "__main__":
    unittest.main()
