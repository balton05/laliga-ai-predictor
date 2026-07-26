CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR(32) PRIMARY KEY,
    started_at_utc TIMESTAMPTZ NOT NULL,
    finished_at_utc TIMESTAMPTZ NULL,
    status VARCHAR(24) NOT NULL,
    trigger VARCHAR(24) NOT NULL,
    source VARCHAR(64) NOT NULL,
    source_url VARCHAR(512) NULL,
    source_checksum VARCHAR(64) NULL,
    rows_downloaded INTEGER NOT NULL DEFAULT 0,
    results_discovered INTEGER NOT NULL DEFAULT 0,
    results_added INTEGER NOT NULL DEFAULT 0,
    odds_discovered INTEGER NOT NULL DEFAULT 0,
    odds_added INTEGER NOT NULL DEFAULT 0,
    update_id VARCHAR(32) NULL,
    simulations INTEGER NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    duration_seconds DOUBLE PRECISION NULL,
    error_type VARCHAR(128) NULL,
    error_message TEXT NULL
);

CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started
    ON pipeline_runs (started_at_utc DESC);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_status
    ON pipeline_runs (status);

CREATE TABLE IF NOT EXISTS pipeline_steps (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(32) NOT NULL
        REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    name VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    started_at_utc TIMESTAMPTZ NOT NULL,
    finished_at_utc TIMESTAMPTZ NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL,
    rows_processed INTEGER NULL,
    detail TEXT NULL,
    CONSTRAINT uq_pipeline_step_order UNIQUE (run_id, step_order)
);

CREATE INDEX IF NOT EXISTS ix_pipeline_steps_run
    ON pipeline_steps (run_id, step_order);
