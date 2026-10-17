CREATE TABLE cluster_capabilities (
  id UUID PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id) ON DELETE RESTRICT,
  session_id UUID REFERENCES sessions(id) ON DELETE RESTRICT,
  evidence_artifact_id UUID REFERENCES evidence_artifacts(id) ON DELETE RESTRICT,
  capability_name TEXT NOT NULL,
  capability_state TEXT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  observed_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT cluster_capabilities_state_check CHECK (
    capability_state IN (
      'SUPPORTED', 'DEGRADED', 'FALLBACK_LOG_EVIDENCE',
      'DISABLED', 'STALE', 'UNSUPPORTED'
    )
  ),
  CONSTRAINT cluster_capabilities_evidence_object_check CHECK (jsonb_typeof(evidence) = 'object'),
  CONSTRAINT cluster_capabilities_observation_unique UNIQUE (
    config_snapshot_id, session_id, capability_name, observed_at
  )
);

CREATE INDEX cluster_capabilities_scope_time_idx
  ON cluster_capabilities(cluster_id, capability_name, observed_at DESC);

CREATE TABLE phase_events (
  id UUID PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  run_id UUID,
  sequence BIGINT NOT NULL,
  phase TEXT NOT NULL,
  event_type TEXT NOT NULL,
  result TEXT,
  occurred_at TIMESTAMPTZ NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT phase_events_result_check CHECK (
    result IS NULL OR result IN (
      'PASS', 'HOLD', 'BLOCKED', 'INCONCLUSIVE', 'NOT_REQUESTED',
      'NOT_EXERCISED', 'UNSUPPORTED', 'NOT_COMPARABLE'
    )
  ),
  CONSTRAINT phase_events_payload_object_check CHECK (jsonb_typeof(payload) = 'object'),
  CONSTRAINT phase_events_sequence_check CHECK (sequence > 0),
  CONSTRAINT phase_events_run_sequence_unique UNIQUE (run_id, sequence)
);

CREATE INDEX phase_events_session_time_idx
  ON phase_events(session_id, occurred_at, sequence);
