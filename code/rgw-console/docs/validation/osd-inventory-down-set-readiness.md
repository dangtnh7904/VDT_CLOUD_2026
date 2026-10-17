# OSD inventory down-set readiness

## Scope

This slice adds a pure, read-only decision for the inventory input used
immediately before a planned OSD down-set. It does not execute, schedule, or
authorize any Ceph mutation.

The domain implementation is in
`backend/app/modules/osd_info_collector/down_set_readiness.py`. The application
binding is in `backend/app/modules/upgrade_common/down_set_assessment.py`.
Focused coverage lives in:

- `backend/tests/test_osd_info_down_set_readiness.py`
- `backend/tests/test_down_set_assessment_service.py`

## Decision contract

The evaluator returns two deliberately separate results:

- `inventory_result`: `READY`, `HOLD`, `BLOCKED`, or `INCONCLUSIVE`.
- `mutation_readiness`: always `BLOCKED` in this slice.

An `inventory_result` of `READY` only means that the supplied collector artifact
is fresh, complete, cluster-wide, internally valid, and that the projected set
of unavailable OSDs does not exceed `max_simultaneous_down`.

The result always carries these limitations:

- `PG_UP_ACTING_RECHECK_REQUIRED`
- `CLUSTER_HEALTH_RECHECK_REQUIRED`
- `LEASE_AND_FENCE_REQUIRED`
- `LIVE_MUTATION_DISABLED`

This separation prevents a fresh inventory artifact from being mistaken for an
execution permit.

## Fail-closed checks

The inventory decision verifies:

1. target OSDs are non-empty and belong to the upgrade run source set;
2. cluster ID, FSID, session, and config snapshot match the run;
3. collection phase is `BEFORE` or `DURING`;
4. run source, target, requested scope, and record scope remain inside and
   exactly match the configured allowlist where required;
5. collection is `COMPLETE`, `VALID`, and carries a 64-character hexadecimal
   payload SHA-256;
6. collection time is neither stale nor outside the allowed future clock skew;
7. every allowlisted OSD has exactly one valid record;
8. `up` and `in` are actual booleans for every OSD; unknown is never coerced;
9. already unavailable OSDs are included in the projected down budget; and
10. the projected unavailable count is within `max_simultaneous_down`.

Structural or identity errors return `BLOCKED`. A stale or currently unsafe
state returns `HOLD`. Missing/unknown evidence returns `INCONCLUSIVE`.

## Persisted-state binding

`DownSetInventoryAssessmentService` accepts repository loaders rather than a
run or collection object from an HTTP request. It loads both persisted objects
by ID and checks the caller's optimistic-concurrency tokens before evaluating
the snapshot:

- expected run state;
- expected plan revision;
- expected config snapshot ID; and
- expected resource version.

If any token changed, the request is `BLOCKED` with all detected stale reasons.
The persisted collection still passes through the domain identity and freshness
checks; loading it by ID does not make it trusted automatically.

## API and UI

The console exposes the assessment as a read-only `POST` because the target OSD
set and concurrency tokens form a structured request:

```text
POST /api/v1/upgrade-runs/{run_id}/down-set-readiness
```

The body contains `collection_id`, `target_osd_ids`, `expected_state`,
`plan_revision`, `config_snapshot_id`, and `resource_version`. It creates no
action job, takes no idempotency key, persists no execution result, and sends no
command to the Node executor.

The OSD Inventory screen exposes the same assessment below the selected
snapshot. It always renders inventory readiness separately from the red
`mutation_readiness=BLOCKED` result and lists the remaining gates.

## Validation results

Validated on 2026-10-09:

- focused comparison/down-set domain and application-binding tests: `16 passed`;
- complete backend unittest suite: `191 tests`, `OK`, `11 skipped` because
  `TEST_DATABASE_URL` was not provided for PostgreSQL-only integration tests;
- frontend contract suite: `5 passed`;
- frontend production build: succeeded (`vite build`).

The read-only API and UI are wired. No live mutation path is wired or enabled.
