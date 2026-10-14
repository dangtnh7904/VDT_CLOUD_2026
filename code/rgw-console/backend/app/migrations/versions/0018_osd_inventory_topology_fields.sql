ALTER TABLE osd_inventory_records
  ADD COLUMN crush_location JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN device_class TEXT,
  ADD COLUMN public_ips JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN cluster_ips JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN data_device_size_bytes BIGINT,
  ADD COLUMN db_device_path TEXT,
  ADD COLUMN db_physical_devices JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN db_device_size_bytes BIGINT,
  ADD COLUMN wal_device_path TEXT,
  ADD COLUMN wal_physical_devices JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN wal_device_size_bytes BIGINT,
  ADD COLUMN device_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN daemon_status TEXT,
  ADD COLUMN ceph_version_short TEXT,
  ADD COLUMN container_image TEXT,
  ADD COLUMN container_image_id TEXT,
  ADD CONSTRAINT osd_inventory_record_crush_location_check
    CHECK (jsonb_typeof(crush_location) = 'object'),
  ADD CONSTRAINT osd_inventory_record_public_ips_check
    CHECK (jsonb_typeof(public_ips) = 'array'),
  ADD CONSTRAINT osd_inventory_record_cluster_ips_check
    CHECK (jsonb_typeof(cluster_ips) = 'array'),
  ADD CONSTRAINT osd_inventory_record_db_devices_check
    CHECK (jsonb_typeof(db_physical_devices) = 'array'),
  ADD CONSTRAINT osd_inventory_record_wal_devices_check
    CHECK (jsonb_typeof(wal_physical_devices) = 'array'),
  ADD CONSTRAINT osd_inventory_record_device_ids_check
    CHECK (jsonb_typeof(device_ids) = 'array'),
  ADD CONSTRAINT osd_inventory_record_role_size_check CHECK (
    (data_device_size_bytes IS NULL OR data_device_size_bytes >= 0) AND
    (db_device_size_bytes IS NULL OR db_device_size_bytes >= 0) AND
    (wal_device_size_bytes IS NULL OR wal_device_size_bytes >= 0)
  );

CREATE INDEX osd_inventory_records_topology_idx
  ON osd_inventory_records(device_class, hostname, osd_id);

CREATE INDEX osd_inventory_records_crush_location_gin_idx
  ON osd_inventory_records USING GIN (crush_location);
