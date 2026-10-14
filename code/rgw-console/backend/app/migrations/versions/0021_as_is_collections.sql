-- New independent collections. Historical sessions and evidence stay untouched.
CREATE TABLE as_is_collections (
    id uuid PRIMARY KEY,
    cluster_id text NOT NULL,
    fsid uuid NOT NULL,
    phase text NOT NULL CHECK (phase IN ('BEFORE', 'DURING', 'AFTER')),
    note text NOT NULL DEFAULT '',
    actor text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    quality text NOT NULL CHECK (quality IN ('VALID', 'PARTIAL')),
    daemon_keys text[] NOT NULL,
    daemon_types text[] NOT NULL,
    payload jsonb NOT NULL,
    sha256 text NOT NULL CHECK (length(sha256) = 64),
    request_hash text NOT NULL,
    deleted_at timestamptz,
    deleted_by text
);
CREATE INDEX as_is_collections_history ON as_is_collections (cluster_id, fsid, started_at DESC);
CREATE INDEX as_is_collections_types ON as_is_collections USING gin (daemon_types);
CREATE TABLE as_is_collection_events (
    id bigserial PRIMARY KEY,
    collection_id uuid NOT NULL REFERENCES as_is_collections(id),
    event_type text NOT NULL CHECK (event_type IN ('CREATED', 'DELETED', 'RESTORED')),
    actor text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    sha256 text NOT NULL
);
