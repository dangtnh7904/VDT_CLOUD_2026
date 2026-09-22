ALTER TABLE stream_objects
  ADD COLUMN claim_owner TEXT,
  ADD COLUMN claim_generation BIGINT,
  ADD COLUMN claim_expires_at TIMESTAMPTZ;

ALTER TABLE stream_objects
  ADD CONSTRAINT stream_objects_claim_generation_check
    CHECK (claim_generation IS NULL OR claim_generation >= 0),
  ADD CONSTRAINT stream_objects_claim_shape_check CHECK (
    (
      state IN ('UPDATING', 'DELETING')
      AND claim_owner IS NOT NULL
      AND claim_generation IS NOT NULL
      AND claim_expires_at IS NOT NULL
    )
    OR (
      state NOT IN ('UPDATING', 'DELETING')
      AND claim_owner IS NULL
      AND claim_generation IS NULL
      AND claim_expires_at IS NULL
    )
  );

CREATE INDEX stream_objects_claim_idx
  ON stream_objects(job_id, state, claim_expires_at)
  WHERE state IN ('UPDATING', 'DELETING');
