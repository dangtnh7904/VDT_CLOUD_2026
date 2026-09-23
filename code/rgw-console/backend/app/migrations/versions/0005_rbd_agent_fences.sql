ALTER TABLE rbd_volumes
  ADD COLUMN agent_fence_token BIGINT NOT NULL DEFAULT 0,
  ADD CONSTRAINT rbd_volumes_agent_fence_token_check
    CHECK (agent_fence_token >= 0);

ALTER TABLE rbd_actions
  ADD COLUMN current_fence_token BIGINT,
  ADD CONSTRAINT rbd_actions_current_fence_token_check
    CHECK (current_fence_token IS NULL OR current_fence_token > 0);
