CREATE TABLE performance_samples (
  id BIGSERIAL PRIMARY KEY,
  fsid TEXT NOT NULL,
  sample_kind TEXT NOT NULL DEFAULT 'raw',
  source TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL,
  window_seconds DOUBLE PRECISION NOT NULL,
  read_iops DOUBLE PRECISION,
  write_iops DOUBLE PRECISION,
  total_iops DOUBLE PRECISION,
  read_bytes_per_second DOUBLE PRECISION,
  write_bytes_per_second DOUBLE PRECISION,
  total_bytes_per_second DOUBLE PRECISION,
  read_latency_ms DOUBLE PRECISION,
  write_latency_ms DOUBLE PRECISION,
  average_latency_ms DOUBLE PRECISION,
  p50_latency_ms DOUBLE PRECISION,
  p95_latency_ms DOUBLE PRECISION,
  p99_latency_ms DOUBLE PRECISION,
  success_count BIGINT,
  error_count BIGINT,
  fresh BOOLEAN NOT NULL,
  reset_detected BOOLEAN NOT NULL DEFAULT false,
  partial BOOLEAN NOT NULL DEFAULT false,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT performance_samples_source_check
    CHECK (source IN ('application', 'ceph', 'device')),
  CONSTRAINT performance_samples_kind_check
    CHECK (sample_kind IN ('raw', 'rollup_1m')),
  CONSTRAINT performance_samples_scope_type_check
    CHECK (scope_type IN ('cluster', 'osd', 'pool', 'image', 'job', 'operation')),
  CONSTRAINT performance_samples_window_check CHECK (window_seconds > 0),
  CONSTRAINT performance_samples_non_negative_check CHECK (
    (read_iops IS NULL OR read_iops >= 0)
    AND (write_iops IS NULL OR write_iops >= 0)
    AND (total_iops IS NULL OR total_iops >= 0)
    AND (read_bytes_per_second IS NULL OR read_bytes_per_second >= 0)
    AND (write_bytes_per_second IS NULL OR write_bytes_per_second >= 0)
    AND (total_bytes_per_second IS NULL OR total_bytes_per_second >= 0)
    AND (read_latency_ms IS NULL OR read_latency_ms >= 0)
    AND (write_latency_ms IS NULL OR write_latency_ms >= 0)
    AND (average_latency_ms IS NULL OR average_latency_ms >= 0)
    AND (p50_latency_ms IS NULL OR p50_latency_ms >= 0)
    AND (p95_latency_ms IS NULL OR p95_latency_ms >= 0)
    AND (p99_latency_ms IS NULL OR p99_latency_ms >= 0)
    AND (success_count IS NULL OR success_count >= 0)
    AND (error_count IS NULL OR error_count >= 0)
  ),
  CONSTRAINT performance_samples_metadata_object_check
    CHECK (jsonb_typeof(metadata) = 'object'),
  CONSTRAINT performance_samples_identity_unique
    UNIQUE (fsid, sample_kind, source, scope_type, scope_id, captured_at, window_seconds)
);

CREATE INDEX performance_samples_lookup_idx
  ON performance_samples(fsid, sample_kind, source, scope_type, scope_id, captured_at DESC);
CREATE INDEX performance_samples_retention_idx
  ON performance_samples(captured_at);
