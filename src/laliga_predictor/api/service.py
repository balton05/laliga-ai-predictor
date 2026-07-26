from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from laliga_predictor.dynamic import (
    ODDS_COLUMNS,
    RESULT_COLUMNS,
    run_phase9,
)

from .models import (
    Fixture,
    MatchResult,
    OddsSnapshot,
    PositionProbability,
    Prediction,
    SimulationSummary,
    Standing,
    UpdateRun,
)
from .schemas import MatchdayUpdateInput


class UpdateConflictError(ValueError):
    """Raised when an existing confirmed value would be overwritten."""


def _clean(value: Any) -> Any:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def _records(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    return [
        {column: _clean(row.get(column)) for column in columns}
        for row in frame.to_dict(orient="records")
    ]


def _read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig", **kwargs)


class DataSyncService:
    """Synchronize Phase 9 outputs and orchestrate safe season updates."""

    def __init__(
        self,
        project_root: Path,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.project_root = Path(project_root)
        self.session_factory = session_factory
        self._update_lock = threading.Lock()

    @property
    def processed(self) -> Path:
        return self.project_root / "data" / "processed"

    @property
    def incoming(self) -> Path:
        return self.project_root / "data" / "incoming"

    @property
    def reports(self) -> Path:
        return self.project_root / "reports"

    def sync_current_state(self, summary: dict | None = None) -> dict:
        if summary is None:
            summary = json.loads(
                (self.reports / "phase9_summary.json").read_text(
                    encoding="utf-8"
                )
            )
        update_id = str(summary["update_id"])

        fixtures = _read_csv(
            self.processed / "fixtures_2026_27.csv",
            parse_dates=["reference_date", "scheduled_date"],
        )
        results = _read_csv(
            self.processed / "current_results_2026_27.csv",
            parse_dates=["date"],
        )
        predictions = _read_csv(
            self.processed / "current_predictions_2026_27.csv"
        )
        standings = _read_csv(self.reports / "current_table_2026_27.csv")
        simulations = _read_csv(
            self.reports / "dynamic_season_simulation_summary.csv"
        )
        positions = _read_csv(
            self.reports / "dynamic_position_distribution.csv"
        )
        odds = self._odds_records(fixtures)

        completed_ids = set(results.get("fixture_id", pd.Series(dtype=str)))
        fixtures = fixtures.copy()
        fixtures["status"] = np.where(
            fixtures["fixture_id"].isin(completed_ids),
            "played",
            fixtures["status"].fillna("scheduled"),
        )

        fixture_columns = [
            "fixture_id",
            "season",
            "matchday",
            "reference_date",
            "scheduled_date",
            "kickoff_time",
            "home_team_id",
            "home_team",
            "home_team_official",
            "away_team_id",
            "away_team",
            "away_team_official",
            "status",
        ]
        result_columns = [
            "fixture_id",
            "played_date",
            "home_goals",
            "away_goals",
            "result",
            *RESULT_COLUMNS[4:],
        ]
        if not results.empty:
            results = results.rename(columns={"date": "played_date"})
        prediction_columns = [
            "fixture_id",
            "model",
            "probability_home",
            "probability_draw",
            "probability_away",
            "predicted_ftr",
            "probability_edge",
            "confidence",
            "expected_home_goals",
            "expected_away_goals",
            "predicted_score",
            "predicted_score_probability",
            "market_odds_available",
            "promoted_adjustment_applied",
            "feature_snapshot",
            "update_id",
        ]
        predictions = predictions.copy()
        predictions["update_id"] = update_id
        predictions["market_odds_available"] = predictions[
            "market_odds_available"
        ].map(lambda value: str(value).lower() == "true")
        predictions["promoted_adjustment_applied"] = predictions[
            "promoted_adjustment_applied"
        ].map(lambda value: str(value).lower() in {"1", "true"})

        standing_columns = [
            "team_id",
            "team",
            "played",
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
            "goal_difference",
            "points",
            "position",
            "ppg",
            "update_id",
        ]
        standings = standings.copy()
        standings["update_id"] = update_id

        simulation_columns = [
            "team_id",
            "team",
            "simulations",
            "expected_points",
            "median_points",
            "points_p05",
            "points_p95",
            "expected_position",
            "median_position",
            "champion_probability",
            "top4_probability",
            "top6_probability",
            "europe_top7_probability",
            "relegation_probability",
            "last_place_probability",
            "update_id",
        ]
        simulations = simulations.copy()
        simulations["update_id"] = update_id

        position_columns = [
            "team_id",
            "position",
            "probability",
            "update_id",
        ]
        positions = positions.copy()
        positions["update_id"] = update_id

        with self.session_factory.begin() as session:
            for model in [
                PositionProbability,
                SimulationSummary,
                Standing,
                Prediction,
                OddsSnapshot,
                MatchResult,
                Fixture,
            ]:
                session.execute(delete(model))

            session.bulk_insert_mappings(
                Fixture, _records(fixtures, fixture_columns)
            )
            if not results.empty:
                session.bulk_insert_mappings(
                    MatchResult, _records(results, result_columns)
                )
            if odds:
                session.bulk_insert_mappings(OddsSnapshot, odds)
            session.bulk_insert_mappings(
                Prediction, _records(predictions, prediction_columns)
            )
            session.bulk_insert_mappings(
                Standing, _records(standings, standing_columns)
            )
            session.bulk_insert_mappings(
                SimulationSummary,
                _records(simulations, simulation_columns),
            )
            session.bulk_insert_mappings(
                PositionProbability, _records(positions, position_columns)
            )
            session.merge(
                UpdateRun(
                    update_id=update_id,
                    created_at_utc=datetime.fromisoformat(
                        summary["created_at_utc"]
                    ),
                    snapshot_date=pd.Timestamp(
                        summary["snapshot_date"]
                    ).date(),
                    completed_matches=int(summary["completed_matches"]),
                    completed_matchdays=int(summary["completed_matchdays"]),
                    remaining_matches=int(summary["remaining_matches"]),
                    next_matchday=summary.get("next_matchday"),
                    market_predictions=int(summary["market_predictions"]),
                    sports_predictions=int(summary["sports_predictions"]),
                    simulations=int(summary["simulations"]),
                    seed=int(summary.get("seed", 42)),
                    quality_passed=bool(summary["quality_passed"]),
                    pipeline_mode=str(summary["pipeline_mode"]),
                    snapshot_path=summary.get("snapshot_path"),
                )
            )
        return summary

    def _odds_records(self, fixtures: pd.DataFrame) -> list[dict]:
        raw = _read_csv(
            self.incoming / "odds_2026_27.csv",
            parse_dates=["captured_at"],
        )
        if raw.empty:
            return []
        known = set(fixtures["fixture_id"])
        raw = raw[raw["fixture_id"].isin(known)].copy()
        raw = raw.drop_duplicates(
            ["fixture_id", "captured_at"], keep="last"
        )
        odds_columns = [
            "odds_b365_home",
            "odds_b365_draw",
            "odds_b365_away",
        ]
        inverse = 1.0 / raw[odds_columns].astype(float)
        overround = inverse.sum(axis=1)
        normalized = inverse.div(overround, axis=0)
        raw["market_probability_home"] = normalized["odds_b365_home"]
        raw["market_probability_draw"] = normalized["odds_b365_draw"]
        raw["market_probability_away"] = normalized["odds_b365_away"]
        raw["market_overround"] = overround
        columns = [
            "fixture_id",
            "captured_at",
            *odds_columns,
            "market_probability_home",
            "market_probability_draw",
            "market_probability_away",
            "market_overround",
        ]
        return _records(raw, columns)

    def apply_update(self, payload: MatchdayUpdateInput) -> dict:
        if not self._update_lock.acquire(blocking=False):
            raise UpdateConflictError(
                "Another matchday update is already running."
            )
        try:
            combined_results = self._combine_results(payload)
            combined_odds = self._combine_odds(payload)
            with TemporaryDirectory(prefix="laliga_phase10_") as temporary:
                temporary_path = Path(temporary)
                results_path = temporary_path / "results.csv"
                odds_path = temporary_path / "odds.csv"
                combined_results.to_csv(
                    results_path,
                    index=False,
                    columns=RESULT_COLUMNS,
                    encoding="utf-8-sig",
                )
                combined_odds.to_csv(
                    odds_path,
                    index=False,
                    columns=ODDS_COLUMNS,
                    encoding="utf-8-sig",
                )
                summary = run_phase9(
                    results_path=results_path,
                    odds_path=odds_path,
                    simulations=payload.simulations,
                    seed=payload.seed,
                    allow_partial=payload.allow_partial,
                )
            self.incoming.mkdir(parents=True, exist_ok=True)
            combined_results.to_csv(
                self.incoming / "results_2026_27.csv",
                index=False,
                columns=RESULT_COLUMNS,
                encoding="utf-8-sig",
            )
            combined_odds.to_csv(
                self.incoming / "odds_2026_27.csv",
                index=False,
                columns=ODDS_COLUMNS,
                encoding="utf-8-sig",
            )
            return self.sync_current_state(summary)
        finally:
            self._update_lock.release()

    def _combine_results(
        self, payload: MatchdayUpdateInput
    ) -> pd.DataFrame:
        existing = _read_csv(self.incoming / "results_2026_27.csv")
        if existing.empty:
            existing = pd.DataFrame(columns=RESULT_COLUMNS)
        incoming = pd.DataFrame(
            [
                item.model_dump(mode="json")
                for item in payload.results
            ],
            columns=RESULT_COLUMNS,
        )
        if incoming.empty:
            return existing[RESULT_COLUMNS].copy()
        if incoming["fixture_id"].duplicated().any():
            raise UpdateConflictError(
                "The request contains duplicated result fixture_id values."
            )
        existing_by_id = existing.set_index("fixture_id", drop=False)
        for row in incoming.to_dict(orient="records"):
            fixture_id = row["fixture_id"]
            if fixture_id not in existing_by_id.index:
                continue
            previous = existing_by_id.loc[fixture_id].to_dict()
            comparable = ["date", "home_goals", "away_goals"]
            if any(
                str(_clean(previous.get(column)))
                != str(_clean(row.get(column)))
                for column in comparable
            ):
                raise UpdateConflictError(
                    f"Result {fixture_id} is already confirmed with "
                    "different values."
                )
        combined = (
            incoming.copy()
            if existing.empty
            else pd.concat([existing, incoming], ignore_index=True)
        )
        return combined.drop_duplicates("fixture_id", keep="first")[
            RESULT_COLUMNS
        ]

    def _combine_odds(self, payload: MatchdayUpdateInput) -> pd.DataFrame:
        existing = _read_csv(self.incoming / "odds_2026_27.csv")
        if existing.empty:
            existing = pd.DataFrame(columns=ODDS_COLUMNS)
        incoming = pd.DataFrame(
            [item.model_dump(mode="json") for item in payload.odds],
            columns=ODDS_COLUMNS,
        )
        if incoming.empty:
            return existing[ODDS_COLUMNS].copy()
        combined = (
            incoming.copy()
            if existing.empty
            else pd.concat([existing, incoming], ignore_index=True)
        )
        duplicate_key = ["fixture_id", "captured_at"]
        conflicts = combined.duplicated(duplicate_key, keep=False)
        if conflicts.any():
            grouped = combined.loc[conflicts].groupby(duplicate_key)
            for key, group in grouped:
                values = group[ODDS_COLUMNS[2:]].drop_duplicates()
                if len(values) > 1:
                    raise UpdateConflictError(
                        "Different odds already exist for fixture/capture "
                        f"{key}."
                    )
        return combined.drop_duplicates(duplicate_key, keep="first")[
            ODDS_COLUMNS
        ]
