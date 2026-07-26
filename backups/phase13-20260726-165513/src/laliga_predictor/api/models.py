from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Fixture(Base):
    __tablename__ = "fixtures"

    fixture_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    matchday: Mapped[int] = mapped_column(Integer, index=True)
    reference_date: Mapped[date] = mapped_column(Date)
    scheduled_date: Mapped[datetime | None] = mapped_column(DateTime)
    kickoff_time: Mapped[str | None] = mapped_column(String(16))
    home_team_id: Mapped[str] = mapped_column(String(64), index=True)
    home_team: Mapped[str] = mapped_column(String(128))
    home_team_official: Mapped[str] = mapped_column(String(128))
    away_team_id: Mapped[str] = mapped_column(String(64), index=True)
    away_team: Mapped[str] = mapped_column(String(128))
    away_team_official: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), index=True)

    __table_args__ = (
        Index("ix_fixtures_matchday_fixture", "matchday", "fixture_id"),
    )


class MatchResult(Base):
    __tablename__ = "match_results"

    fixture_id: Mapped[str] = mapped_column(
        ForeignKey("fixtures.fixture_id", ondelete="CASCADE"),
        primary_key=True,
    )
    played_date: Mapped[date] = mapped_column(Date, index=True)
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(1))
    home_shots: Mapped[float | None] = mapped_column(Float)
    away_shots: Mapped[float | None] = mapped_column(Float)
    home_shots_on_target: Mapped[float | None] = mapped_column(Float)
    away_shots_on_target: Mapped[float | None] = mapped_column(Float)
    home_corners: Mapped[float | None] = mapped_column(Float)
    away_corners: Mapped[float | None] = mapped_column(Float)
    home_yellow_cards: Mapped[float | None] = mapped_column(Float)
    away_yellow_cards: Mapped[float | None] = mapped_column(Float)
    home_red_cards: Mapped[float | None] = mapped_column(Float)
    away_red_cards: Mapped[float | None] = mapped_column(Float)


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fixture_id: Mapped[str] = mapped_column(
        ForeignKey("fixtures.fixture_id", ondelete="CASCADE"), index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    odds_b365_home: Mapped[float] = mapped_column(Float)
    odds_b365_draw: Mapped[float] = mapped_column(Float)
    odds_b365_away: Mapped[float] = mapped_column(Float)
    market_probability_home: Mapped[float] = mapped_column(Float)
    market_probability_draw: Mapped[float] = mapped_column(Float)
    market_probability_away: Mapped[float] = mapped_column(Float)
    market_overround: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint(
            "fixture_id", "captured_at", name="uq_odds_fixture_capture"
        ),
    )


class Prediction(Base):
    __tablename__ = "predictions"

    fixture_id: Mapped[str] = mapped_column(
        ForeignKey("fixtures.fixture_id", ondelete="CASCADE"),
        primary_key=True,
    )
    model: Mapped[str] = mapped_column(String(32), index=True)
    probability_home: Mapped[float] = mapped_column(Float)
    probability_draw: Mapped[float] = mapped_column(Float)
    probability_away: Mapped[float] = mapped_column(Float)
    predicted_ftr: Mapped[str] = mapped_column(String(1))
    probability_edge: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(16))
    expected_home_goals: Mapped[float] = mapped_column(Float)
    expected_away_goals: Mapped[float] = mapped_column(Float)
    predicted_score: Mapped[str] = mapped_column(String(16))
    predicted_score_probability: Mapped[float] = mapped_column(Float)
    market_odds_available: Mapped[bool] = mapped_column(Boolean)
    promoted_adjustment_applied: Mapped[bool] = mapped_column(Boolean)
    feature_snapshot: Mapped[str] = mapped_column(String(32))
    update_id: Mapped[str] = mapped_column(String(32), index=True)


class Standing(Base):
    __tablename__ = "standings"

    team_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team: Mapped[str] = mapped_column(String(128), unique=True)
    played: Mapped[int] = mapped_column(Integer)
    wins: Mapped[int] = mapped_column(Integer)
    draws: Mapped[int] = mapped_column(Integer)
    losses: Mapped[int] = mapped_column(Integer)
    goals_for: Mapped[int] = mapped_column(Integer)
    goals_against: Mapped[int] = mapped_column(Integer)
    goal_difference: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)
    position: Mapped[int | None] = mapped_column(Integer)
    ppg: Mapped[float | None] = mapped_column(Float)
    update_id: Mapped[str] = mapped_column(String(32), index=True)


class SimulationSummary(Base):
    __tablename__ = "simulation_summary"

    team_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team: Mapped[str] = mapped_column(String(128), unique=True)
    simulations: Mapped[int] = mapped_column(Integer)
    expected_points: Mapped[float] = mapped_column(Float)
    median_points: Mapped[float] = mapped_column(Float)
    points_p05: Mapped[float] = mapped_column(Float)
    points_p95: Mapped[float] = mapped_column(Float)
    expected_position: Mapped[float] = mapped_column(Float)
    median_position: Mapped[float] = mapped_column(Float)
    champion_probability: Mapped[float] = mapped_column(Float)
    top4_probability: Mapped[float] = mapped_column(Float)
    top6_probability: Mapped[float] = mapped_column(Float)
    europe_top7_probability: Mapped[float] = mapped_column(Float)
    relegation_probability: Mapped[float] = mapped_column(Float)
    last_place_probability: Mapped[float] = mapped_column(Float)
    update_id: Mapped[str] = mapped_column(String(32), index=True)


class PositionProbability(Base):
    __tablename__ = "position_probabilities"

    team_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_summary.team_id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    probability: Mapped[float] = mapped_column(Float)
    update_id: Mapped[str] = mapped_column(String(32), index=True)


class UpdateRun(Base):
    __tablename__ = "update_runs"

    update_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot_date: Mapped[date] = mapped_column(Date)
    completed_matches: Mapped[int] = mapped_column(Integer)
    completed_matchdays: Mapped[int] = mapped_column(Integer)
    remaining_matches: Mapped[int] = mapped_column(Integer)
    next_matchday: Mapped[int | None] = mapped_column(Integer)
    market_predictions: Mapped[int] = mapped_column(Integer)
    sports_predictions: Mapped[int] = mapped_column(Integer)
    simulations: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(Integer)
    quality_passed: Mapped[bool] = mapped_column(Boolean)
    pipeline_mode: Mapped[str] = mapped_column(String(32))
    snapshot_path: Mapped[str | None] = mapped_column(String(512))
