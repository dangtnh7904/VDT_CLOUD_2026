CREATE TABLE upgrade_batches (
  id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  source_osds INTEGER[] NOT NULL,
  destination_osds INTEGER[] NOT NULL,
  parameters JSONB NOT NULL,
  state TEXT NOT NULL DEFAULT 'PLANNED',
  plan_revision BIGINT NOT NULL DEFAULT 1,
  resource_version BIGINT NOT NULL DEFAULT 1,
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT upgrade_batches_name_check CHECK (length(name) BETWEEN 1 AND 255),
  CONSTRAINT upgrade_batches_source_check CHECK (cardinality(source_osds) > 0),
  CONSTRAINT upgrade_batches_destination_check CHECK (cardinality(destination_osds) > 0),
  CONSTRAINT upgrade_batches_no_overlap_check CHECK (NOT (source_osds && destination_osds)),
  CONSTRAINT upgrade_batches_parameters_object_check CHECK (jsonb_typeof(parameters) = 'object'),
  CONSTRAINT upgrade_batches_state_check CHECK (state IN ('PLANNED', 'ACTIVE', 'CLOSED')),
  CONSTRAINT upgrade_batches_revision_check CHECK (plan_revision > 0 AND resource_version > 0),
  CONSTRAINT upgrade_batches_fingerprint_check CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  CONSTRAINT upgrade_batches_idempotency_unique UNIQUE (cluster_id, idempotency_key)
);

CREATE INDEX upgrade_batches_session_idx
  ON upgrade_batches(session_id, state, created_at DESC);

CREATE TABLE upgrade_runs (
  id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES upgrade_batches(id) ON DELETE RESTRICT,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id) ON DELETE RESTRICT,
  strategy TEXT NOT NULL,
  execution_mode TEXT NOT NULL DEFAULT 'DRY_RUN',
  state TEXT NOT NULL DEFAULT 'CREATED',
  target_version TEXT NOT NULL,
  target_image_digest TEXT NOT NULL,
  pa2_end_state TEXT,
  run_config JSONB NOT NULL,
  plan_revision BIGINT NOT NULL DEFAULT 1,
  resource_version BIGINT NOT NULL DEFAULT 1,
  operation_result TEXT,
  preflight_result JSONB,
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT upgrade_runs_strategy_check CHECK (strategy IN ('PA1_PRODUCTION', 'PA2_ROTATING_SPARE')),
  CONSTRAINT upgrade_runs_mode_check CHECK (execution_mode IN ('DRY_RUN', 'LIVE')),
  CONSTRAINT upgrade_runs_state_check CHECK (
    state IN ('CREATED', 'PREFLIGHT_READY', 'PREFLIGHT_BLOCKED', 'DRY_RUN_READY', 'PAUSED', 'CANCELLED')
  ),
  CONSTRAINT upgrade_runs_end_state_check CHECK (
    (strategy = 'PA1_PRODUCTION' AND pa2_end_state IS NULL)
    OR
    (strategy = 'PA2_ROTATING_SPARE' AND pa2_end_state IN ('KEEP_ROTATED_PLACEMENT', 'RECONCILE_TO_POLICY'))
  ),
  CONSTRAINT upgrade_runs_config_object_check CHECK (jsonb_typeof(run_config) = 'object'),
  CONSTRAINT upgrade_runs_preflight_object_check CHECK (
    preflight_result IS NULL OR jsonb_typeof(preflight_result) = 'object'
  ),
  CONSTRAINT upgrade_runs_result_check CHECK (
    operation_result IS NULL OR operation_result IN (
      'PASS', 'HOLD', 'BLOCKED', 'INCONCLUSIVE', 'NOT_REQUESTED',
      'NOT_EXERCISED', 'UNSUPPORTED', 'NOT_COMPARABLE'
    )
  ),
  CONSTRAINT upgrade_runs_revision_check CHECK (plan_revision > 0 AND resource_version > 0),
  CONSTRAINT upgrade_runs_fingerprint_check CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  CONSTRAINT upgrade_runs_idempotency_unique UNIQUE (cluster_id, idempotency_key)
);

CREATE INDEX upgrade_runs_session_state_idx
  ON upgrade_runs(session_id, state, created_at DESC);

CREATE TABLE placement_plans (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES upgrade_runs(id) ON DELETE RESTRICT,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  plan_revision BIGINT NOT NULL,
  inventory_snapshot_id UUID NOT NULL REFERENCES cluster_inventory_snapshots(id) ON DELETE RESTRICT,
  mode TEXT NOT NULL DEFAULT 'DRY_RUN',
  plan JSONB NOT NULL,
  plan_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT placement_plans_revision_check CHECK (plan_revision > 0),
  CONSTRAINT placement_plans_mode_check CHECK (mode = 'DRY_RUN'),
  CONSTRAINT placement_plans_payload_object_check CHECK (jsonb_typeof(plan) = 'object'),
  CONSTRAINT placement_plans_hash_check CHECK (plan_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT placement_plans_run_revision_unique UNIQUE (run_id, plan_revision)
);
