CREATE TABLE IF NOT EXISTS fixtures (
    fixture_id VARCHAR(32) PRIMARY KEY,
    season VARCHAR(10) NOT NULL,
    matchday INTEGER NOT NULL CHECK (matchday BETWEEN 1 AND 38),
    reference_date DATE NOT NULL,
    scheduled_date TIMESTAMP NULL,
    kickoff_time VARCHAR(16) NULL,
    home_team_id VARCHAR(64) NOT NULL,
    home_team VARCHAR(128) NOT NULL,
    home_team_official VARCHAR(128) NOT NULL,
    away_team_id VARCHAR(64) NOT NULL,
    away_team VARCHAR(128) NOT NULL,
    away_team_official VARCHAR(128) NOT NULL,
    status VARCHAR(24) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_fixtures_matchday
    ON fixtures (matchday, fixture_id);
CREATE INDEX IF NOT EXISTS ix_fixtures_home_team
    ON fixtures (home_team_id);
CREATE INDEX IF NOT EXISTS ix_fixtures_away_team
    ON fixtures (away_team_id);

CREATE TABLE IF NOT EXISTS match_results (
    fixture_id VARCHAR(32) PRIMARY KEY
        REFERENCES fixtures(fixture_id) ON DELETE CASCADE,
    played_date DATE NOT NULL,
    home_goals INTEGER NOT NULL CHECK (home_goals >= 0),
    away_goals INTEGER NOT NULL CHECK (away_goals >= 0),
    result CHAR(1) NOT NULL CHECK (result IN ('H', 'D', 'A')),
    home_shots DOUBLE PRECISION NULL,
    away_shots DOUBLE PRECISION NULL,
    home_shots_on_target DOUBLE PRECISION NULL,
    away_shots_on_target DOUBLE PRECISION NULL,
    home_corners DOUBLE PRECISION NULL,
    away_corners DOUBLE PRECISION NULL,
    home_yellow_cards DOUBLE PRECISION NULL,
    away_yellow_cards DOUBLE PRECISION NULL,
    home_red_cards DOUBLE PRECISION NULL,
    away_red_cards DOUBLE PRECISION NULL
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id BIGSERIAL PRIMARY KEY,
    fixture_id VARCHAR(32) NOT NULL
        REFERENCES fixtures(fixture_id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ NOT NULL,
    odds_b365_home DOUBLE PRECISION NOT NULL CHECK (odds_b365_home > 1),
    odds_b365_draw DOUBLE PRECISION NOT NULL CHECK (odds_b365_draw > 1),
    odds_b365_away DOUBLE PRECISION NOT NULL CHECK (odds_b365_away > 1),
    market_probability_home DOUBLE PRECISION NOT NULL,
    market_probability_draw DOUBLE PRECISION NOT NULL,
    market_probability_away DOUBLE PRECISION NOT NULL,
    market_overround DOUBLE PRECISION NOT NULL,
    CONSTRAINT uq_odds_fixture_capture UNIQUE (fixture_id, captured_at)
);

CREATE TABLE IF NOT EXISTS predictions (
    fixture_id VARCHAR(32) PRIMARY KEY
        REFERENCES fixtures(fixture_id) ON DELETE CASCADE,
    model VARCHAR(32) NOT NULL,
    probability_home DOUBLE PRECISION NOT NULL,
    probability_draw DOUBLE PRECISION NOT NULL,
    probability_away DOUBLE PRECISION NOT NULL,
    predicted_ftr CHAR(1) NOT NULL,
    probability_edge DOUBLE PRECISION NOT NULL,
    confidence VARCHAR(16) NOT NULL,
    expected_home_goals DOUBLE PRECISION NOT NULL,
    expected_away_goals DOUBLE PRECISION NOT NULL,
    predicted_score VARCHAR(16) NOT NULL,
    predicted_score_probability DOUBLE PRECISION NOT NULL,
    market_odds_available BOOLEAN NOT NULL,
    promoted_adjustment_applied BOOLEAN NOT NULL,
    feature_snapshot VARCHAR(32) NOT NULL,
    update_id VARCHAR(32) NOT NULL,
    CONSTRAINT ck_prediction_sum CHECK (
        ABS(probability_home + probability_draw + probability_away - 1) < 0.000001
    )
);

CREATE TABLE IF NOT EXISTS standings (
    team_id VARCHAR(64) PRIMARY KEY,
    team VARCHAR(128) UNIQUE NOT NULL,
    played INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    draws INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    goals_for INTEGER NOT NULL,
    goals_against INTEGER NOT NULL,
    goal_difference INTEGER NOT NULL,
    points INTEGER NOT NULL,
    position INTEGER NULL,
    ppg DOUBLE PRECISION NULL,
    update_id VARCHAR(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_summary (
    team_id VARCHAR(64) PRIMARY KEY,
    team VARCHAR(128) UNIQUE NOT NULL,
    simulations INTEGER NOT NULL,
    expected_points DOUBLE PRECISION NOT NULL,
    median_points DOUBLE PRECISION NOT NULL,
    points_p05 DOUBLE PRECISION NOT NULL,
    points_p95 DOUBLE PRECISION NOT NULL,
    expected_position DOUBLE PRECISION NOT NULL,
    median_position DOUBLE PRECISION NOT NULL,
    champion_probability DOUBLE PRECISION NOT NULL,
    top4_probability DOUBLE PRECISION NOT NULL,
    top6_probability DOUBLE PRECISION NOT NULL,
    europe_top7_probability DOUBLE PRECISION NOT NULL,
    relegation_probability DOUBLE PRECISION NOT NULL,
    last_place_probability DOUBLE PRECISION NOT NULL,
    update_id VARCHAR(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS position_probabilities (
    team_id VARCHAR(64) NOT NULL
        REFERENCES simulation_summary(team_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 20),
    probability DOUBLE PRECISION NOT NULL CHECK (
        probability BETWEEN 0 AND 1
    ),
    update_id VARCHAR(32) NOT NULL,
    PRIMARY KEY (team_id, position)
);

CREATE TABLE IF NOT EXISTS update_runs (
    update_id VARCHAR(32) PRIMARY KEY,
    created_at_utc TIMESTAMPTZ NOT NULL,
    snapshot_date DATE NOT NULL,
    completed_matches INTEGER NOT NULL,
    completed_matchdays INTEGER NOT NULL,
    remaining_matches INTEGER NOT NULL,
    next_matchday INTEGER NULL,
    market_predictions INTEGER NOT NULL,
    sports_predictions INTEGER NOT NULL,
    simulations INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    quality_passed BOOLEAN NOT NULL,
    pipeline_mode VARCHAR(32) NOT NULL,
    snapshot_path VARCHAR(512) NULL
);
