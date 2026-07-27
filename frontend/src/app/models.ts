export interface Health {
  status: string;
  database: string;
  season: string;
  latest_update_id: string | null;
  fixtures: number;
  predictions: number;
  completed_matches: number;
  simulations: number;
}

export interface Fixture {
  fixture_id: string;
  season: string;
  matchday: number;
  reference_date: string;
  scheduled_date: string | null;
  kickoff_time: string | null;
  home_team_id: string;
  home_team: string;
  away_team_id: string;
  away_team: string;
  status: string;
}

export interface Prediction {
  fixture_id: string;
  matchday: number;
  home_team: string;
  away_team: string;
  model: string;
  probability_home: number;
  probability_draw: number;
  probability_away: number;
  predicted_ftr: 'H' | 'D' | 'A';
  confidence: string;
  expected_home_goals: number;
  expected_away_goals: number;
  predicted_score: string;
  market_odds_available: boolean;
}

export interface Standing {
  team_id: string;
  team: string;
  played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
  position: number | null;
  ppg: number | null;
}

export interface Simulation {
  team_id: string;
  team: string;
  simulations: number;
  expected_points: number;
  points_p05: number;
  points_p95: number;
  expected_position: number;
  champion_probability: number;
  top4_probability: number;
  europe_top7_probability: number;
  relegation_probability: number;
}

export interface PipelineRun {
  run_id: string;
  started_at_utc: string;
  finished_at_utc: string | null;
  status:
    | 'running'
    | 'success'
    | 'no_changes'
    | 'source_unavailable'
    | 'failed';
  trigger: string;
  source: string;
  source_url: string | null;
  source_checksum: string | null;
  rows_downloaded: number;
  results_discovered: number;
  results_added: number;
  odds_discovered: number;
  odds_added: number;
  update_id: string | null;
  simulations: number;
  model_version: string;
  duration_seconds: number | null;
  error_type: string | null;
  error_message: string | null;
}

export interface AutomationStatus {
  enabled: boolean;
  interval_minutes: number;
  source: string;
  source_url: string;
  latest_run: PipelineRun | null;
}

export interface PerformanceSummary {
  season: string;
  prediction_snapshots: number;
  fixtures_with_snapshot: number;
  completed_matches: number;
  evaluated_matches: number;
  pending_evaluation: number;
  correct_predictions: number;
  accuracy: number | null;
  log_loss: number | null;
  brier_score: number | null;
  market_matches: number;
  market_accuracy: number | null;
  market_log_loss: number | null;
  market_brier_score: number | null;
  model_versions: string[];
  last_evaluated_at_utc: string | null;
}

export interface PerformanceHistory {
  fixture_id: string;
  snapshot_id: string;
  season: string;
  matchday: number;
  played_date: string;
  home_team: string;
  away_team: string;
  home_goals: number;
  away_goals: number;
  actual_ftr: 'H' | 'D' | 'A';
  predicted_ftr: 'H' | 'D' | 'A';
  probability_home: number;
  probability_draw: number;
  probability_away: number;
  correct: boolean;
  log_loss: number;
  brier_score: number;
  market_predicted_ftr: 'H' | 'D' | 'A' | null;
  market_log_loss: number | null;
  market_brier_score: number | null;
  model_version: string;
  prediction_captured_at_utc: string;
  evaluated_at_utc: string;
}

export interface MatchdayPerformance {
  matchday: number;
  matches: number;
  correct: number;
  accuracy: number;
  log_loss: number;
  brier_score: number;
  market_log_loss: number | null;
}

export interface ConfusionCell {
  actual_ftr: 'H' | 'D' | 'A';
  predicted_ftr: 'H' | 'D' | 'A';
  matches: number;
}

export interface CalibrationBin {
  bin_lower: number;
  bin_upper: number;
  label: string;
  matches: number;
  mean_confidence: number | null;
  observed_accuracy: number | null;
}

export interface ModelTrainingRun {
  run_id: string;
  trigger: string;
  status: 'running' | 'not_ready' | 'candidate_ready' | 'rejected' | 'failed';
  started_at_utc: string;
  finished_at_utc: string | null;
  champion_version: string;
  candidate_version: string | null;
  evaluated_matches: number;
  completed_matchdays: number;
  minimum_matches: number;
  minimum_matchdays: number;
  train_matches: number;
  validation_matches: number;
  champion_log_loss: number | null;
  candidate_log_loss: number | null;
  log_loss_improvement: number | null;
  champion_brier_score: number | null;
  candidate_brier_score: number | null;
  selected_temperature: number | null;
  eligible_for_promotion: boolean;
  duration_seconds: number | null;
  error_message: string | null;
}

export interface ModelStatus {
  active_model: string;
  active_trained_through: string;
  evaluated_matches: number;
  completed_matchdays: number;
  minimum_matches: number;
  minimum_matchdays: number;
  ready_to_retrain: boolean;
  latest_training_run: ModelTrainingRun | null;
}

export interface ModelVersion {
  version: string;
  family: string;
  stage: 'active' | 'candidate' | 'rejected' | 'archived';
  created_at_utc: string;
  activated_at_utc: string | null;
  trained_through: string;
  training_matches: number;
  validation_matches: number;
  transformation: string;
  artifact_checksum: string;
  validation_log_loss: number | null;
  validation_brier_score: number | null;
  validation_accuracy: number | null;
  validation_macro_f1: number | null;
  eligible_for_promotion: boolean;
  parent_version: string | null;
  training_run_id: string | null;
  notes: string | null;
}
