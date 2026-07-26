CREATE TABLE IF NOT EXISTS prediction_snapshots (
    snapshot_id VARCHAR(32) PRIMARY KEY,
    fixture_id VARCHAR(32) NOT NULL,
    update_id VARCHAR(32) NOT NULL,
    season VARCHAR(10) NOT NULL,
    matchday INTEGER NOT NULL,
    reference_date DATE NOT NULL,
    scheduled_date TIMESTAMP NULL,
    home_team VARCHAR(128) NOT NULL,
    away_team VARCHAR(128) NOT NULL,
    captured_at_utc TIMESTAMPTZ NOT NULL,
    model VARCHAR(32) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    probability_home DOUBLE PRECISION NOT NULL,
    probability_draw DOUBLE PRECISION NOT NULL,
    probability_away DOUBLE PRECISION NOT NULL,
    predicted_ftr VARCHAR(1) NOT NULL,
    confidence VARCHAR(16) NOT NULL,
    expected_home_goals DOUBLE PRECISION NOT NULL,
    expected_away_goals DOUBLE PRECISION NOT NULL,
    predicted_score VARCHAR(16) NOT NULL,
    market_probability_home DOUBLE PRECISION NULL,
    market_probability_draw DOUBLE PRECISION NULL,
    market_probability_away DOUBLE PRECISION NULL,
    odds_b365_home DOUBLE PRECISION NULL,
    odds_b365_draw DOUBLE PRECISION NULL,
    odds_b365_away DOUBLE PRECISION NULL,
    is_pre_match BOOLEAN NOT NULL,
    capture_source VARCHAR(24) NOT NULL,
    CONSTRAINT uq_prediction_snapshot_version
        UNIQUE (fixture_id, update_id, model_version)
);

CREATE INDEX IF NOT EXISTS ix_prediction_snapshots_fixture_time
    ON prediction_snapshots (fixture_id, captured_at_utc DESC);
CREATE INDEX IF NOT EXISTS ix_prediction_snapshots_matchday
    ON prediction_snapshots (matchday);

CREATE TABLE IF NOT EXISTS prediction_evaluations (
    fixture_id VARCHAR(32) PRIMARY KEY,
    snapshot_id VARCHAR(32) NOT NULL UNIQUE,
    season VARCHAR(10) NOT NULL,
    matchday INTEGER NOT NULL,
    played_date DATE NOT NULL,
    home_team VARCHAR(128) NOT NULL,
    away_team VARCHAR(128) NOT NULL,
    home_goals INTEGER NOT NULL,
    away_goals INTEGER NOT NULL,
    actual_ftr VARCHAR(1) NOT NULL,
    predicted_ftr VARCHAR(1) NOT NULL,
    probability_home DOUBLE PRECISION NOT NULL,
    probability_draw DOUBLE PRECISION NOT NULL,
    probability_away DOUBLE PRECISION NOT NULL,
    correct BOOLEAN NOT NULL,
    log_loss DOUBLE PRECISION NOT NULL,
    brier_score DOUBLE PRECISION NOT NULL,
    market_predicted_ftr VARCHAR(1) NULL,
    market_log_loss DOUBLE PRECISION NULL,
    market_brier_score DOUBLE PRECISION NULL,
    model_version VARCHAR(64) NOT NULL,
    prediction_captured_at_utc TIMESTAMPTZ NOT NULL,
    evaluated_at_utc TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_prediction_evaluations_matchday
    ON prediction_evaluations (matchday);
CREATE INDEX IF NOT EXISTS ix_prediction_evaluations_model
    ON prediction_evaluations (model_version);
