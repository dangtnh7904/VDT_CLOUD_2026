from __future__ import annotations

import unittest

from app.main import app


# Additive /api/v1 routes are allowed, but these compatibility facade routes
# must remain present while legacy RGW/RBD tools are moved behind module seams.
LEGACY_RGW_CONTRACT = {
    ("GET", "/api/health"),
    ("GET", "/api/buckets"),
    ("GET", "/api/corpora"),
    ("GET", "/api/corpora/{corpus_id}/browse"),
    ("POST", "/api/uploads/corpus"),
    ("POST", "/api/uploads/random"),
    ("POST", "/api/uploads/browser"),
    ("GET", "/api/objects"),
    ("GET", "/api/objects/head"),
    ("GET", "/api/objects/content"),
    ("PUT", "/api/objects/content"),
    ("PATCH", "/api/objects/metadata"),
    ("DELETE", "/api/objects"),
    ("POST", "/api/objects/bulk-delete"),
    ("GET", "/api/objects/versions"),
    ("POST", "/api/jobs"),
    ("GET", "/api/jobs"),
    ("POST", "/api/jobs/{job_id}/{action}"),
    ("GET", "/api/metrics"),
    ("GET", "/api/metrics/stream"),
}


class LegacyApiContractTests(unittest.TestCase):
    def test_existing_rgw_routes_are_not_removed_by_modularization(self):
        actual = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
            if method in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
        }

        self.assertEqual(LEGACY_RGW_CONTRACT - actual, set())

    def test_new_cluster_and_session_routes_are_versioned(self):
        # Included routers are lazily resolved in newer FastAPI releases; use
        # the public HTTP contract rather than its internal route containers.
        paths = app.openapi()["paths"]
        methods = {
            (method.upper(), path)
            for path, operations in paths.items()
            for method in operations
            if method in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
        }

        self.assertIn(("GET", "/api/live"), methods)
        self.assertIn(("GET", "/api/ready"), methods)
        self.assertIn(("GET", "/api/health/dependencies"), methods)

        self.assertIn("/api/v1/cluster/profile", paths)
        self.assertIn("/api/v1/cluster/capabilities", paths)
        self.assertIn("/api/v1/cluster/inventory", paths)
        self.assertIn("/api/v1/sessions", paths)
        self.assertIn("/api/v1/sessions/{session_id}", paths)
        self.assertIn("/api/v1/sessions/{session_id}/timeline", paths)
        self.assertIn("/api/v1/sessions/{session_id}/report", paths)
        self.assertFalse(any(path.startswith("/api/v1/upgrade-") or path.startswith("/api/v1/qos-") for path in paths))
        self.assertIn("/api/v1/as-is/observe", paths)
        self.assertIn("/api/v1/as-is/collections", paths)
        self.assertIn("/api/v1/as-is/compare", paths)
        self.assertIn("/api/v1/osdmap-previews", paths)
        self.assertIn("/api/v1/osd-inventory/collections", paths)
        self.assertIn("/api/v1/osd-inventory/collections/compare", paths)
        self.assertIn("/api/v1/osd-inventory/collections/compare-config", paths)
        self.assertIn(("GET", "/api/v1/sessions"), methods)
        self.assertIn(("POST", "/api/v1/sessions"), methods)
        self.assertIn(("GET", "/api/v1/osd-inventory/collections"), methods)
        self.assertIn(("POST", "/api/v1/osd-inventory/collections"), methods)
        self.assertIn("/api/v1/osd-inventory/collections/{collection_id}", paths)
        self.assertIn(
            "/api/v1/osd-inventory/collections/{collection_id}/evidence",
            paths,
        )
        self.assertIn(
            "/api/v1/osd-inventory/collections/{collection_id}/osds/{osd_id}",
            paths,
        )


if __name__ == "__main__":
    unittest.main()
