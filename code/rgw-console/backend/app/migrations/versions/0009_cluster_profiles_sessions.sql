CREATE TABLE cluster_profiles (
  id UUID PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  expected_fsid UUID NOT NULL,
  revision TEXT NOT NULL,
  profile JSONB NOT NULL,
  config_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT cluster_profiles_cluster_revision_unique UNIQUE (cluster_id, revision),
  CONSTRAINT cluster_profiles_payload_object_check CHECK (jsonb_typeof(profile) = 'object'),
  CONSTRAINT cluster_profiles_hash_check CHECK (config_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE policy_revisions (
  id UUID PRIMARY KEY,
  revision TEXT NOT NULL UNIQUE,
  policy JSONB NOT NULL,
  policy_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT policy_revisions_payload_object_check CHECK (jsonb_typeof(policy) = 'object'),
  CONSTRAINT policy_revisions_hash_check CHECK (policy_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE config_snapshots (
  id UUID PRIMARY KEY,
  cluster_profile_id UUID NOT NULL REFERENCES cluster_profiles(id) ON DELETE RESTRICT,
  policy_revision_id UUID REFERENCES policy_revisions(id) ON DELETE RESTRICT,
  cluster_id TEXT NOT NULL,
  expected_fsid UUID NOT NULL,
  actual_fsid UUID NOT NULL,
  config_hash TEXT NOT NULL,
  resolved_config JSONB NOT NULL,
  secrets_redacted BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT config_snapshots_payload_object_check CHECK (jsonb_typeof(resolved_config) = 'object'),
  CONSTRAINT config_snapshots_hash_check CHECK (config_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT config_snapshots_fsid_match_check CHECK (expected_fsid = actual_fsid),
  CONSTRAINT config_snapshots_redacted_check CHECK (secrets_redacted)
);

CREATE INDEX config_snapshots_cluster_time_idx
  ON config_snapshots(cluster_id, created_at DESC);

CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  execution_environment TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'CREATED',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ,
  CONSTRAINT sessions_name_check CHECK (length(name) BETWEEN 1 AND 255),
  CONSTRAINT sessions_environment_check CHECK (execution_environment IN ('lab', 'staging', 'production')),
  CONSTRAINT sessions_state_check CHECK (state IN ('CREATED', 'ACTIVE', 'CLOSED')),
  CONSTRAINT sessions_close_shape_check CHECK (
    (state = 'CLOSED' AND closed_at IS NOT NULL)
    OR (state <> 'CLOSED' AND closed_at IS NULL)
  )
);

CREATE INDEX sessions_cluster_state_idx
  ON sessions(cluster_id, state, created_at DESC);

CREATE TABLE session_workflows (
  id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  workflow_type TEXT NOT NULL,
  status TEXT NOT NULL,
  run_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT session_workflows_type_check CHECK (
    workflow_type IN ('UPGRADE_PRODUCTION', 'QOS_OBSERVER', 'LAB_TEST', 'ROLLBACK', 'LEGACY')
  ),
  CONSTRAINT session_workflows_status_check CHECK (
    status IN ('NOT_REQUESTED', 'CREATED', 'ACTIVE', 'COMPLETE', 'HOLD', 'BLOCKED', 'INCONCLUSIVE')
  ),
  CONSTRAINT session_workflows_session_type_run_unique UNIQUE (session_id, workflow_type, run_id)
);

CREATE UNIQUE INDEX session_workflows_one_unbound_type_unique
  ON session_workflows(session_id, workflow_type)
  WHERE run_id IS NULL;
