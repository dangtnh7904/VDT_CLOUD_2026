ALTER TABLE osd_inventory_collections
  ADD COLUMN health_status TEXT,
  ADD COLUMN health_checks JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN osdmap_epoch BIGINT,
  ADD COLUMN cluster_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN pool_summaries JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN version_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN cluster_pg_count INTEGER,
  ADD COLUMN cluster_osd_count INTEGER,
  ADD COLUMN cluster_up_osd_count INTEGER,
  ADD COLUMN cluster_in_osd_count INTEGER,
  ADD CONSTRAINT osd_inventory_health_checks_check
    CHECK (jsonb_typeof(health_checks) = 'object'),
  ADD CONSTRAINT osd_inventory_cluster_flags_check
    CHECK (jsonb_typeof(cluster_flags) = 'array'),
  ADD CONSTRAINT osd_inventory_pool_summaries_check
    CHECK (jsonb_typeof(pool_summaries) = 'array'),
  ADD CONSTRAINT osd_inventory_version_summary_check
    CHECK (jsonb_typeof(version_summary) = 'object'),
  ADD CONSTRAINT osd_inventory_cluster_counters_check CHECK (
    (osdmap_epoch IS NULL OR osdmap_epoch >= 0) AND
    (cluster_pg_count IS NULL OR cluster_pg_count >= 0) AND
    (cluster_osd_count IS NULL OR cluster_osd_count >= 0) AND
    (cluster_up_osd_count IS NULL OR cluster_up_osd_count >= 0) AND
    (cluster_in_osd_count IS NULL OR cluster_in_osd_count >= 0)
  );

CREATE INDEX osd_inventory_collections_health_epoch_idx
  ON osd_inventory_collections(health_status, osdmap_epoch DESC);
