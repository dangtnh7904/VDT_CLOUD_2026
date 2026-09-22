\set ON_ERROR_STOP on

BEGIN;
CREATE SCHEMA rgw_console_migration_test_fresh;
SET LOCAL search_path TO rgw_console_migration_test_fresh;

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

\ir ../app/migrations/versions/0001_legacy_baseline.sql
\ir ../app/migrations/versions/0002_p1_foundation.sql

INSERT INTO capacity_decisions (
  id,
  policy_version,
  state,
  reason,
  decision
)
VALUES (
  '22222222-2222-2222-2222-222222222222',
  'test-policy',
  'READ_CLEANUP_ONLY',
  'no telemetry is available during this test',
  'BLOCK'
);

DO $$
DECLARE
  required_table TEXT;
BEGIN
  FOREACH required_table IN ARRAY ARRAY[
    'operations',
    'stream_jobs',
    'stream_objects',
    'stream_object_heads',
    'idempotency_requests',
    'capacity_snapshots',
    'capacity_osds',
    'capacity_decisions',
    'capacity_reservations',
    'capacity_reservation_allocations',
    'control_state',
    'rbd_volumes',
    'rbd_actions'
  ]
  LOOP
    IF to_regclass(required_table) IS NULL THEN
      RAISE EXCEPTION 'fresh migration did not create table %', required_table;
    END IF;
  END LOOP;

  IF (SELECT desired_state FROM control_state WHERE id = true) <> 'NORMAL' THEN
    RAISE EXCEPTION 'control_state was not seeded as NORMAL';
  END IF;
END
$$;

ROLLBACK;

BEGIN;
CREATE SCHEMA rgw_console_migration_test_legacy;
SET LOCAL search_path TO rgw_console_migration_test_legacy;

\ir ../app/migrations/versions/0001_legacy_baseline.sql

INSERT INTO stream_jobs (
  id,
  state,
  config,
  sent_count,
  failed_count,
  bytes_sent,
  last_error
)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  'running',
  '{"client_id":"legacy-client"}'::jsonb,
  17,
  2,
  4096,
  'legacy error retained'
);

INSERT INTO operations (
  kind,
  success,
  bytes_count,
  latency_ms,
  bucket,
  object_key,
  client_id,
  category,
  source,
  content_type,
  error
)
VALUES (
  'PUT',
  true,
  4096,
  12.5,
  'legacy-bucket',
  'path/to/object',
  'legacy-client',
  'documents',
  'corpus',
  'application/octet-stream',
  NULL
);

\ir ../app/migrations/versions/0002_p1_foundation.sql

DO $$
DECLARE
  migrated_job stream_jobs%ROWTYPE;
  migrated_operation operations%ROWTYPE;
BEGIN
  SELECT * INTO STRICT migrated_job
  FROM stream_jobs
  WHERE id = '11111111-1111-1111-1111-111111111111';

  IF migrated_job.job_type <> 'legacy_put'
     OR migrated_job.sent_count <> 17
     OR migrated_job.failed_count <> 2
     OR migrated_job.bytes_sent <> 4096
     OR migrated_job.last_error <> 'legacy error retained'
     OR migrated_job.config <> '{"client_id":"legacy-client"}'::jsonb THEN
    RAISE EXCEPTION 'legacy stream_jobs row changed during migration';
  END IF;

  SELECT * INTO STRICT migrated_operation
  FROM operations
  WHERE bucket = 'legacy-bucket' AND object_key = 'path/to/object';

  IF migrated_operation.kind <> 'PUT'
     OR migrated_operation.bytes_count <> 4096
     OR migrated_operation.target_type <> 'RGW_OBJECT'
     OR migrated_operation.target_id <> 'rgw:13:legacy-bucket:path/to/object' THEN
    RAISE EXCEPTION 'legacy operations row was not preserved/backfilled correctly';
  END IF;

  BEGIN
    INSERT INTO operations (
      kind,
      success,
      target_type,
      target_id
    )
    VALUES ('NOT_A_KIND', false, 'RGW_OBJECT', 'invalid');
    RAISE EXCEPTION 'invalid operation kind unexpectedly passed';
  EXCEPTION
    WHEN check_violation THEN NULL;
  END;
END
$$;

ROLLBACK;

SELECT 'migration SQL tests passed' AS result;
