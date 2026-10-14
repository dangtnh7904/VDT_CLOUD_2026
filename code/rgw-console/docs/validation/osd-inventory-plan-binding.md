# OSD inventory plan-binding validation

Date: 2026-10-09 (Asia/Saigon)

## Implemented contract

- `POST /api/v1/upgrade-runs/{run_id}/inventory-bindings` accepts an immutable
  collection ID plus expected state, plan/config/resource revisions, operator
  reason and idempotency key.
- Only a complete, `VALID`, `BEFORE` collection from the same cluster, FSID,
  session and config snapshot is eligible.
- Every source and destination OSD in the persisted batch must have a `VALID`
  record. Superset collections are allowed; missing plan OSDs are not.
- Artifact SHA-256 and timezone-aware collection time are mandatory. Future or
  older-than-policy timestamps fail closed.
- `GET /api/v1/upgrade-runs/{run_id}/inventory-readiness` recomputes age using
  the current clock. It returns `READY`, `HOLD`, `BLOCKED` or `INCONCLUSIVE`
  with machine-readable reasons.
- Dry-run preflight embeds this decision in its evidence artifact and stores the
  binding foreign key on the placement plan. Non-ready evidence keeps
  `execution_readiness` blocked and never changes `operation_result` from
  `NOT_EXERCISED`.

## Automated evidence

- Domain tests cover fresh READY, stale HOLD, FSID mismatch, missing plan OSDs,
  invalid quality and unbound runs.
- Service tests prove stale evidence is rejected before repository write.
- Route and forward-only migration contracts cover binding migration 0017;
  the current contiguous schema reaches version 18.
- Full backend result: 191 discovered, 180 passed, 11 PostgreSQL-only skipped.
- Frontend result: 5 passed and production build completed.

## Not claimed

- PostgreSQL application of migration 0017 was not run without
  `TEST_DATABASE_URL`.
- No live Ceph collection or production down-set was executed.
- The current live-mutation surface remains disabled; an eventual down-set
  command must call the readiness gate again inside its fenced transaction.

## Follow-on phase comparison

The additive comparison endpoint now computes raw indexed-field differences
between `BEFORE` and `AFTER_START`/`AFTER_STABLE` collections, including the
topology, BlueStore-role and container-image fields indexed by migration 0018.
It preserves the overlapping raw diff even when scope mismatch makes the pair
`NOT_COMPARABLE`, treats device/address lists as order-insensitive, and never
emits production PASS/FAIL. The focused comparison cases and complete backend
suite pass.

The separate pre-down-set inventory endpoint rechecks a fresh full-allowlist
snapshot against current run concurrency tokens. Its inventory result can be
`READY`, but mutation readiness remains explicitly `BLOCKED` until the PG,
health, lease/fence and live-action gates exist and pass.
