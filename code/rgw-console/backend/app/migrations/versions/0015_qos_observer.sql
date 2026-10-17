CREATE TABLE qos_runs (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id),
    upgrade_run_id UUID REFERENCES upgrade_runs(id),
    wave_id UUID REFERENCES upgrade_waves(id),
    cluster_id TEXT NOT NULL,
    fsid UUID NOT NULL,
    config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id),
    provider TEXT NOT NULL CHECK (provider IN ('WARP', 'FIO', 'APPLICATION')),
    state TEXT NOT NULL DEFAULT 'CREATED' CHECK (state IN (
        'CREATED', 'RUNNING', 'PAUSED', 'STOPPING', 'COMPLETED', 'FAILED'
    )),
    qos_result TEXT NOT NULL DEFAULT 'NOT_EXERCISED' CHECK (qos_result IN (
        'PENDING', 'PASS', 'FAIL', 'INCONCLUSIVE', 'NOT_REQUESTED',
        'NOT_EXERCISED', 'UNSUPPORTED', 'RUNNER_FAILED', 'NOT_COMPARABLE'
    )),
    requested_proof_level TEXT NOT NULL CHECK (requested_proof_level IN (
        'PG_ATTRIBUTED', 'PARTIAL_ATTRIBUTION', 'SERVICE_ONLY'
    )),
    runner_capability TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (runner_capability IN (
        'UNKNOWN', 'SUPPORTED', 'UNSUPPORTED', 'DISABLED'
    )),
    workload_hash TEXT NOT NULL CHECK (workload_hash ~ '^[0-9a-f]{64}$'),
    load_model TEXT NOT NULL,
    run_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    runner_handle JSONB,
    idempotency_key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    resource_version INTEGER NOT NULL DEFAULT 1 CHECK (resource_version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cluster_id, idempotency_key)
);

CREATE TABLE qos_segments (
    id UUID PRIMARY KEY,
    qos_run_id UUID NOT NULL REFERENCES qos_runs(id),
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    phase TEXT NOT NULL CHECK (phase IN (
        'BEFORE', 'DURING_PA1', 'DURING_PA2', 'AFTER_PA1', 'AFTER_PA2'
    )),
    cohort TEXT NOT NULL CHECK (cohort IN (
        'REMAP', 'NEIGHBOR', 'CONTROL', 'UNATTRIBUTED'
    )),
    proof_level TEXT NOT NULL CHECK (proof_level IN (
        'PG_ATTRIBUTED', 'PARTIAL_ATTRIBUTION', 'SERVICE_ONLY'
    )),
    workload_hash TEXT NOT NULL CHECK (workload_hash ~ '^[0-9a-f]{64}$'),
    topology_hash TEXT NOT NULL CHECK (topology_hash ~ '^[0-9a-f]{64}$'),
    budget_hash TEXT NOT NULL CHECK (budget_hash ~ '^[0-9a-f]{64}$'),
    load_profile_hash TEXT NOT NULL CHECK (load_profile_hash ~ '^[0-9a-f]{64}$'),
    attribution_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    result TEXT NOT NULL DEFAULT 'PENDING' CHECK (result IN (
        'PENDING', 'PASS', 'FAIL', 'INCONCLUSIVE', 'NOT_EXERCISED',
        'UNSUPPORTED', 'RUNNER_FAILED', 'NOT_COMPARABLE'
    )),
    comparison_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (qos_run_id, sequence)
);

CREATE TABLE qos_metric_windows (
    id UUID PRIMARY KEY,
    qos_run_id UUID NOT NULL REFERENCES qos_runs(id),
    segment_id UUID NOT NULL REFERENCES qos_segments(id),
    evidence_artifact_id UUID REFERENCES evidence_artifacts(id),
    source TEXT NOT NULL,
    unit_schema TEXT NOT NULL DEFAULT 'qos-metrics-v1',
    quality TEXT NOT NULL CHECK (quality IN ('VALID', 'STALE', 'GAP', 'COUNTER_RESET')),
    proof_level TEXT NOT NULL CHECK (proof_level IN (
        'PG_ATTRIBUTED', 'PARTIAL_ATTRIBUTION', 'SERVICE_ONLY'
    )),
    metrics JSONB NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    window_ended_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    config_hash TEXT NOT NULL CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (window_ended_at > window_started_at),
    CHECK (collected_at >= observed_at)
);

CREATE TABLE qos_benchmark_attempts (
    id UUID PRIMARY KEY,
    qos_run_id UUID NOT NULL REFERENCES qos_runs(id),
    segment_id UUID REFERENCES qos_segments(id),
    provider TEXT NOT NULL CHECK (provider IN ('WARP', 'FIO', 'APPLICATION')),
    state TEXT NOT NULL CHECK (state IN (
        'REQUESTED', 'RUNNING', 'PAUSED', 'SUCCEEDED', 'FAILED', 'STOPPED'
    )),
    request JSONB NOT NULL DEFAULT '{}'::jsonb,
    runner_handle JSONB,
    raw_artifact_id UUID REFERENCES evidence_artifacts(id),
    error_code TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_qos_runs_session ON qos_runs(session_id, created_at);
CREATE INDEX idx_qos_runs_upgrade_run ON qos_runs(upgrade_run_id) WHERE upgrade_run_id IS NOT NULL;
CREATE INDEX idx_qos_segments_run ON qos_segments(qos_run_id, sequence);
CREATE INDEX idx_qos_metric_windows_segment ON qos_metric_windows(segment_id, window_started_at);
CREATE INDEX idx_qos_benchmark_attempts_run ON qos_benchmark_attempts(qos_run_id, created_at);
