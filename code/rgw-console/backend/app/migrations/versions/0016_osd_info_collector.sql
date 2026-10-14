CREATE TABLE osd_inventory_collections (
  id UUID PRIMARY KEY,
  action_job_id UUID NOT NULL UNIQUE REFERENCES action_jobs(id) ON DELETE RESTRICT,
  cluster_id TEXT NOT NULL,
  fsid UUID NOT NULL,
  config_snapshot_id UUID NOT NULL REFERENCES config_snapshots(id) ON DELETE RESTRICT,
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  phase TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'RUNNING',
  requested_osd_ids INTEGER[] NOT NULL,
  collector_version TEXT,
  quality TEXT,
  evidence_artifact_id UUID UNIQUE REFERENCES evidence_artifacts(id) ON DELETE RESTRICT,
  artifact_sha256 TEXT,
  osd_count INTEGER,
  collected_at TIMESTAMPTZ,
  error_code TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT osd_inventory_phase_check CHECK (
    phase IN ('MANUAL', 'BEFORE', 'DURING', 'AFTER_START', 'AFTER_STABLE')
  ),
  CONSTRAINT osd_inventory_state_check CHECK (state IN ('RUNNING', 'COMPLETE', 'FAILED')),
  CONSTRAINT osd_inventory_quality_check CHECK (
    quality IS NULL OR quality IN ('VALID', 'PARTIAL', 'INCONCLUSIVE')
  ),
  CONSTRAINT osd_inventory_requested_check CHECK (
    cardinality(requested_osd_ids) BETWEEN 1 AND 128
  ),
  CONSTRAINT osd_inventory_hash_check CHECK (
    artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT osd_inventory_count_check CHECK (osd_count IS NULL OR osd_count >= 0),
  CONSTRAINT osd_inventory_complete_check CHECK (
    state <> 'COMPLETE' OR (
      quality IS NOT NULL AND evidence_artifact_id IS NOT NULL AND
      artifact_sha256 IS NOT NULL AND osd_count IS NOT NULL AND collected_at IS NOT NULL
    )
  )
);

CREATE INDEX osd_inventory_collections_scope_time_idx
  ON osd_inventory_collections(cluster_id, session_id, collected_at DESC);

CREATE TABLE osd_inventory_records (
  collection_id UUID NOT NULL REFERENCES osd_inventory_collections(id) ON DELETE RESTRICT,
  osd_id INTEGER NOT NULL,
  quality TEXT NOT NULL,
  warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
  errors JSONB NOT NULL DEFAULT '[]'::jsonb,
  osd_fsid TEXT,
  hostname TEXT,
  public_ip TEXT,
  cluster_ip TEXT,
  data_device_path TEXT,
  physical_devices JSONB NOT NULL DEFAULT '[]'::jsonb,
  total_bytes BIGINT,
  used_bytes BIGINT,
  available_bytes BIGINT,
  used_percent DOUBLE PRECISION,
  pg_count INTEGER,
  primary_count INTEGER,
  up BOOLEAN,
  in_cluster BOOLEAN,
  crush_weight DOUBLE PRECISION,
  reweight DOUBLE PRECISION,
  primary_affinity DOUBLE PRECISION,
  ceph_version TEXT,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (collection_id, osd_id),
  CONSTRAINT osd_inventory_record_id_check CHECK (osd_id >= 0),
  CONSTRAINT osd_inventory_record_quality_check CHECK (
    quality IN ('VALID', 'PARTIAL', 'INCONCLUSIVE')
  ),
  CONSTRAINT osd_inventory_record_warnings_check CHECK (jsonb_typeof(warnings) = 'array'),
  CONSTRAINT osd_inventory_record_errors_check CHECK (jsonb_typeof(errors) = 'array'),
  CONSTRAINT osd_inventory_record_devices_check CHECK (jsonb_typeof(physical_devices) = 'array'),
  CONSTRAINT osd_inventory_record_payload_check CHECK (jsonb_typeof(payload) = 'object'),
  CONSTRAINT osd_inventory_record_bytes_check CHECK (
    (total_bytes IS NULL OR total_bytes >= 0) AND
    (used_bytes IS NULL OR used_bytes >= 0) AND
    (available_bytes IS NULL OR available_bytes >= 0)
  ),
  CONSTRAINT osd_inventory_record_pg_check CHECK (
    (pg_count IS NULL OR pg_count >= 0) AND
    (primary_count IS NULL OR primary_count >= 0)
  )
);

CREATE INDEX osd_inventory_records_host_idx
  ON osd_inventory_records(hostname, osd_id);
