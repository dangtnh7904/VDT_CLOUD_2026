CREATE TABLE evidence_artifacts (
  id UUID PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  session_id UUID REFERENCES sessions(id) ON DELETE RESTRICT,
  run_id UUID,
  evidence_type TEXT NOT NULL,
  uri TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  mime_type TEXT NOT NULL,
  producer TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  access_policy TEXT NOT NULL DEFAULT 'operator',
  retention_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT evidence_artifacts_hash_check CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT evidence_artifacts_size_check CHECK (size_bytes >= 0),
  CONSTRAINT evidence_artifacts_metadata_object_check CHECK (jsonb_typeof(metadata) = 'object'),
  CONSTRAINT evidence_artifacts_access_check CHECK (access_policy IN ('operator', 'internal'))
);

CREATE INDEX evidence_artifacts_scope_time_idx
  ON evidence_artifacts(cluster_id, session_id, run_id, created_at DESC);

CREATE TABLE cluster_inventory_snapshots (
  id UUID PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id) ON DELETE RESTRICT,
  session_id UUID REFERENCES sessions(id) ON DELETE RESTRICT,
  evidence_artifact_id UUID NOT NULL REFERENCES evidence_artifacts(id) ON DELETE RESTRICT,
  osdmap_epoch BIGINT,
  quality TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT cluster_inventory_quality_check CHECK (
    quality IN ('VALID', 'STALE', 'GAP', 'UNSUPPORTED', 'INCONCLUSIVE')
  ),
  CONSTRAINT cluster_inventory_epoch_check CHECK (osdmap_epoch IS NULL OR osdmap_epoch >= 0),
  CONSTRAINT cluster_inventory_payload_object_check CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX cluster_inventory_scope_time_idx
  ON cluster_inventory_snapshots(cluster_id, observed_at DESC);

CREATE TABLE outbox_events (
  id UUID PRIMARY KEY,
  schema_version INTEGER NOT NULL DEFAULT 1,
  event_type TEXT NOT NULL,
  stream_key TEXT NOT NULL,
  sequence BIGINT NOT NULL,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  session_id UUID REFERENCES sessions(id) ON DELETE RESTRICT,
  run_id UUID,
  occurred_at TIMESTAMPTZ NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  producer TEXT NOT NULL,
  correlation_id UUID NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT outbox_events_schema_check CHECK (schema_version = 1),
  CONSTRAINT outbox_events_sequence_check CHECK (sequence > 0),
  CONSTRAINT outbox_events_payload_object_check CHECK (jsonb_typeof(payload) = 'object'),
  CONSTRAINT outbox_events_stream_sequence_unique UNIQUE (stream_key, sequence)
);

CREATE INDEX outbox_events_unpublished_idx
  ON outbox_events(created_at, id)
  WHERE published_at IS NULL;
CREATE INDEX outbox_events_session_idx
  ON outbox_events(session_id, occurred_at, sequence);

CREATE TABLE resource_leases (
  cluster_id TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  owner_run_id UUID NOT NULL,
  lease_generation BIGINT NOT NULL,
  lease_expires_at TIMESTAMPTZ NOT NULL,
  heartbeat_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (cluster_id, resource_type, resource_id),
  CONSTRAINT resource_leases_generation_check CHECK (lease_generation > 0)
);

CREATE INDEX resource_leases_owner_idx
  ON resource_leases(owner_run_id, lease_expires_at);

CREATE TABLE action_jobs (
  id UUID PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  run_id UUID,
  action_type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING',
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  expected_state TEXT,
  plan_revision BIGINT,
  resource_version BIGINT,
  lease_generation BIGINT,
  request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  result JSONB,
  error_code TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT action_jobs_state_check CHECK (
    state IN ('PENDING', 'RUNNING', 'RECONCILING', 'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_FINAL')
  ),
  CONSTRAINT action_jobs_fingerprint_check CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  CONSTRAINT action_jobs_attempt_check CHECK (attempt_count >= 0),
  CONSTRAINT action_jobs_payload_object_check CHECK (jsonb_typeof(request_payload) = 'object'),
  CONSTRAINT action_jobs_result_object_check CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
  CONSTRAINT action_jobs_scope_key_unique UNIQUE (cluster_id, idempotency_key)
);

CREATE INDEX action_jobs_run_state_idx ON action_jobs(run_id, state, created_at);

CREATE TABLE run_changes (
  id UUID PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  run_id UUID NOT NULL,
  sequence BIGINT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  change_type TEXT NOT NULL,
  ownership_state TEXT NOT NULL,
  before_state JSONB,
  desired_state JSONB,
  observed_state JSONB,
  dependent_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
  disposition TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT run_changes_sequence_check CHECK (sequence > 0),
  CONSTRAINT run_changes_owner_check CHECK (
    ownership_state IN ('PLANNED', 'OWNED', 'HANDED_OFF', 'RELEASED', 'CONFLICT')
  ),
  CONSTRAINT run_changes_disposition_check CHECK (
    disposition IN ('RESTORE', 'KEEP', 'HANDOFF', 'OBSERVE_ONLY')
  ),
  CONSTRAINT run_changes_before_object_check CHECK (before_state IS NULL OR jsonb_typeof(before_state) = 'object'),
  CONSTRAINT run_changes_desired_object_check CHECK (desired_state IS NULL OR jsonb_typeof(desired_state) = 'object'),
  CONSTRAINT run_changes_observed_object_check CHECK (observed_state IS NULL OR jsonb_typeof(observed_state) = 'object'),
  CONSTRAINT run_changes_dependencies_array_check CHECK (jsonb_typeof(dependent_steps) = 'array'),
  CONSTRAINT run_changes_run_sequence_unique UNIQUE (run_id, sequence)
);

CREATE INDEX run_changes_resource_idx
  ON run_changes(cluster_id, resource_type, resource_id, ownership_state);
