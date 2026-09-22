ALTER TABLE rbd_volumes
  ADD COLUMN transition_generation BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN creation_action_id UUID,
  ADD COLUMN filesystem TEXT NOT NULL DEFAULT 'ext4',
  ADD COLUMN auto_mount BOOLEAN NOT NULL DEFAULT true,
  ADD CONSTRAINT rbd_volumes_transition_generation_check
    CHECK (transition_generation >= 0),
  ADD CONSTRAINT rbd_volumes_filesystem_check
    CHECK (filesystem = 'ext4');

ALTER TABLE rbd_actions
  ADD COLUMN request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN current_step TEXT,
  ADD COLUMN volume_generation BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN lease_owner TEXT,
  ADD COLUMN lease_generation BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN heartbeat_at TIMESTAMPTZ,
  ADD COLUMN lease_expires_at TIMESTAMPTZ,
  ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN capacity_decision_id UUID
    REFERENCES capacity_decisions(id) ON DELETE SET NULL,
  ADD CONSTRAINT rbd_actions_payload_object_check
    CHECK (jsonb_typeof(request_payload) = 'object'),
  ADD CONSTRAINT rbd_actions_volume_generation_check
    CHECK (volume_generation >= 0),
  ADD CONSTRAINT rbd_actions_lease_generation_check
    CHECK (lease_generation >= 0),
  ADD CONSTRAINT rbd_actions_attempt_count_check
    CHECK (attempt_count >= 0);

CREATE INDEX rbd_actions_claim_idx
  ON rbd_actions(state, lease_expires_at, created_at)
  WHERE state IN ('PENDING', 'RUNNING', 'RECONCILING');

CREATE UNIQUE INDEX rbd_actions_one_active_per_volume
  ON rbd_actions(volume_id)
  WHERE state IN ('PENDING', 'RUNNING', 'RECONCILING');

