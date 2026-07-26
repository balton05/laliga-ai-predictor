from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.goal_modeling import run_phase5  # noqa: E402


@pytest.fixture(scope="module")
def phase5_summary() -> dict:
    return run_phase5()


def test_phase5_outputs(phase5_summary: dict) -> None:
    assert phase5_summary["quality_passed"] is True
    assert phase5_summary["quality_checks"] == 14
    assert phase5_summary["goal_models_evaluated"] == 2
    assert phase5_summary["candidate_configurations"] == 8
    assert phase5_summary["validation_rows_per_model"] == 760
    assert phase5_summary["test_rows_per_model"] == 380
    assert phase5_summary["promoted_adjustments"] == 3
    assert phase5_summary["fixture_predictions_2026_27"] == 380


def test_goal_probabilities_are_valid(phase5_summary: dict) -> None:
    validation = pd.read_csv(
        PROJECT_ROOT / "reports" / "goal_model_predictions_validation.csv"
    )
    test = pd.read_csv(
        PROJECT_ROOT / "reports" / "goal_model_predictions_test.csv"
    )
    predictions = pd.concat([validation, test], ignore_index=True)
    columns = ["probability_home", "probability_draw", "probability_away"]
    values = predictions[columns].to_numpy(dtype=float)
    assert np.isfinite(values).all()
    assert np.allclose(values.sum(axis=1), 1.0)
    assert ((values >= 0.0) & (values <= 1.0)).all()
    assert predictions[
        ["expected_home_goals", "expected_away_goals"]
    ].gt(0).all().all()


def test_test_season_is_not_used_for_selection(phase5_summary: dict) -> None:
    selection = json.loads(
        (PROJECT_ROOT / "reports" / "goal_model_selection.json").read_text(
            encoding="utf-8"
        )
    )
    assert selection["test_protocol"]["evaluate_once"] == "2025/26"
    assert all(
        fold["evaluate"] != "2025/26"
        for fold in selection["validation_protocol"]
    )


def test_2026_27_fixture_predictions_are_complete(phase5_summary: dict) -> None:
    fixtures = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "fixtures_2026_27_goal_predictions.csv"
    )
    columns = ["probability_home", "probability_draw", "probability_away"]
    assert len(fixtures) == 380
    assert fixtures["fixture_id"].is_unique
    assert fixtures.groupby("matchday").size().eq(10).all()
    assert np.allclose(fixtures[columns].sum(axis=1), 1.0)
    assert fixtures["requires_dynamic_update"].all()


def test_promoted_adjustments_are_conservative(phase5_summary: dict) -> None:
    adjustments = pd.read_csv(
        PROJECT_ROOT / "reports" / "promoted_strength_adjustment.csv"
    )
    assert set(adjustments["team_id"]) == {
        "racing_santander",
        "deportivo",
        "malaga",
    }
    assert adjustments["confidence"].eq("low").all()
    assert adjustments["attack_effect"].between(-0.45, 0.45).all()
    assert adjustments["defense_effect"].between(-0.45, 0.45).all()
