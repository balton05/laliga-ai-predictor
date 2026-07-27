CREATE TABLE IF NOT EXISTS model_versions (
    version VARCHAR(96) PRIMARY KEY,
    family VARCHAR(48) NOT NULL,
    stage VARCHAR(24) NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL,
    activated_at_utc TIMESTAMPTZ,
    trained_through VARCHAR(16) NOT NULL,
    training_matches INTEGER NOT NULL,
    validation_matches INTEGER NOT NULL,
    transformation VARCHAR(32) NOT NULL,
    parameters_json TEXT NOT NULL,
    artifact_checksum VARCHAR(64) NOT NULL,
    validation_log_loss DOUBLE PRECISION,
    validation_brier_score DOUBLE PRECISION,
    validation_accuracy DOUBLE PRECISION,
    validation_macro_f1 DOUBLE PRECISION,
    eligible_for_promotion BOOLEAN NOT NULL,
    parent_version VARCHAR(96),
    training_run_id VARCHAR(32),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS ix_model_versions_stage
    ON model_versions (stage);
CREATE INDEX IF NOT EXISTS ix_model_versions_created_at
    ON model_versions (created_at_utc);

CREATE TABLE IF NOT EXISTS model_training_runs (
    run_id VARCHAR(32) PRIMARY KEY,
    trigger VARCHAR(24) NOT NULL,
    status VARCHAR(24) NOT NULL,
    started_at_utc TIMESTAMPTZ NOT NULL,
    finished_at_utc TIMESTAMPTZ,
    champion_version VARCHAR(96) NOT NULL,
    candidate_version VARCHAR(96),
    evaluated_matches INTEGER NOT NULL,
    completed_matchdays INTEGER NOT NULL,
    minimum_matches INTEGER NOT NULL,
    minimum_matchdays INTEGER NOT NULL,
    train_matches INTEGER NOT NULL,
    validation_matches INTEGER NOT NULL,
    champion_log_loss DOUBLE PRECISION,
    candidate_log_loss DOUBLE PRECISION,
    log_loss_improvement DOUBLE PRECISION,
    champion_brier_score DOUBLE PRECISION,
    candidate_brier_score DOUBLE PRECISION,
    selected_temperature DOUBLE PRECISION,
    eligible_for_promotion BOOLEAN NOT NULL,
    duration_seconds DOUBLE PRECISION,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS ix_model_training_runs_status
    ON model_training_runs (status);
CREATE INDEX IF NOT EXISTS ix_model_training_runs_started_at
    ON model_training_runs (started_at_utc);
