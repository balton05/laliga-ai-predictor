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

from laliga_predictor.advanced_modeling import run_phase6  # noqa: E402


@pytest.fixture(scope="module")
def phase6_summary() -> dict:
    return run_phase6()


def test_phase6_outputs(phase6_summary: dict) -> None:
    assert phase6_summary["quality_passed"] is True
    assert phase6_summary["quality_checks"] == 14
    assert phase6_summary["advanced_models_evaluated"] == 4
    assert phase6_summary["candidate_configurations"] == 64
    assert phase6_summary["validation_rows_per_model"] == 760
    assert phase6_summary["test_rows_per_model"] == 380
    assert phase6_summary["fixture_predictions_2026_27"] == 380


def test_advanced_probabilities_are_valid(phase6_summary: dict) -> None:
    validation = pd.read_csv(
        PROJECT_ROOT / "reports" / "advanced_model_predictions_validation.csv"
    )
    test = pd.read_csv(
        PROJECT_ROOT / "reports" / "advanced_model_predictions_test.csv"
    )
    predictions = pd.concat([validation, test], ignore_index=True)
    columns = ["probability_home", "probability_draw", "probability_away"]
    values = predictions[columns].to_numpy(dtype=float)
    assert np.isfinite(values).all()
    assert np.allclose(values.sum(axis=1), 1.0)
    assert ((values >= 0.0) & (values <= 1.0)).all()


def test_test_season_is_not_used_for_selection(phase6_summary: dict) -> None:
    selection = json.loads(
        (
            PROJECT_ROOT / "reports" / "advanced_model_selection.json"
        ).read_text(encoding="utf-8")
    )
    assert selection["test_protocol"]["evaluate_once"] == "2025/26"
    assert all(
        fold["evaluate"] != "2025/26"
        for fold in selection["validation_protocol"]
    )


def test_fixture_predictions_are_sports_only(phase6_summary: dict) -> None:
    fixtures = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "fixtures_2026_27_advanced_predictions.csv"
    )
    columns = ["probability_home", "probability_draw", "probability_away"]
    assert len(fixtures) == 380
    assert fixtures["fixture_id"].is_unique
    assert fixtures.groupby("matchday").size().eq(10).all()
    assert np.allclose(fixtures[columns].sum(axis=1), 1.0)
    assert fixtures["requires_dynamic_update"].all()
    assert not fixtures["market_odds_available"].any()
    assert fixtures["model"].str.endswith("_sports").all()


def test_feature_importance_uses_validation(phase6_summary: dict) -> None:
    importance = pd.read_csv(
        PROJECT_ROOT
        / "reports"
        / "advanced_model_feature_importance.csv"
    )
    assert importance["model"].nunique() == 4
    assert importance.groupby("model").size().ge(72).all()
    assert importance.groupby("model")["rank"].min().eq(1).all()
