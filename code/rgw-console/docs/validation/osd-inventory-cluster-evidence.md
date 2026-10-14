# OSD inventory cluster evidence read path

Date: 2026-10-09 (Asia/Saigon)

## Implemented boundary

`GET /api/v1/osd-inventory/collections/{collection_id}/evidence` reads the
collection-level `cluster_evidence` and collection errors from the immutable
collector artifact. The client supplies only a collection UUID. The backend
looks up its registered `filesystem:` URI, expected size and SHA-256 from the
collection/evidence rows; arbitrary browser-supplied paths are not accepted.

The filesystem store rejects unsupported or absolute URIs, paths escaping
`EVIDENCE_ROOT`, non-files, oversized or size-mismatched content, SHA-256
mismatch, and invalid UTF-8 JSON. The service then revalidates schema, kind,
FSID, exact OSD scope, collector version and collection quality before returning
any content.

The response is a derived redacted view. Credential-shaped object fields,
sensitive Ceph config rows such as a `secret_key` option, and values following
config/keyring/secret argv flags are replaced with `[REDACTED]`. The stored
artifact is not modified. Per-OSD payload reads use the same response redactor.

## Automated evidence

- Focused artifact/service/API contract run: 10 tests passed.
- Full backend run: 202 discovered, 191 passed, 11 PostgreSQL-only skipped.
- Frontend contract run: 6 tests passed.
- Frontend production build completed; Vite transformed 1842 modules and
  emitted only the existing bundle-size advisory.

## Not claimed

- No collector was invoked against a live Ceph cluster.
- No stored artifact was read through a deployed PostgreSQL-backed console.
- PostgreSQL migration/repository integration remains unverified without
  `TEST_DATABASE_URL`.
- This endpoint is observational and does not authorize a Ceph mutation or an
  upgrade result.
