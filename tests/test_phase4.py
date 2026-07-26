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

from laliga_predictor.modeling import run_phase4  # noqa: E402


@pytest.fixture(scope="module")
def phase4_summary() -> dict:
    return run_phase4()


def test_phase4_outputs(phase4_summary: dict) -> None:
    summary = phase4_summary
    assert summary["quality_passed"] is True
    assert summary["quality_checks"] == 10
    assert summary["models_evaluated"] == 5
    assert summary["validation_rows_per_model"] == 760
    assert summary["test_rows_per_model"] == 380
    assert summary["sport_features"] == 72
    assert summary["market_features"] == 75


def test_probabilities_are_valid(phase4_summary: dict) -> None:
    reports = PROJECT_ROOT / "reports"
    validation = pd.read_csv(reports / "model_predictions_validation.csv")
    test = pd.read_csv(reports / "model_predictions_test.csv")
    predictions = pd.concat([validation, test], ignore_index=True)
    columns = ["probability_home", "probability_draw", "probability_away"]
    assert np.isfinite(predictions[columns].to_numpy()).all()
    assert np.allclose(predictions[columns].sum(axis=1), 1.0)
    assert predictions[columns].ge(0).all().all()
    assert predictions[columns].le(1).all().all()


def test_test_is_not_part_of_model_selection(phase4_summary: dict) -> None:
    selection = json.loads(
        (PROJECT_ROOT / "reports" / "model_selection.json").read_text(
            encoding="utf-8"
        )
    )
    assert selection["test_protocol"]["evaluate_once"] == "2025/26"
    assert all(
        fold["evaluate"] != "2025/26"
        for fold in selection["validation_protocol"]
    )


def test_each_model_has_complete_temporal_predictions(phase4_summary: dict) -> None:
    reports = PROJECT_ROOT / "reports"
    validation = pd.read_csv(reports / "model_predictions_validation.csv")
    test = pd.read_csv(reports / "model_predictions_test.csv")
    assert validation.groupby("model").size().eq(760).all()
    assert test.groupby("model").size().eq(380).all()
    assert set(validation["season"]) == {"2023/24", "2024/25"}
    assert set(test["season"]) == {"2025/26"}
