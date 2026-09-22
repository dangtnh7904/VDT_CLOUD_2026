import json
import unittest
from copy import deepcopy
from uuid import uuid4

from app.models.domain import (
    IdempotencyClaimRequest,
    IdempotencyDisposition,
    IdempotencyState,
)
from app.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyFenceLostError,
    IdempotencyService,
    canonical_request_fingerprint,
    redact_sensitive_data,
)


class FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=()):
        self.calls.append((query, params))
        if not self.rows:
            raise AssertionError("unexpected SQL call")
        return FakeCursor(self.rows.pop(0))

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def record(*, state="CLAIMED", fingerprint=None, generation=1, response_body=None):
    return {
        "id": 9,
        "scope": "rgw:lab",
        "idempotency_key": "key-1",
        "http_method": "PUT",
        "resource": "rgw://lab/jobs/a",
        "request_fingerprint": fingerprint or canonical_request_fingerprint(
            "PUT", "rgw://lab/jobs/a", {"size": 4}
        ),
        "state": state,
        "owner_id": "api-1",
        "fencing_generation": generation,
        "request_id": uuid4(),
        "action_id": None,
        "response_status": 200 if state == "SUCCEEDED" else None,
        "response_body": response_body,
        "error_code": None,
        "created_at": None,
        "updated_at": None,
        "completed_at": None,
    }


def claim_request(**overrides):
    values = {
        "scope": "rgw:lab",
        "idempotency_key": "key-1",
        "http_method": "put",
        "resource": "rgw://lab/jobs/a",
        "request_fingerprint": canonical_request_fingerprint(
            "PUT", "rgw://lab/jobs/a", {"size": 4}
        ),
        "owner_id": "api-1",
    }
    values.update(overrides)
    return IdempotencyClaimRequest(**values)


class FingerprintTests(unittest.TestCase):
    def test_mapping_order_method_case_and_header_case_are_canonical(self):
        first = canonical_request_fingerprint(
            "put",
            "rgw://lab/key",
            {"b": 2, "a": 1},
            headers={"Content-Type": "application/json"},
        )
        second = canonical_request_fingerprint(
            "PUT",
            "rgw://lab/key",
            {"a": 1, "b": 2},
            headers={"content-type": "application/json"},
        )

        self.assertEqual(first, second)
        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")

    def test_semantic_payload_change_changes_fingerprint(self):
        first = canonical_request_fingerprint("DELETE", "rgw://lab/key", {"version": "1"})
        second = canonical_request_fingerprint("DELETE", "rgw://lab/key", {"version": "2"})

        self.assertNotEqual(first, second)

    def test_non_json_unordered_values_are_rejected(self):
        with self.assertRaises(TypeError):
            canonical_request_fingerprint("PUT", "rgw://lab/key", {"items": {"a", "b"}})

    def test_invalid_content_digest_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_request_fingerprint(
                "PUT", "rgw://lab/key", {"size": 4}, content_sha256="not-a-digest"
            )

    def test_sensitive_response_fields_are_redacted_recursively(self):
        result = redact_sensitive_data(
            {"result": {"secret_key": "secret", "next_token": "allowed"}, "password": "pw"}
        )

        self.assertEqual(result["result"]["secret_key"], "[REDACTED]")
        self.assertEqual(result["password"], "[REDACTED]")
        self.assertEqual(result["result"]["next_token"], "allowed")


class IdempotencyServiceTests(unittest.TestCase):
    def test_first_claim_is_owned_and_executable(self):
        inserted = record()
        connection = FakeConnection([inserted])
        service = IdempotencyService(lambda: connection)

        result = service.claim(claim_request())

        self.assertEqual(result.disposition, IdempotencyDisposition.CLAIMED)
        self.assertTrue(result.should_execute)
        self.assertEqual(connection.commits, 1)

    def test_successful_request_is_replayed_without_execution(self):
        existing = record(state="SUCCEEDED", response_body={"ok": True})
        connection = FakeConnection([None, existing])
        service = IdempotencyService(lambda: connection)

        result = service.claim(claim_request())

        self.assertEqual(result.disposition, IdempotencyDisposition.REPLAY)
        self.assertFalse(result.should_execute)
        self.assertEqual(result.record.response_body, {"ok": True})

    def test_same_key_with_different_fingerprint_conflicts(self):
        existing = record(fingerprint=canonical_request_fingerprint("PUT", "other", {}))
        connection = FakeConnection([None, existing])
        service = IdempotencyService(lambda: connection)

        with self.assertRaises(IdempotencyConflictError):
            service.claim(claim_request())

        self.assertEqual(connection.rollbacks, 1)

    def test_retryable_failure_gets_new_fencing_generation(self):
        failed = record(state="FAILED_RETRYABLE", generation=3)
        reclaimed = deepcopy(failed)
        reclaimed.update(state="CLAIMED", fencing_generation=4, owner_id="api-2")
        connection = FakeConnection([None, failed, reclaimed])
        service = IdempotencyService(lambda: connection)

        result = service.claim(claim_request(owner_id="api-2"))

        self.assertEqual(result.disposition, IdempotencyDisposition.RETRY_CLAIMED)
        self.assertEqual(result.record.fencing_generation, 4)
        self.assertTrue(result.should_execute)

    def test_mark_in_progress_rejects_lost_fence(self):
        connection = FakeConnection([None])
        service = IdempotencyService(lambda: connection)

        with self.assertRaises(IdempotencyFenceLostError):
            service.mark_in_progress(
                "rgw:lab", "key-1", owner_id="old-worker", fencing_generation=1
            )

        self.assertEqual(connection.rollbacks, 1)

    def test_finish_stores_only_redacted_json(self):
        completed = record(state="SUCCEEDED", response_body={"secret_key": "[REDACTED]"})
        connection = FakeConnection([completed])
        service = IdempotencyService(lambda: connection)

        service.finish(
            "rgw:lab",
            "key-1",
            owner_id="api-1",
            fencing_generation=1,
            state=IdempotencyState.SUCCEEDED,
            response_status=200,
            response_body={"secret_key": "must-not-persist", "etag": "abc"},
        )

        stored_json = connection.calls[0][1][2]
        self.assertEqual(json.loads(stored_json)["secret_key"], "[REDACTED]")
        self.assertNotIn("must-not-persist", stored_json)


if __name__ == "__main__":
    unittest.main()
