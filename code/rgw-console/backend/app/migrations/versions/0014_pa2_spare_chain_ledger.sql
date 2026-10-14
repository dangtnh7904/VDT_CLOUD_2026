CREATE TABLE upgrade_waves (
    id UUID PRIMARY KEY,
    upgrade_run_id UUID NOT NULL REFERENCES upgrade_runs(id),
    wave_number INTEGER NOT NULL CHECK (wave_number >= 0),
    state TEXT NOT NULL CHECK (state IN (
        'WAVE_PLANNED',
        'CHAIN_READY',
        'SPARE_CANDIDATE',
        'SPARE_ADMISSION_ALLOWED',
        'HANDOFF_GROUP_CONVERGING',
        'HANDOFF_GROUP_SCRUBBING',
        'HANDOFF_GROUP_ACCEPTED',
        'HANDOFF_COMPLETE',
        'SOURCE_UPGRADING',
        'SPARE_ROTATED',
        'WAVE_RECONCILING',
        'WAVE_STABILIZING',
        'WAVE_COMPLETE'
    )),
    expected_state_version INTEGER NOT NULL DEFAULT 0 CHECK (expected_state_version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (upgrade_run_id, wave_number)
);

CREATE TABLE spare_registry (
    id UUID PRIMARY KEY,
    upgrade_run_id UUID NOT NULL REFERENCES upgrade_runs(id),
    host_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RESERVED', 'CANDIDATE', 'ADMITTED', 'ROTATED', 'RELEASED', 'HOLD')),
    expected_digest TEXT NOT NULL,
    observed_digest TEXT,
    reservation_owner TEXT NOT NULL,
    healthy BOOLEAN NOT NULL DEFAULT FALSE,
    isolated_from_production BOOLEAN NOT NULL DEFAULT FALSE,
    incarnation TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (upgrade_run_id, host_id)
);

CREATE TABLE spare_chains (
    id UUID PRIMARY KEY,
    wave_id UUID NOT NULL REFERENCES upgrade_waves(id),
    chain_index INTEGER NOT NULL CHECK (chain_index >= 0),
    source_host_id TEXT NOT NULL,
    destination_host_id TEXT NOT NULL,
    failure_domain TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PLANNED', 'READY', 'ROTATING', 'COMPLETE', 'HOLD')),
    lease_generation BIGINT CHECK (lease_generation IS NULL OR lease_generation >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (source_host_id <> destination_host_id),
    UNIQUE (wave_id, chain_index),
    UNIQUE (wave_id, destination_host_id)
);

CREATE TABLE handoff_groups (
    id UUID PRIMARY KEY,
    spare_chain_id UUID NOT NULL REFERENCES spare_chains(id),
    group_index INTEGER NOT NULL CHECK (group_index >= 0),
    pg_ids JSONB NOT NULL,
    initial_mapping_digest TEXT NOT NULL,
    accepted_mapping_digest TEXT,
    state TEXT NOT NULL CHECK (state IN ('PLANNED', 'CONVERGING', 'SCRUBBING', 'ACCEPTED', 'HOLD')),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (spare_chain_id, group_index)
);

CREATE TABLE rotation_steps (
    id UUID PRIMARY KEY,
    spare_chain_id UUID NOT NULL REFERENCES spare_chains(id),
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    state TEXT NOT NULL CHECK (state IN ('PLANNED', 'HANDOFF_COMPLETE', 'SOURCE_UPGRADING', 'ROTATED', 'HOLD')),
    source_incarnation TEXT,
    destination_incarnation TEXT,
    observed_mapping JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (spare_chain_id, sequence_number)
);

CREATE TABLE end_state_handoffs (
    id UUID PRIMARY KEY,
    wave_id UUID NOT NULL UNIQUE REFERENCES upgrade_waves(id),
    selected_end_state TEXT NOT NULL CHECK (selected_end_state IN ('KEEP_FINAL_SPARE', 'RESTORE_ORIGINAL_TOPOLOGY')),
    final_spare_host_id TEXT,
    final_spare_received_pg BOOLEAN NOT NULL DEFAULT FALSE,
    verification_outcome TEXT NOT NULL CHECK (verification_outcome IN ('PENDING', 'PASS', 'HOLD', 'INCONCLUSIVE', 'NOT_EXERCISED')),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_upgrade_waves_run ON upgrade_waves(upgrade_run_id, wave_number);
CREATE INDEX idx_spare_registry_run ON spare_registry(upgrade_run_id, status);
CREATE INDEX idx_spare_chains_wave ON spare_chains(wave_id, chain_index);
CREATE INDEX idx_handoff_groups_chain ON handoff_groups(spare_chain_id, group_index);
CREATE INDEX idx_rotation_steps_chain ON rotation_steps(spare_chain_id, sequence_number);
