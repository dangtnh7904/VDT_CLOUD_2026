CREATE TABLE rbd_validation_runs (
  id UUID PRIMARY KEY,
  volume_id UUID NOT NULL REFERENCES rbd_volumes(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  baseline_label TEXT NOT NULL DEFAULT 'pre-upgrade',
  status TEXT NOT NULL DEFAULT 'BASELINE_RECORDED',
  image_id TEXT NOT NULL,
  fs_uuid UUID NOT NULL,
  baseline_fsid UUID,
  baseline_osdmap_epoch BIGINT,
  manifest JSONB NOT NULL,
  verification JSONB,
  baseline_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT rbd_validation_runs_name_check CHECK (length(name) BETWEEN 1 AND 255),
  CONSTRAINT rbd_validation_runs_status_check CHECK (
    status IN ('BASELINE_RECORDED', 'PASS', 'FAIL', 'ERROR')
  ),
  CONSTRAINT rbd_validation_runs_epoch_check CHECK (
    baseline_osdmap_epoch IS NULL OR baseline_osdmap_epoch >= 0
  ),
  CONSTRAINT rbd_validation_runs_manifest_check CHECK (
    jsonb_typeof(manifest) = 'object'
    AND jsonb_typeof(manifest->'files') = 'array'
  ),
  CONSTRAINT rbd_validation_runs_verification_check CHECK (
    verification IS NULL OR jsonb_typeof(verification) = 'object'
  )
);

CREATE INDEX rbd_validation_runs_volume_time_idx
  ON rbd_validation_runs(volume_id, created_at DESC);
