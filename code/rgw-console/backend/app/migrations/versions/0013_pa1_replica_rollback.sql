ALTER TABLE upgrade_runs DROP CONSTRAINT upgrade_runs_state_check;
ALTER TABLE upgrade_runs ADD CONSTRAINT upgrade_runs_state_check CHECK (
  state IN (
    'CREATED', 'PREFLIGHT_READY', 'PREFLIGHT_BLOCKED', 'DRY_RUN_READY',
    'BASELINE_READY', 'DRAINING', 'DRAINED', 'MAINTENANCE_APPROVED',
    'UPGRADING', 'DAEMON_READY', 'REPLICA_RETURN', 'REPLICA_CONVERGING',
    'REPLICA_SCRUBBING', 'REPLICA_ACCEPTED', 'PRIMARY_RESTORE_READY',
    'PRIMARY_RESTORED', 'RESTORING', 'STABILIZING', 'COMPLETE',
    'PAUSED', 'CANCELLED'
  )
);

CREATE TABLE placement_entries (
  id UUID PRIMARY KEY,
  placement_plan_id UUID NOT NULL REFERENCES placement_plans(id) ON DELETE RESTRICT,
  run_id UUID NOT NULL REFERENCES upgrade_runs(id) ON DELETE RESTRICT,
  pgid TEXT NOT NULL,
  before_up INTEGER[] NOT NULL,
  before_acting INTEGER[] NOT NULL,
  current_up INTEGER[] NOT NULL,
  current_acting INTEGER[] NOT NULL,
  desired_up INTEGER[] NOT NULL,
  desired_acting INTEGER[] NOT NULL,
  actual_primary INTEGER,
  mapping_interval TEXT NOT NULL,
  osdmap_epoch BIGINT NOT NULL,
  source_osd INTEGER NOT NULL,
  source_incarnation TEXT NOT NULL,
  destination_osd INTEGER NOT NULL,
  destination_incarnation TEXT NOT NULL,
  expected_destination_role TEXT NOT NULL,
  owner_run_id UUID NOT NULL,
  plan_revision BIGINT NOT NULL,
  dependent_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
  disposition TEXT NOT NULL,
  estimated_bytes BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT placement_entries_epoch_check CHECK (osdmap_epoch >= 0),
  CONSTRAINT placement_entries_role_check CHECK (expected_destination_role = 'REPLICA'),
  CONSTRAINT placement_entries_revision_check CHECK (plan_revision > 0),
  CONSTRAINT placement_entries_dependencies_check CHECK (jsonb_typeof(dependent_steps) = 'array'),
  CONSTRAINT placement_entries_disposition_check CHECK (
    disposition IN ('RESTORE', 'KEEP', 'HANDOFF', 'OBSERVE_ONLY')
  ),
  CONSTRAINT placement_entries_bytes_check CHECK (estimated_bytes IS NULL OR estimated_bytes >= 0),
  CONSTRAINT placement_entries_plan_pgid_unique UNIQUE (placement_plan_id, pgid)
);

CREATE INDEX placement_entries_run_pgid_idx ON placement_entries(run_id, pgid);

CREATE TABLE return_groups (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES upgrade_runs(id) ON DELETE RESTRICT,
  group_index INTEGER NOT NULL,
  pgids TEXT[] NOT NULL,
  estimated_bytes BIGINT,
  state TEXT NOT NULL DEFAULT 'PLANNED',
  result TEXT,
  evidence_revision BIGINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT return_groups_index_check CHECK (group_index >= 0),
  CONSTRAINT return_groups_pgids_check CHECK (cardinality(pgids) > 0),
  CONSTRAINT return_groups_bytes_check CHECK (estimated_bytes IS NULL OR estimated_bytes >= 0),
  CONSTRAINT return_groups_state_check CHECK (
    state IN ('PLANNED', 'ADMITTED', 'CONVERGING', 'SCRUBBING', 'ACCEPTED')
  ),
  CONSTRAINT return_groups_result_check CHECK (
    result IS NULL OR result IN ('PASS', 'HOLD', 'BLOCKED', 'INCONCLUSIVE', 'UNSUPPORTED')
  ),
  CONSTRAINT return_groups_run_index_unique UNIQUE (run_id, group_index)
);

CREATE TABLE pg_role_observations (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES upgrade_runs(id) ON DELETE RESTRICT,
  return_group_id UUID REFERENCES return_groups(id) ON DELETE RESTRICT,
  pgid TEXT NOT NULL,
  up_osds INTEGER[] NOT NULL,
  acting_osds INTEGER[] NOT NULL,
  actual_primary INTEGER,
  target_osd INTEGER NOT NULL,
  target_role TEXT,
  active BOOLEAN NOT NULL,
  clean BOOLEAN NOT NULL,
  mapping_interval TEXT NOT NULL,
  mapping_fingerprint TEXT NOT NULL,
  osdmap_epoch BIGINT NOT NULL,
  source_incarnation TEXT NOT NULL,
  target_incarnation TEXT NOT NULL,
  fresh BOOLEAN NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT pg_role_observations_role_check CHECK (
    target_role IS NULL OR target_role IN ('PRIMARY', 'REPLICA')
  ),
  CONSTRAINT pg_role_observations_epoch_check CHECK (osdmap_epoch >= 0),
  CONSTRAINT pg_role_observations_fingerprint_check CHECK (length(mapping_fingerprint) > 0)
);

CREATE INDEX pg_role_observations_scope_idx
  ON pg_role_observations(run_id, pgid, observed_at DESC);

CREATE TABLE scrub_runs (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES upgrade_runs(id) ON DELETE RESTRICT,
  return_group_id UUID REFERENCES return_groups(id) ON DELETE RESTRICT,
  pgid TEXT NOT NULL,
  target_osd INTEGER NOT NULL,
  target_incarnation TEXT NOT NULL,
  mapping_fingerprint TEXT NOT NULL,
  requested_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  result_clean BOOLEAN,
  inconsistency_count INTEGER,
  io_error_count INTEGER,
  repair_event_count INTEGER,
  fresh BOOLEAN NOT NULL DEFAULT false,
  result TEXT,
  evidence_artifact_id UUID REFERENCES evidence_artifacts(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scrub_runs_counts_check CHECK (
    (inconsistency_count IS NULL OR inconsistency_count >= 0)
    AND (io_error_count IS NULL OR io_error_count >= 0)
    AND (repair_event_count IS NULL OR repair_event_count >= 0)
  ),
  CONSTRAINT scrub_runs_time_check CHECK (
    started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at
  ),
  CONSTRAINT scrub_runs_result_check CHECK (
    result IS NULL OR result IN ('PASS', 'HOLD', 'BLOCKED', 'INCONCLUSIVE', 'UNSUPPORTED')
  )
);

CREATE INDEX scrub_runs_scope_idx ON scrub_runs(run_id, pgid, created_at DESC);

CREATE TABLE affinity_restores (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES upgrade_runs(id) ON DELETE RESTRICT,
  plan_revision BIGINT NOT NULL,
  ownership_verified BOOLEAN NOT NULL,
  before_state JSONB NOT NULL,
  desired_state JSONB NOT NULL,
  observed_state JSONB,
  state TEXT NOT NULL DEFAULT 'PLANNED',
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT affinity_restores_revision_check CHECK (plan_revision > 0),
  CONSTRAINT affinity_restores_state_check CHECK (
    state IN ('PLANNED', 'RUNNING', 'STABILIZING', 'COMPLETE', 'HOLD')
  ),
  CONSTRAINT affinity_restores_before_check CHECK (jsonb_typeof(before_state) = 'object'),
  CONSTRAINT affinity_restores_desired_check CHECK (jsonb_typeof(desired_state) = 'object'),
  CONSTRAINT affinity_restores_observed_check CHECK (
    observed_state IS NULL OR jsonb_typeof(observed_state) = 'object'
  )
);

CREATE TABLE rollback_runs (
  id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  upgrade_run_id UUID NOT NULL REFERENCES upgrade_runs(id) ON DELETE RESTRICT,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id) ON DELETE RESTRICT,
  failed_osd INTEGER NOT NULL,
  failed_incarnation TEXT NOT NULL,
  old_version TEXT NOT NULL,
  old_image_digest TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'HOLD',
  result TEXT,
  plan JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT rollback_runs_state_check CHECK (
    state IN (
      'HOLD', 'CONTAINED', 'SOURCES_READY', 'SAFE_TO_REMOVE',
      'R_PROVISIONED', 'R_REBUILT', 'ROLLBACK_COMPLETE'
    )
  ),
  CONSTRAINT rollback_runs_result_check CHECK (
    result IS NULL OR result IN ('PASS', 'HOLD', 'BLOCKED', 'INCONCLUSIVE', 'UNSUPPORTED')
  ),
  CONSTRAINT rollback_runs_plan_check CHECK (jsonb_typeof(plan) = 'object')
);

CREATE TABLE replacement_sources (
  id UUID PRIMARY KEY,
  rollback_run_id UUID NOT NULL REFERENCES rollback_runs(id) ON DELETE RESTRICT,
  pgid TEXT NOT NULL,
  source_osd INTEGER NOT NULL,
  source_incarnation TEXT NOT NULL,
  mapping_fingerprint TEXT NOT NULL,
  healthy BOOLEAN NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT replacement_sources_scope_unique UNIQUE (rollback_run_id, pgid, source_osd)
);

CREATE TABLE replacement_rebuild_groups (
  id UUID PRIMARY KEY,
  rollback_run_id UUID NOT NULL REFERENCES rollback_runs(id) ON DELETE RESTRICT,
  group_index INTEGER NOT NULL,
  pgids TEXT[] NOT NULL,
  state TEXT NOT NULL DEFAULT 'PLANNED',
  result TEXT,
  evidence_artifact_id UUID REFERENCES evidence_artifacts(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT replacement_rebuild_groups_index_check CHECK (group_index >= 0),
  CONSTRAINT replacement_rebuild_groups_pgids_check CHECK (cardinality(pgids) > 0),
  CONSTRAINT replacement_rebuild_groups_state_check CHECK (
    state IN ('PLANNED', 'REBUILDING', 'SCRUBBING', 'ACCEPTED')
  ),
  CONSTRAINT replacement_rebuild_groups_result_check CHECK (
    result IS NULL OR result IN ('PASS', 'HOLD', 'BLOCKED', 'INCONCLUSIVE', 'UNSUPPORTED')
  ),
  CONSTRAINT replacement_rebuild_groups_run_index_unique UNIQUE (rollback_run_id, group_index)
);
