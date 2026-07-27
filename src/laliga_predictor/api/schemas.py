from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FixtureOut(APIModel):
    fixture_id: str
    season: str
    matchday: int
    reference_date: date
    scheduled_date: datetime | None
    kickoff_time: str | None
    home_team_id: str
    home_team: str
    away_team_id: str
    away_team: str
    status: str


class PredictionOut(APIModel):
    fixture_id: str
    matchday: int
    home_team: str
    away_team: str
    model: str
    probability_home: float
    probability_draw: float
    probability_away: float
    predicted_ftr: str
    confidence: str
    expected_home_goals: float
    expected_away_goals: float
    predicted_score: str
    market_odds_available: bool


class StandingOut(APIModel):
    team_id: str
    team: str
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    position: int | None
    ppg: float | None


class SimulationOut(APIModel):
    team_id: str
    team: str
    simulations: int
    expected_points: float
    points_p05: float
    points_p95: float
    expected_position: float
    champion_probability: float
    top4_probability: float
    europe_top7_probability: float
    relegation_probability: float


class ResultInput(APIModel):
    fixture_id: str
    date: date
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    home_shots: float | None = Field(default=None, ge=0)
    away_shots: float | None = Field(default=None, ge=0)
    home_shots_on_target: float | None = Field(default=None, ge=0)
    away_shots_on_target: float | None = Field(default=None, ge=0)
    home_corners: float | None = Field(default=None, ge=0)
    away_corners: float | None = Field(default=None, ge=0)
    home_yellow_cards: float | None = Field(default=None, ge=0)
    away_yellow_cards: float | None = Field(default=None, ge=0)
    home_red_cards: float | None = Field(default=None, ge=0)
    away_red_cards: float | None = Field(default=None, ge=0)


class OddsInput(APIModel):
    fixture_id: str
    captured_at: datetime
    odds_b365_home: float = Field(gt=1)
    odds_b365_draw: float = Field(gt=1)
    odds_b365_away: float = Field(gt=1)


class MatchdayUpdateInput(APIModel):
    results: list[ResultInput] = Field(default_factory=list)
    odds: list[OddsInput] = Field(default_factory=list)
    simulations: int = Field(default=50_000, ge=100, le=100_000)
    seed: int = 42
    allow_partial: bool = False

    @model_validator(mode="after")
    def require_data(self) -> "MatchdayUpdateInput":
        if not self.results and not self.odds:
            raise ValueError("At least one result or odds snapshot is required.")
        return self


class UpdateRunOut(APIModel):
    update_id: str
    created_at_utc: datetime
    snapshot_date: date
    completed_matches: int
    completed_matchdays: int
    remaining_matches: int
    next_matchday: int | None
    market_predictions: int
    sports_predictions: int
    simulations: int
    seed: int
    quality_passed: bool
    pipeline_mode: str
    snapshot_path: str | None


class HealthOut(APIModel):
    status: str
    database: str
    season: str
    latest_update_id: str | None
    fixtures: int
    predictions: int
    completed_matches: int
    simulations: int


class PipelineStepOut(APIModel):
    step_order: int
    name: str
    status: str
    started_at_utc: datetime
    finished_at_utc: datetime
    duration_seconds: float
    rows_processed: int | None
    detail: str | None


class PipelineRunOut(APIModel):
    run_id: str
    started_at_utc: datetime
    finished_at_utc: datetime | None
    status: str
    trigger: str
    source: str
    source_url: str | None
    source_checksum: str | None
    rows_downloaded: int
    results_discovered: int
    results_added: int
    odds_discovered: int
    odds_added: int
    update_id: str | None
    simulations: int
    model_version: str
    duration_seconds: float | None
    error_type: str | None
    error_message: str | None


class AutomationStatusOut(APIModel):
    enabled: bool
    interval_minutes: int
    source: str
    source_url: str
    latest_run: PipelineRunOut | None


class PerformanceSummaryOut(APIModel):
    season: str
    prediction_snapshots: int
    fixtures_with_snapshot: int
    completed_matches: int
    evaluated_matches: int
    pending_evaluation: int
    correct_predictions: int
    accuracy: float | None
    log_loss: float | None
    brier_score: float | None
    market_matches: int
    market_accuracy: float | None
    market_log_loss: float | None
    market_brier_score: float | None
    model_versions: list[str]
    last_evaluated_at_utc: datetime | None


class PerformanceHistoryOut(APIModel):
    fixture_id: str
    snapshot_id: str
    season: str
    matchday: int
    played_date: date
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    actual_ftr: str
    predicted_ftr: str
    probability_home: float
    probability_draw: float
    probability_away: float
    correct: bool
    log_loss: float
    brier_score: float
    market_predicted_ftr: str | None
    market_log_loss: float | None
    market_brier_score: float | None
    model_version: str
    prediction_captured_at_utc: datetime
    evaluated_at_utc: datetime


class MatchdayPerformanceOut(APIModel):
    matchday: int
    matches: int
    correct: int
    accuracy: float
    log_loss: float
    brier_score: float
    market_log_loss: float | None


class ConfusionCellOut(APIModel):
    actual_ftr: str
    predicted_ftr: str
    matches: int


class CalibrationBinOut(APIModel):
    bin_lower: float
    bin_upper: float
    label: str
    matches: int
    mean_confidence: float | None
    observed_accuracy: float | None


class ModelVersionOut(APIModel):
    version: str
    family: str
    stage: str
    created_at_utc: datetime
    activated_at_utc: datetime | None
    trained_through: str
    training_matches: int
    validation_matches: int
    transformation: str
    artifact_checksum: str
    validation_log_loss: float | None
    validation_brier_score: float | None
    validation_accuracy: float | None
    validation_macro_f1: float | None
    eligible_for_promotion: bool
    parent_version: str | None
    training_run_id: str | None
    notes: str | None


class ModelTrainingRunOut(APIModel):
    run_id: str
    trigger: str
    status: str
    started_at_utc: datetime
    finished_at_utc: datetime | None
    champion_version: str
    candidate_version: str | None
    evaluated_matches: int
    completed_matchdays: int
    minimum_matches: int
    minimum_matchdays: int
    train_matches: int
    validation_matches: int
    champion_log_loss: float | None
    candidate_log_loss: float | None
    log_loss_improvement: float | None
    champion_brier_score: float | None
    candidate_brier_score: float | None
    selected_temperature: float | None
    eligible_for_promotion: bool
    duration_seconds: float | None
    error_message: str | None


class ModelStatusOut(APIModel):
    active_model: str
    active_trained_through: str
    evaluated_matches: int
    completed_matchdays: int
    minimum_matches: int
    minimum_matchdays: int
    ready_to_retrain: bool
    latest_training_run: ModelTrainingRunOut | None


class PromoteModelInput(APIModel):
    confirm: bool


class PromotionOut(APIModel):
    active_model: str
    previous_model: str
    applied_from_next_pipeline_run: bool = True
