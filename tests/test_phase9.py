from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.dynamic import (  # noqa: E402
    ODDS_COLUMNS,
    RESULT_COLUMNS,
    _normalize_odds,
    _normalize_results,
    _update_id,
    _validate_matchday_completeness,
    run_phase9,
)


@pytest.fixture(scope="module")
def fixtures() -> pd.DataFrame:
    return pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "fixtures_2026_27.csv"
    )


@pytest.fixture(scope="module")
def phase9_summary() -> dict:
    return run_phase9(simulations=2_000)


def test_preseason_noop_outputs(phase9_summary: dict) -> None:
    assert phase9_summary["quality_passed"] is True
    assert phase9_summary["pipeline_mode"] == "preseason_noop"
    assert phase9_summary["completed_matches"] == 0
    assert phase9_summary["remaining_matches"] == 380
    assert phase9_summary["next_matchday"] == 1


def test_dynamic_probabilities_are_valid(phase9_summary: dict) -> None:
    predictions = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "current_predictions_2026_27.csv"
    )
    probabilities = predictions[
        ["probability_home", "probability_draw", "probability_away"]
    ]
    assert len(predictions) == 380
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert probabilities.ge(0).all().all()
    assert probabilities.le(1).all().all()


def test_empty_templates_have_required_schema() -> None:
    results = pd.read_csv(
        PROJECT_ROOT / "data" / "incoming" / "results_2026_27.csv"
    )
    odds = pd.read_csv(
        PROJECT_ROOT / "data" / "incoming" / "odds_2026_27.csv"
    )
    assert results.columns.tolist() == RESULT_COLUMNS
    assert odds.columns.tolist() == ODDS_COLUMNS
    assert results.empty and odds.empty


def test_unknown_fixture_is_rejected(fixtures: pd.DataFrame) -> None:
    row = {column: np.nan for column in RESULT_COLUMNS}
    row.update(
        {
            "fixture_id": "laliga_unknown",
            "date": "2026-08-16",
            "home_goals": 1,
            "away_goals": 0,
        }
    )
    with pytest.raises(ValueError, match="Unknown fixture_id"):
        _normalize_results(pd.DataFrame([row]), fixtures)


def test_duplicate_result_is_rejected(fixtures: pd.DataFrame) -> None:
    fixture_id = fixtures.iloc[0]["fixture_id"]
    row = {column: np.nan for column in RESULT_COLUMNS}
    row.update(
        {
            "fixture_id": fixture_id,
            "date": "2026-08-16",
            "home_goals": 1,
            "away_goals": 0,
        }
    )
    with pytest.raises(ValueError, match="Duplicated"):
        _normalize_results(pd.DataFrame([row, row]), fixtures)


def test_partial_matchday_requires_explicit_override(
    fixtures: pd.DataFrame,
) -> None:
    fixture_id = fixtures.iloc[0]["fixture_id"]
    row = {column: np.nan for column in RESULT_COLUMNS}
    row.update(
        {
            "fixture_id": fixture_id,
            "date": "2026-08-16",
            "home_goals": 0,
            "away_goals": 0,
        }
    )
    result = _normalize_results(pd.DataFrame([row]), fixtures)
    with pytest.raises(ValueError, match="all 10 results"):
        _validate_matchday_completeness(result, allow_partial=False)
    _validate_matchday_completeness(result, allow_partial=True)


def test_latest_odds_snapshot_is_selected(fixtures: pd.DataFrame) -> None:
    fixture_id = fixtures.iloc[0]["fixture_id"]
    rows = [
        {
            "fixture_id": fixture_id,
            "captured_at": "2026-08-14T12:00:00Z",
            "odds_b365_home": 2.0,
            "odds_b365_draw": 3.0,
            "odds_b365_away": 4.0,
        },
        {
            "fixture_id": fixture_id,
            "captured_at": "2026-08-15T12:00:00Z",
            "odds_b365_home": 1.9,
            "odds_b365_draw": 3.2,
            "odds_b365_away": 4.2,
        },
    ]
    normalized = _normalize_odds(pd.DataFrame(rows), fixtures)
    assert len(normalized) == 1
    assert normalized.iloc[0]["odds_b365_home"] == 1.9
    assert np.isclose(
        normalized.iloc[0][
            [
                "market_probability_home",
                "market_probability_draw",
                "market_probability_away",
            ]
        ].astype(float).sum(),
        1.0,
    )


def test_update_id_is_idempotent() -> None:
    results = pd.DataFrame(columns=RESULT_COLUMNS)
    odds = pd.DataFrame(columns=ODDS_COLUMNS)
    assert _update_id(results, odds) == _update_id(results.copy(), odds.copy())


def test_simulation_zones_reconcile(phase9_summary: dict) -> None:
    summary = pd.read_csv(
        PROJECT_ROOT
        / "reports"
        / "dynamic_season_simulation_summary.csv"
    )
    assert np.isclose(summary["champion_probability"].sum(), 1.0)
    assert np.isclose(summary["top4_probability"].sum(), 4.0)
    assert np.isclose(summary["europe_top7_probability"].sum(), 7.0)
    assert np.isclose(summary["relegation_probability"].sum(), 3.0)


def test_full_dynamic_update_switches_per_fixture_to_market() -> None:
    summary = run_phase9(
        results_path=(
            PROJECT_ROOT
            / "tests"
            / "fixtures"
            / "phase9_synthetic_matchday1_results.csv"
        ),
        odds_path=(
            PROJECT_ROOT
            / "tests"
            / "fixtures"
            / "phase9_synthetic_matchday2_odds.csv"
        ),
        simulations=300,
    )
    predictions = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "current_predictions_2026_27.csv"
    )
    assert summary["pipeline_mode"] == "dynamic_update"
    assert summary["completed_matches"] == 10
    assert summary["remaining_matches"] == 370
    assert summary["next_matchday"] == 2
    assert summary["market_predictions"] == 1
    assert predictions["fixture_id"].eq("laliga_102259").any()
    assert predictions.loc[
        predictions["fixture_id"].eq("laliga_102259"), "model"
    ].eq("ensemble_market").all()
