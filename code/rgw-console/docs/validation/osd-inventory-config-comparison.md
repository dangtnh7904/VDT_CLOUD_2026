# OSD inventory configuration evidence comparison

Date: 2026-10-09 (Asia/Saigon)

## Implemented boundary

`GET /api/v1/osd-inventory/collections/compare-config` compares a `BEFORE`
collection with an `AFTER_START` or `AFTER_STABLE` collection. It is separate
from the indexed OSD-field comparator, so artifact failure cannot silently
change the earlier API contract.

Both artifacts pass the same path-containment, byte-count, SHA-256, FSID,
collector schema, exact OSD-scope and metadata checks used by the evidence read
endpoint. Only then does the comparator inspect:

- cluster-wide `ceph config dump` evidence; and
- per-OSD `ceph config show-with-defaults` evidence.

Dictionary key order and config-dump row order are not changes. Added, removed
and changed options are reported separately for cluster scope and each OSD.
Missing/failed config commands produce `INCONCLUSIVE`; cluster/session/config
snapshot, phase or OSD-scope mismatch remains `NOT_COMPARABLE`. These statuses
describe evidence comparability and never become an upgrade PASS/FAIL result.

Sensitive values are compared from the verified source artifact so secret
rotation is still visible as a change. The response contains `[REDACTED]` for
both sides and does not expose a secret-derived hash. Artifacts remain
append-only and unchanged.

## Automated evidence

- Focused comparator/service/API-contract run: 12 tests passed.
- Full backend run: 202 discovered, 191 passed, 11 PostgreSQL-only skipped.
- Frontend contract run: 6 tests passed.
- Frontend production build completed with the existing bundle-size advisory.

## Not claimed

- No live Ceph config database was compared.
- PostgreSQL-backed artifact lookup remains unverified without
  `TEST_DATABASE_URL`.
- Config drift is observational evidence, not mutation authorization or an
  upgrade verdict.
