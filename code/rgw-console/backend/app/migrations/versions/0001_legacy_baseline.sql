CREATE TABLE operations (
  id BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('PUT', 'GET')),
  success BOOLEAN NOT NULL,
  bytes_count BIGINT NOT NULL DEFAULT 0,
  latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
  bucket TEXT NOT NULL,
  object_key TEXT NOT NULL,
  client_id TEXT,
  category TEXT,
  source TEXT,
  content_type TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX operations_created_idx ON operations(created_at DESC);
CREATE INDEX operations_object_idx ON operations(bucket, object_key);

CREATE TABLE stream_jobs (
  id UUID PRIMARY KEY,
  state TEXT NOT NULL DEFAULT 'pending',
  config JSONB NOT NULL,
  sent_count BIGINT NOT NULL DEFAULT 0,
  failed_count BIGINT NOT NULL DEFAULT 0,
  bytes_sent BIGINT NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE INDEX stream_jobs_state_idx ON stream_jobs(state, created_at);
