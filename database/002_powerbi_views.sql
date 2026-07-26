-- Fase 11: capa analítica estable para Power BI.
-- Las vistas mantienen el contrato del dashboard separado de las tablas
-- operativas de FastAPI y PostgreSQL.

CREATE OR REPLACE VIEW bi_dim_team AS
SELECT
    s.team_id,
    s.team,
    CASE
        WHEN s.team_id IN ('racing_santander', 'deportivo', 'malaga')
            THEN TRUE
        ELSE FALSE
    END AS is_promoted
FROM simulation_summary AS s;

CREATE OR REPLACE VIEW bi_dim_matchday AS
SELECT
    matchday,
    'Jornada ' || matchday::text AS matchday_label,
    CASE
        WHEN matchday <= 10 THEN 'Inicio'
        WHEN matchday <= 28 THEN 'Desarrollo'
        ELSE 'Recta final'
    END AS season_stage
FROM generate_series(1, 38) AS matchday;

CREATE OR REPLACE VIEW bi_dim_position AS
SELECT
    position,
    CASE
        WHEN position = 1 THEN 'Campeón'
        WHEN position <= 4 THEN 'Champions'
        WHEN position <= 7 THEN 'Europa'
        WHEN position >= 18 THEN 'Descenso'
        ELSE 'Permanencia'
    END AS position_zone
FROM generate_series(1, 20) AS position;

CREATE OR REPLACE VIEW bi_fact_matches AS
WITH latest_odds AS (
    SELECT DISTINCT ON (fixture_id)
        fixture_id,
        captured_at,
        odds_b365_home,
        odds_b365_draw,
        odds_b365_away,
        market_probability_home,
        market_probability_draw,
        market_probability_away,
        market_overround
    FROM odds_snapshots
    ORDER BY fixture_id, captured_at DESC
)
SELECT
    f.fixture_id,
    f.season,
    f.matchday,
    f.reference_date,
    f.scheduled_date,
    f.kickoff_time,
    f.home_team_id,
    f.home_team,
    f.away_team_id,
    f.away_team,
    f.home_team || ' vs ' || f.away_team AS match_label,
    f.status,
    (f.status = 'played') AS is_played,
    r.played_date,
    r.home_goals,
    r.away_goals,
    r.result AS actual_result,
    CASE r.result
        WHEN 'H' THEN 'Victoria local'
        WHEN 'D' THEN 'Empate'
        WHEN 'A' THEN 'Victoria visitante'
    END AS actual_result_label,
    p.model,
    p.probability_home,
    p.probability_draw,
    p.probability_away,
    p.predicted_ftr,
    CASE p.predicted_ftr
        WHEN 'H' THEN 'Victoria local'
        WHEN 'D' THEN 'Empate'
        WHEN 'A' THEN 'Victoria visitante'
    END AS predicted_result_label,
    p.probability_edge,
    p.confidence,
    p.expected_home_goals,
    p.expected_away_goals,
    p.predicted_score,
    p.predicted_score_probability,
    p.market_odds_available,
    p.promoted_adjustment_applied,
    p.feature_snapshot,
    p.update_id,
    o.captured_at AS odds_captured_at,
    o.odds_b365_home,
    o.odds_b365_draw,
    o.odds_b365_away,
    o.market_probability_home,
    o.market_probability_draw,
    o.market_probability_away,
    o.market_overround,
    CASE
        WHEN r.result IS NULL THEN NULL
        ELSE (r.result = p.predicted_ftr)
    END AS prediction_correct,
    CASE
        WHEN r.result IS NULL THEN NULL
        WHEN r.result = 'H' THEN p.probability_home
        WHEN r.result = 'D' THEN p.probability_draw
        WHEN r.result = 'A' THEN p.probability_away
    END AS probability_assigned_to_actual
FROM fixtures AS f
LEFT JOIN match_results AS r USING (fixture_id)
LEFT JOIN predictions AS p USING (fixture_id)
LEFT JOIN latest_odds AS o USING (fixture_id);

CREATE OR REPLACE VIEW bi_fact_team_matches AS
SELECT
    m.fixture_id,
    m.season,
    m.matchday,
    m.reference_date,
    m.scheduled_date,
    m.home_team_id AS team_id,
    m.home_team AS team,
    m.away_team_id AS opponent_id,
    m.away_team AS opponent,
    'Local' AS venue,
    m.status,
    m.is_played,
    m.home_goals AS goals_for,
    m.away_goals AS goals_against,
    CASE m.actual_result WHEN 'H' THEN 'W' WHEN 'D' THEN 'D' WHEN 'A' THEN 'L' END AS team_result,
    m.probability_home AS win_probability,
    m.probability_draw AS draw_probability,
    m.probability_away AS loss_probability,
    m.expected_home_goals AS expected_goals_for,
    m.expected_away_goals AS expected_goals_against,
    m.update_id
FROM bi_fact_matches AS m
UNION ALL
SELECT
    m.fixture_id,
    m.season,
    m.matchday,
    m.reference_date,
    m.scheduled_date,
    m.away_team_id,
    m.away_team,
    m.home_team_id,
    m.home_team,
    'Visitante',
    m.status,
    m.is_played,
    m.away_goals,
    m.home_goals,
    CASE m.actual_result WHEN 'A' THEN 'W' WHEN 'D' THEN 'D' WHEN 'H' THEN 'L' END,
    m.probability_away,
    m.probability_draw,
    m.probability_home,
    m.expected_away_goals,
    m.expected_home_goals,
    m.update_id
FROM bi_fact_matches AS m;

CREATE OR REPLACE VIEW bi_current_standings AS
SELECT
    team_id,
    team,
    played,
    wins,
    draws,
    losses,
    goals_for,
    goals_against,
    goal_difference,
    points,
    position,
    ppg,
    update_id
FROM standings;

CREATE OR REPLACE VIEW bi_simulation_summary AS
SELECT
    team_id,
    team,
    simulations,
    expected_points,
    median_points,
    points_p05,
    points_p95,
    expected_position,
    median_position,
    champion_probability,
    top4_probability,
    top6_probability,
    europe_top7_probability,
    relegation_probability,
    last_place_probability,
    update_id
FROM simulation_summary;

CREATE OR REPLACE VIEW bi_position_probabilities AS
SELECT
    team_id,
    position,
    probability,
    update_id
FROM position_probabilities;

CREATE OR REPLACE VIEW bi_update_status AS
SELECT
    update_id,
    created_at_utc,
    snapshot_date,
    completed_matches,
    completed_matchdays,
    remaining_matches,
    next_matchday,
    market_predictions,
    sports_predictions,
    simulations,
    seed,
    quality_passed,
    pipeline_mode
FROM update_runs;

COMMENT ON VIEW bi_fact_matches IS
    'Una fila por fixture con resultado, predicción vigente y última cuota.';
COMMENT ON VIEW bi_fact_team_matches IS
    'Dos filas por fixture, una desde la perspectiva de cada equipo.';
COMMENT ON VIEW bi_simulation_summary IS
    'Probabilidades Monte Carlo vigentes por equipo.';
