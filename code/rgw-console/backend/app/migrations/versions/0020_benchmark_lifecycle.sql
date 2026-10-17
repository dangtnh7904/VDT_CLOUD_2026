-- Preserve the actual workload lifecycle instead of labelling stopped runs successful.
ALTER TABLE qos_runs DROP CONSTRAINT qos_runs_state_check;
ALTER TABLE qos_runs ADD CONSTRAINT qos_runs_state_check CHECK (state IN (
    'CREATED', 'STARTING', 'RUNNING', 'PAUSED', 'STOPPING', 'COMPLETED',
    'FAILED', 'STOPPED', 'TIMED_OUT', 'LOST'
));
CREATE INDEX idx_qos_live_asset ON qos_runs (fsid, (run_config->'profile'->>'asset_id'))
    WHERE state IN ('STARTING', 'RUNNING', 'PAUSED', 'STOPPING', 'LOST');
