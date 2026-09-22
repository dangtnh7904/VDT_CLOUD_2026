ALTER TABLE stream_jobs
  ADD COLUMN job_type TEXT NOT NULL DEFAULT 'legacy_put',
  ADD COLUMN lease_owner TEXT,
  ADD COLUMN lease_generation BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN lease_expires_at TIMESTAMPTZ,
  ADD COLUMN heartbeat_at TIMESTAMPTZ,
  ADD COLUMN paused_reason TEXT,
  ADD COLUMN operation_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN operation_bytes JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE stream_jobs
  ADD CONSTRAINT stream_jobs_lease_generation_check CHECK (lease_generation >= 0),
  ADD CONSTRAINT stream_jobs_operation_counts_object_check
    CHECK (jsonb_typeof(operation_counts) = 'object'),
  ADD CONSTRAINT stream_jobs_operation_bytes_object_check
    CHECK (jsonb_typeof(operation_bytes) = 'object');

CREATE INDEX stream_jobs_lease_idx
  ON stream_jobs(state, lease_expires_at)
  WHERE state IN ('pending', 'running', 'paused', 'stopping');

CREATE TABLE idempotency_requests (
  id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  http_method TEXT NOT NULL,
  resource TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'CLAIMED',
  owner_id TEXT,
  fencing_generation BIGINT NOT NULL DEFAULT 0,
  request_id UUID NOT NULL,
  action_id UUID,
  response_status INTEGER,
  response_body JSONB,
  error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT idempotency_requests_scope_key_unique UNIQUE (scope, idempotency_key),
  CONSTRAINT idempotency_requests_request_id_unique UNIQUE (request_id),
  CONSTRAINT idempotency_requests_state_check CHECK (
    state IN (
      'CLAIMED',
      'IN_PROGRESS',
      'SUCCEEDED',
      'FAILED_RETRYABLE',
      'FAILED_FINAL'
    )
  ),
  CONSTRAINT idempotency_requests_fencing_generation_check
    CHECK (fencing_generation >= 0),
  CONSTRAINT idempotency_requests_response_status_check
    CHECK (response_status IS NULL OR response_status BETWEEN 100 AND 599),
  CONSTRAINT idempotency_requests_completion_check CHECK (
    (state IN ('SUCCEEDED', 'FAILED_FINAL') AND completed_at IS NOT NULL)
    OR state IN ('CLAIMED', 'IN_PROGRESS', 'FAILED_RETRYABLE')
  )
);

CREATE UNIQUE INDEX idempotency_requests_action_id_unique
  ON idempotency_requests(action_id)
  WHERE action_id IS NOT NULL;
CREATE INDEX idempotency_requests_state_idx
  ON idempotency_requests(state, updated_at);

CREATE TABLE capacity_snapshots (
  id BIGSERIAL PRIMARY KEY,
  fsid TEXT NOT NULL,
  osdmap_epoch BIGINT NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL,
  collector_version TEXT NOT NULL,
  fresh BOOLEAN NOT NULL,
  cluster_health_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT capacity_snapshots_epoch_check CHECK (osdmap_epoch >= 0),
  CONSTRAINT capacity_snapshots_health_object_check
    CHECK (jsonb_typeof(cluster_health_summary) = 'object'),
  CONSTRAINT capacity_snapshots_identity_unique
    UNIQUE (fsid, osdmap_epoch, captured_at)
);

CREATE INDEX capacity_snapshots_scope_time_idx
  ON capacity_snapshots(fsid, captured_at DESC);

CREATE TABLE capacity_osds (
  snapshot_id BIGINT NOT NULL REFERENCES capacity_snapshots(id) ON DELETE CASCADE,
  osd_id INTEGER NOT NULL,
  total_bytes BIGINT NOT NULL,
  used_bytes BIGINT NOT NULL,
  available_bytes BIGINT NOT NULL,
  used_ratio DOUBLE PRECISION NOT NULL,
  is_up BOOLEAN NOT NULL,
  is_in BOOLEAN NOT NULL,
  host TEXT,
  device_class TEXT,
  scope_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (snapshot_id, osd_id),
  CONSTRAINT capacity_osds_id_check CHECK (osd_id >= 0),
  CONSTRAINT capacity_osds_bytes_check CHECK (
    total_bytes >= 0 AND used_bytes >= 0 AND available_bytes >= 0
  ),
  CONSTRAINT capacity_osds_ratio_check CHECK (used_ratio >= 0),
  CONSTRAINT capacity_osds_scope_object_check
    CHECK (jsonb_typeof(scope_metadata) = 'object')
);

CREATE INDEX capacity_osds_osd_snapshot_idx
  ON capacity_osds(osd_id, snapshot_id DESC);

CREATE TABLE capacity_decisions (
  id UUID PRIMARY KEY,
  request_id UUID,
  job_id UUID REFERENCES stream_jobs(id) ON DELETE SET NULL,
  action_id UUID,
  policy_version TEXT NOT NULL,
  snapshot_id BIGINT REFERENCES capacity_snapshots(id) ON DELETE RESTRICT,
  osdmap_epoch BIGINT,
  state TEXT NOT NULL,
  reason TEXT,
  reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
  participating_osds INTEGER[] NOT NULL DEFAULT '{}'::integer[],
  projected_ratios JSONB NOT NULL DEFAULT '{}'::jsonb,
  decision TEXT NOT NULL,
  inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT capacity_decisions_epoch_check
    CHECK (osdmap_epoch IS NULL OR osdmap_epoch >= 0),
  CONSTRAINT capacity_decisions_state_check CHECK (
    state IN (
      'NORMAL',
      'THROTTLED',
      'PAUSED_CAPACITY',
      'EMERGENCY_CAPACITY',
      'BLOCKED_TELEMETRY',
      'BLOCKED_UNKNOWN_CAPACITY',
      'RECONCILING',
      'PAUSED_REMAP',
      'READ_CLEANUP_ONLY'
    )
  ),
  CONSTRAINT capacity_decisions_decision_check
    CHECK (decision IN ('ADMIT', 'THROTTLE', 'BLOCK')),
  CONSTRAINT capacity_decisions_reasons_array_check
    CHECK (jsonb_typeof(reasons) = 'array'),
  CONSTRAINT capacity_decisions_projected_object_check
    CHECK (jsonb_typeof(projected_ratios) = 'object'),
  CONSTRAINT capacity_decisions_inputs_object_check
    CHECK (jsonb_typeof(inputs) = 'object')
);

CREATE INDEX capacity_decisions_created_idx
  ON capacity_decisions(created_at DESC);
CREATE INDEX capacity_decisions_job_idx
  ON capacity_decisions(job_id, created_at DESC)
  WHERE job_id IS NOT NULL;

CREATE TABLE capacity_reservations (
  id UUID PRIMARY KEY,
  decision_id UUID NOT NULL REFERENCES capacity_decisions(id) ON DELETE RESTRICT,
  owner_type TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  fsid TEXT NOT NULL,
  osdmap_epoch BIGINT NOT NULL,
  affected_pools TEXT[] NOT NULL,
  logical_bytes BIGINT NOT NULL,
  estimated_raw_bytes BIGINT NOT NULL,
  remaining_commitment_bytes BIGINT NOT NULL DEFAULT 0,
  reservation_class TEXT NOT NULL,
  lease_owner TEXT,
  lease_generation BIGINT NOT NULL DEFAULT 0,
  heartbeat_at TIMESTAMPTZ,
  lease_expires_at TIMESTAMPTZ,
  state TEXT NOT NULL DEFAULT 'PENDING',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  settled_at TIMESTAMPTZ,
  released_at TIMESTAMPTZ,
  CONSTRAINT capacity_reservations_owner_type_check
    CHECK (owner_type IN ('REQUEST', 'JOB', 'VOLUME')),
  CONSTRAINT capacity_reservations_epoch_check CHECK (osdmap_epoch >= 0),
  CONSTRAINT capacity_reservations_pools_check CHECK (cardinality(affected_pools) > 0),
  CONSTRAINT capacity_reservations_bytes_check CHECK (
    logical_bytes >= 0
    AND estimated_raw_bytes >= 0
    AND remaining_commitment_bytes >= 0
  ),
  CONSTRAINT capacity_reservations_class_check
    CHECK (reservation_class IN ('TRANSIENT_OPERATION', 'PERSISTENT_VOLUME')),
  CONSTRAINT capacity_reservations_lease_generation_check CHECK (lease_generation >= 0),
  CONSTRAINT capacity_reservations_state_check CHECK (
    state IN (
      'PENDING',
      'IN_FLIGHT',
      'LEASE_EXPIRED_UNRECONCILED',
      'SETTLING',
      'PERSISTENT_COMMITMENT',
      'RELEASED'
    )
  )
);

CREATE INDEX capacity_reservations_scope_state_idx
  ON capacity_reservations(fsid, state, created_at);
CREATE INDEX capacity_reservations_lease_idx
  ON capacity_reservations(lease_expires_at)
  WHERE state IN ('PENDING', 'IN_FLIGHT');
CREATE INDEX capacity_reservations_owner_idx
  ON capacity_reservations(owner_type, owner_id, state);

CREATE TABLE capacity_reservation_allocations (
  reservation_id UUID NOT NULL
    REFERENCES capacity_reservations(id) ON DELETE CASCADE,
  pool_id BIGINT NOT NULL,
  pool_name TEXT NOT NULL,
  osd_id INTEGER NOT NULL,
  estimated_bytes BIGINT NOT NULL,
  PRIMARY KEY (reservation_id, pool_id, osd_id),
  CONSTRAINT capacity_reservation_allocations_pool_check CHECK (pool_id >= 0),
  CONSTRAINT capacity_reservation_allocations_osd_check CHECK (osd_id >= 0),
  CONSTRAINT capacity_reservation_allocations_bytes_check CHECK (estimated_bytes >= 0)
);

CREATE INDEX capacity_reservation_allocations_osd_idx
  ON capacity_reservation_allocations(osd_id, reservation_id);

CREATE TABLE rbd_volumes (
  id UUID PRIMARY KEY,
  pool TEXT NOT NULL,
  namespace TEXT,
  image_name TEXT NOT NULL,
  image_id TEXT,
  display_name TEXT,
  logical_size_bytes BIGINT NOT NULL,
  actual_allocated_bytes BIGINT,
  reserved_raw_bytes BIGINT NOT NULL DEFAULT 0,
  capacity_mode TEXT NOT NULL DEFAULT 'reserved-logical',
  feature_set TEXT[] NOT NULL DEFAULT '{}'::text[],
  desired_state TEXT NOT NULL DEFAULT 'REQUESTED',
  observed_state TEXT NOT NULL DEFAULT 'REQUESTED',
  device TEXT,
  device_major INTEGER,
  device_minor INTEGER,
  fs_uuid TEXT,
  mountpoint TEXT,
  capacity_reservation_id UUID
    REFERENCES capacity_reservations(id) ON DELETE RESTRICT,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT rbd_volumes_logical_size_check CHECK (logical_size_bytes > 0),
  CONSTRAINT rbd_volumes_allocation_check CHECK (
    (actual_allocated_bytes IS NULL OR actual_allocated_bytes >= 0)
    AND reserved_raw_bytes >= 0
  ),
  CONSTRAINT rbd_volumes_capacity_mode_check
    CHECK (capacity_mode IN ('reserved-logical', 'actual-use')),
  CONSTRAINT rbd_volumes_desired_state_check CHECK (
    desired_state IN (
      'REQUESTED', 'CAPACITY_RESERVED', 'CREATED', 'MAPPING', 'MAPPED',
      'FORMATTED', 'MOUNTING', 'MOUNTED', 'READY', 'UNMOUNTING', 'UNMOUNTED',
      'UNMAPPING', 'UNMAPPED', 'DELETING', 'DELETED', 'BLOCKED_CAPACITY',
      'BLOCKED_CLUSTER_HEALTH', 'MAP_FAILED', 'FORMAT_FAILED', 'MOUNT_FAILED',
      'BUSY', 'DELETE_BLOCKED_DEPENDENCY', 'RECONCILING', 'UNKNOWN'
    )
  ),
  CONSTRAINT rbd_volumes_observed_state_check CHECK (
    observed_state IN (
      'REQUESTED', 'CAPACITY_RESERVED', 'CREATED', 'MAPPING', 'MAPPED',
      'FORMATTED', 'MOUNTING', 'MOUNTED', 'READY', 'UNMOUNTING', 'UNMOUNTED',
      'UNMAPPING', 'UNMAPPED', 'DELETING', 'DELETED', 'BLOCKED_CAPACITY',
      'BLOCKED_CLUSTER_HEALTH', 'MAP_FAILED', 'FORMAT_FAILED', 'MOUNT_FAILED',
      'BUSY', 'DELETE_BLOCKED_DEPENDENCY', 'RECONCILING', 'UNKNOWN'
    )
  ),
  CONSTRAINT rbd_volumes_device_numbers_check CHECK (
    (device_major IS NULL AND device_minor IS NULL)
    OR (device_major >= 0 AND device_minor >= 0)
  )
);

CREATE UNIQUE INDEX rbd_volumes_pool_namespace_name_unique
  ON rbd_volumes(pool, COALESCE(namespace, ''), image_name);
CREATE UNIQUE INDEX rbd_volumes_image_id_unique
  ON rbd_volumes(pool, COALESCE(namespace, ''), image_id)
  WHERE image_id IS NOT NULL;
CREATE INDEX rbd_volumes_state_idx
  ON rbd_volumes(observed_state, updated_at);

CREATE TABLE rbd_actions (
  id UUID PRIMARY KEY,
  idempotency_request_id BIGINT NOT NULL UNIQUE
    REFERENCES idempotency_requests(id) ON DELETE RESTRICT,
  volume_id UUID NOT NULL REFERENCES rbd_volumes(id) ON DELETE RESTRICT,
  action_type TEXT NOT NULL,
  intended_state TEXT NOT NULL,
  observed_state TEXT,
  state TEXT NOT NULL DEFAULT 'PENDING',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  timeout_seconds INTEGER,
  exit_code INTEGER,
  redacted_result JSONB,
  error_code TEXT,
  error TEXT,
  CONSTRAINT rbd_actions_type_check CHECK (
    action_type IN (
      'CREATE', 'MAP', 'FORMAT', 'MOUNT', 'FILE_LIST', 'FILE_READ',
      'FILE_WRITE', 'FILE_DELETE', 'MKDIR', 'UNMOUNT', 'UNMAP', 'DELETE',
      'RECONCILE'
    )
  ),
  CONSTRAINT rbd_actions_state_check CHECK (
    state IN (
      'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_FINAL',
      'RECONCILING'
    )
  ),
  CONSTRAINT rbd_actions_timeout_check
    CHECK (timeout_seconds IS NULL OR timeout_seconds > 0),
  CONSTRAINT rbd_actions_result_object_check
    CHECK (redacted_result IS NULL OR jsonb_typeof(redacted_result) = 'object')
);

CREATE INDEX rbd_actions_volume_time_idx
  ON rbd_actions(volume_id, created_at DESC);
CREATE INDEX rbd_actions_state_idx
  ON rbd_actions(state, created_at);

CREATE TABLE stream_objects (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES stream_jobs(id) ON DELETE RESTRICT,
  bucket TEXT NOT NULL,
  object_key TEXT NOT NULL,
  version_id TEXT,
  synthetic_unversioned_id UUID,
  is_delete_marker BOOLEAN NOT NULL DEFAULT false,
  size_bytes BIGINT NOT NULL DEFAULT 0,
  etag TEXT,
  checksum TEXT,
  state TEXT NOT NULL DEFAULT 'LIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT stream_objects_version_identity_check CHECK (
    num_nonnulls(version_id, synthetic_unversioned_id) = 1
  ),
  CONSTRAINT stream_objects_size_check CHECK (size_bytes >= 0),
  CONSTRAINT stream_objects_state_check
    CHECK (state IN ('LIVE', 'UPDATING', 'DELETING', 'DELETED', 'UNKNOWN'))
);

CREATE UNIQUE INDEX stream_objects_version_unique
  ON stream_objects(bucket, object_key, version_id)
  WHERE version_id IS NOT NULL;
CREATE UNIQUE INDEX stream_objects_synthetic_unique
  ON stream_objects(bucket, object_key, synthetic_unversioned_id)
  WHERE synthetic_unversioned_id IS NOT NULL;
CREATE INDEX stream_objects_job_state_idx
  ON stream_objects(job_id, state, updated_at);
CREATE INDEX stream_objects_key_idx
  ON stream_objects(bucket, object_key, created_at DESC);

CREATE TABLE stream_object_heads (
  bucket TEXT NOT NULL,
  object_key TEXT NOT NULL,
  stream_object_id BIGINT NOT NULL UNIQUE
    REFERENCES stream_objects(id) ON DELETE RESTRICT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (bucket, object_key)
);

ALTER TABLE operations
  DROP CONSTRAINT operations_kind_check,
  ALTER COLUMN bucket DROP NOT NULL,
  ALTER COLUMN object_key DROP NOT NULL,
  ADD COLUMN request_id UUID,
  ADD COLUMN job_id UUID REFERENCES stream_jobs(id) ON DELETE SET NULL,
  ADD COLUMN volume_id UUID REFERENCES rbd_volumes(id) ON DELETE RESTRICT,
  ADD COLUMN target_type TEXT,
  ADD COLUMN target_id TEXT,
  ADD COLUMN bytes_delta_logical BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN estimated_bytes_delta_raw BIGINT,
  ADD COLUMN capacity_decision_id UUID
    REFERENCES capacity_decisions(id) ON DELETE SET NULL,
  ADD COLUMN osdmap_epoch BIGINT,
  ADD COLUMN error_code TEXT;

UPDATE operations
SET target_type = 'RGW_OBJECT',
    target_id = format(
      'rgw:%s:%s:%s',
      octet_length(bucket),
      bucket,
      object_key
    );

ALTER TABLE operations
  ALTER COLUMN target_type SET NOT NULL,
  ALTER COLUMN target_id SET NOT NULL,
  ADD CONSTRAINT operations_kind_check CHECK (
    kind IN (
      'PUT', 'GET', 'HEAD', 'LIST', 'UPDATE', 'DELETE',
      'RBD_CREATE', 'RBD_MAP', 'RBD_FORMAT', 'RBD_MOUNT',
      'RBD_FILE_READ', 'RBD_FILE_WRITE', 'RBD_FILE_DELETE',
      'RBD_UNMOUNT', 'RBD_UNMAP', 'RBD_DELETE'
    )
  ),
  ADD CONSTRAINT operations_target_type_check CHECK (
    target_type IN ('RGW_OBJECT', 'RGW_BUCKET', 'RBD_VOLUME', 'RBD_FILE')
  ),
  ADD CONSTRAINT operations_target_id_check CHECK (target_id <> ''),
  ADD CONSTRAINT operations_target_shape_check CHECK (
    (
      kind IN ('PUT', 'GET', 'HEAD', 'UPDATE', 'DELETE')
      AND target_type = 'RGW_OBJECT'
      AND bucket IS NOT NULL
      AND object_key IS NOT NULL
    )
    OR (
      kind = 'LIST'
      AND target_type IN ('RGW_BUCKET', 'RGW_OBJECT')
      AND bucket IS NOT NULL
    )
    OR (
      kind IN ('RBD_FILE_READ', 'RBD_FILE_WRITE', 'RBD_FILE_DELETE')
      AND target_type = 'RBD_FILE'
      AND volume_id IS NOT NULL
    )
    OR (
      kind IN (
        'RBD_CREATE', 'RBD_MAP', 'RBD_FORMAT', 'RBD_MOUNT',
        'RBD_UNMOUNT', 'RBD_UNMAP', 'RBD_DELETE'
      )
      AND target_type = 'RBD_VOLUME'
      AND volume_id IS NOT NULL
    )
  ),
  ADD CONSTRAINT operations_osdmap_epoch_check
    CHECK (osdmap_epoch IS NULL OR osdmap_epoch >= 0);

CREATE INDEX operations_target_idx
  ON operations(target_type, target_id, created_at DESC);
CREATE INDEX operations_request_idx
  ON operations(request_id)
  WHERE request_id IS NOT NULL;
CREATE INDEX operations_job_idx
  ON operations(job_id, created_at DESC)
  WHERE job_id IS NOT NULL;
CREATE INDEX operations_volume_idx
  ON operations(volume_id, created_at DESC)
  WHERE volume_id IS NOT NULL;

CREATE TABLE control_state (
  id BOOLEAN PRIMARY KEY DEFAULT true,
  desired_state TEXT NOT NULL DEFAULT 'NORMAL',
  reason TEXT,
  action_id UUID,
  idempotency_request_id BIGINT
    REFERENCES idempotency_requests(id) ON DELETE RESTRICT,
  version BIGINT NOT NULL DEFAULT 0,
  updated_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT control_state_singleton_check CHECK (id),
  CONSTRAINT control_state_desired_state_check
    CHECK (desired_state IN ('NORMAL', 'READ_CLEANUP_ONLY')),
  CONSTRAINT control_state_version_check CHECK (version >= 0)
);

INSERT INTO control_state (id, desired_state)
VALUES (true, 'NORMAL');
