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

from laliga_predictor.ensembling import run_phase7  # noqa: E402


@pytest.fixture(scope="module")
def phase7_summary() -> dict:
    return run_phase7()


def test_phase7_outputs(phase7_summary: dict) -> None:
    assert phase7_summary["quality_passed"] is True
    assert phase7_summary["quality_checks"] == 18
    assert phase7_summary["components_calibrated"] == 6
    assert phase7_summary["candidate_weight_combinations"] == 2002
    assert phase7_summary["validation_rows_per_ensemble"] == 760
    assert phase7_summary["test_rows_per_ensemble"] == 380
    assert phase7_summary["fixture_predictions_2026_27"] == 380


def test_ensemble_probabilities_are_valid(phase7_summary: dict) -> None:
    validation = pd.read_csv(
        PROJECT_ROOT / "reports" / "ensemble_predictions_validation.csv"
    )
    test = pd.read_csv(
        PROJECT_ROOT / "reports" / "ensemble_predictions_test.csv"
    )
    predictions = pd.concat([validation, test], ignore_index=True)
    columns = ["probability_home", "probability_draw", "probability_away"]
    values = predictions[columns].to_numpy(dtype=float)
    assert np.isfinite(values).all()
    assert np.allclose(values.sum(axis=1), 1.0)
    assert ((values >= 0.0) & (values <= 1.0)).all()
    assert validation.groupby("model").size().eq(760).all()
    assert test.groupby("model").size().eq(380).all()


def test_selection_does_not_use_test_season(phase7_summary: dict) -> None:
    selection = json.loads(
        (
            PROJECT_ROOT / "reports" / "ensemble_selection.json"
        ).read_text(encoding="utf-8")
    )
    assert selection["test_protocol"]["parameters_frozen_before_test"] is True
    assert selection["test_protocol"]["evaluate_once"] == "2025/26"
    assert all(
        fold["evaluate"] != "2025/26"
        for fold in selection["validation_protocol"]
    )


def test_ensemble_weights_are_valid(phase7_summary: dict) -> None:
    selection = json.loads(
        (
            PROJECT_ROOT / "reports" / "ensemble_selection.json"
        ).read_text(encoding="utf-8")
    )
    assert set(selection["ensembles"]) == {
        "ensemble_sports",
        "ensemble_market",
    }
    for specification in selection["ensembles"].values():
        weights = list(specification["weights"].values())
        assert np.isclose(sum(weights), 1.0)
        assert all(weight >= 0.0 for weight in weights)


def test_fixture_predictions_are_sports_only(
    phase7_summary: dict,
) -> None:
    fixtures = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "fixtures_2026_27_ensemble_predictions.csv"
    )
    columns = ["probability_home", "probability_draw", "probability_away"]
    assert len(fixtures) == 380
    assert fixtures["fixture_id"].is_unique
    assert fixtures.groupby("matchday").size().eq(10).all()
    assert np.allclose(fixtures[columns].sum(axis=1), 1.0)
    assert fixtures["requires_dynamic_update"].all()
    assert not fixtures["market_odds_available"].any()
    assert fixtures["model"].eq("ensemble_sports").all()


def test_test_improvements_are_reported_with_uncertainty(
    phase7_summary: dict,
) -> None:
    bootstrap = pd.read_csv(
        PROJECT_ROOT / "reports" / "ensemble_bootstrap_comparison.csv"
    )
    test = bootstrap[bootstrap["split"].eq("test")]
    assert len(test) == 4
    assert (
        test["ci_95_lower"]
        <= test["mean_log_loss_difference"]
    ).all()
    assert (
        test["ci_95_upper"]
        >= test["mean_log_loss_difference"]
    ).all()
    assert not phase7_summary[
        "market_improvement_statistically_clear"
    ]
    assert not phase7_summary[
        "sports_improvement_statistically_clear"
    ]
