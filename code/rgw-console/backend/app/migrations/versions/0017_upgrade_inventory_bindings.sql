CREATE TABLE upgrade_inventory_bindings (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES upgrade_runs(id) ON DELETE RESTRICT,
  collection_id UUID NOT NULL REFERENCES osd_inventory_collections(id) ON DELETE RESTRICT,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id) ON DELETE RESTRICT,
  plan_revision BIGINT NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'PLAN_BASELINE',
  artifact_sha256 TEXT NOT NULL,
  collected_at TIMESTAMPTZ NOT NULL,
  max_age_seconds DOUBLE PRECISION NOT NULL,
  readiness_result TEXT NOT NULL,
  reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
  observed JSONB NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  reason TEXT NOT NULL,
  bound_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT upgrade_inventory_binding_revision_check CHECK (plan_revision > 0),
  CONSTRAINT upgrade_inventory_binding_purpose_check CHECK (purpose = 'PLAN_BASELINE'),
  CONSTRAINT upgrade_inventory_binding_hash_check CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT upgrade_inventory_binding_age_check CHECK (max_age_seconds > 0),
  CONSTRAINT upgrade_inventory_binding_result_check CHECK (readiness_result = 'READY'),
  CONSTRAINT upgrade_inventory_binding_reasons_check CHECK (jsonb_typeof(reasons) = 'array'),
  CONSTRAINT upgrade_inventory_binding_observed_check CHECK (jsonb_typeof(observed) = 'object'),
  CONSTRAINT upgrade_inventory_binding_fingerprint_check CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  CONSTRAINT upgrade_inventory_binding_reason_check CHECK (length(reason) BETWEEN 1 AND 1000),
  CONSTRAINT upgrade_inventory_binding_idempotency_unique UNIQUE (cluster_id, idempotency_key)
);

CREATE INDEX upgrade_inventory_bindings_run_revision_idx
  ON upgrade_inventory_bindings(run_id, plan_revision, bound_at DESC);

ALTER TABLE placement_plans
  ADD COLUMN osd_inventory_binding_id UUID
  REFERENCES upgrade_inventory_bindings(id) ON DELETE RESTRICT;

CREATE INDEX placement_plans_osd_inventory_binding_idx
  ON placement_plans(osd_inventory_binding_id)
  WHERE osd_inventory_binding_id IS NOT NULL;
