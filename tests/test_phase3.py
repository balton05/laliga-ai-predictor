from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.eda import run_phase3  # noqa: E402


def test_phase3_outputs() -> None:
    summary = run_phase3()
    assert summary["quality_passed"] is True
    assert summary["laliga_matches"] == 3800
    assert summary["seasons"] == 10
    assert summary["promoted_team_seasons"] == 27
    assert len(summary["figures"]) == 7


def test_result_rates_sum_to_one() -> None:
    run_phase3()
    season = pd.read_csv(PROJECT_ROOT / "reports" / "eda_season_summary.csv")
    assert np.allclose(
        season[["h_rate", "d_rate", "a_rate"]].sum(axis=1),
        1.0,
    )


def test_feature_associations_use_train_rows_only() -> None:
    run_phase3()
    associations = pd.read_csv(
        PROJECT_ROOT / "reports" / "eda_feature_associations_train.csv"
    )
    assert associations["observations"].max() <= 2660


def test_favorite_strategy_is_reconciled() -> None:
    run_phase3()
    strategy = pd.read_csv(
        PROJECT_ROOT / "reports" / "eda_favorite_strategy.csv"
    )
    total = strategy.loc[strategy["season"].eq("TOTAL")].iloc[0]
    assert total["bets"] <= 3800
    assert -1.0 <= total["roi"] <= 10.0
