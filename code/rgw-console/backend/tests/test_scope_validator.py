import unittest
from uuid import uuid4

from app.models.domain import RgwScopeTarget
from app.services.scope_validator import InvalidScopeError, ScopeValidator


class ScopeValidatorTests(unittest.TestCase):
    def test_empty_bucket_allowlist_fails_closed(self):
        validator = ScopeValidator(allowed_buckets=(), stream_prefix_root="jobs/")

        with self.assertRaisesRegex(InvalidScopeError, "allowlist is not configured"):
            validator.require_bucket("lab")

    def test_all_reads_and_writes_require_allowed_bucket(self):
        validator = ScopeValidator(allowed_buckets={"lab"}, stream_prefix_root="jobs/")

        self.assertEqual(validator.require_bucket("lab"), "lab")
        with self.assertRaises(InvalidScopeError):
            validator.require_prefix("production", "")
        with self.assertRaises(InvalidScopeError):
            validator.require_key("production", "safe/key")

    def test_manual_scope_can_list_bucket_root(self):
        validator = ScopeValidator(allowed_buckets={"lab"}, stream_prefix_root="jobs/")

        self.assertEqual(validator.require_prefix("lab", ""), "")

    def test_stream_scope_is_boundary_checked(self):
        validator = ScopeValidator(allowed_buckets={"lab"}, stream_prefix_root="jobs/")

        self.assertEqual(
            validator.require_key("lab", "jobs/run-1/object.bin", streaming=True),
            "jobs/run-1/object.bin",
        )
        with self.assertRaisesRegex(InvalidScopeError, "outside"):
            validator.require_key("lab", "jobs-escaped/object.bin", streaming=True)

    def test_missing_stream_root_fails_closed(self):
        validator = ScopeValidator(allowed_buckets={"lab"}, stream_prefix_root="")

        with self.assertRaisesRegex(InvalidScopeError, "not configured"):
            validator.require_key("lab", "jobs/object.bin", streaming=True)

    def test_unsafe_path_segments_are_rejected(self):
        validator = ScopeValidator(allowed_buckets={"lab"}, stream_prefix_root="jobs/")

        for key in ("../object", "safe/../object", "/absolute", "safe//object", "safe\\object"):
            with self.subTest(key=key), self.assertRaises(InvalidScopeError):
                validator.require_key("lab", key)

    def test_build_stream_prefix_keeps_relative_input_inside_root(self):
        validator = ScopeValidator(allowed_buckets={"lab"}, stream_prefix_root="jobs")

        self.assertEqual(validator.build_stream_prefix(), "jobs/")
        self.assertEqual(validator.build_stream_prefix("run-1"), "jobs/run-1/")
        with self.assertRaises(InvalidScopeError):
            validator.build_stream_prefix("../production")

    def test_target_cannot_mix_key_and_prefix(self):
        validator = ScopeValidator(allowed_buckets={"lab"}, stream_prefix_root="jobs/")
        target = RgwScopeTarget(bucket="lab", key="jobs/a", prefix="jobs/", streaming=True)

        with self.assertRaises(InvalidScopeError):
            validator.validate_rgw_target(target)

    def test_invalid_scope_maps_to_stable_api_error(self):
        error = InvalidScopeError("outside", observed_state={"scope": "RGW_BUCKET"})
        request_id = uuid4()

        detail = error.as_error_detail(request_id)

        self.assertEqual(detail.request_id, request_id)
        self.assertEqual(detail.code, "INVALID_SCOPE")
        self.assertFalse(detail.retryable)


if __name__ == "__main__":
    unittest.main()
