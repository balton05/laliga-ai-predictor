from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.features import (  # noqa: E402
    build_match_features,
    run_phase2,
)
from laliga_predictor.pipeline import (  # noqa: E402
    build_promotions,
    build_team_match_history,
    load_fixtures,
    load_historical_matches,
)


def test_phase2_outputs() -> None:
    summary = run_phase2()
    assert summary["quality_passed"] is True
    assert summary["historical_matches_with_features"] == 6110
    assert summary["laliga_matches_with_features"] == 3800
    assert summary["team_pre_match_rows"] == 12220
    assert summary["laliga_train_rows"] == 2660
    assert summary["laliga_validation_rows"] == 760
    assert summary["laliga_test_rows"] == 380
    assert summary["preseason_teams"] == 20
    assert summary["fixture_seed_rows"] == 380
    assert set(summary["promoted_preseason_teams"]) == {
        "Racing de Santander",
        "RC Deportivo",
        "Málaga CF",
    }


def test_market_probabilities_sum_to_one() -> None:
    run_phase2()
    features = pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "laliga_match_features.csv"
    )
    columns = [
        "market_probability_home",
        "market_probability_draw",
        "market_probability_away",
    ]
    complete = features[columns].notna().all(axis=1)
    assert np.allclose(features.loc[complete, columns].sum(axis=1), 1.0)


def test_current_match_statistics_do_not_change_its_features() -> None:
    matches = load_historical_matches()
    fixtures = load_fixtures()
    promotions = build_promotions(matches, fixtures)
    history = build_team_match_history(matches)
    original, _, _ = build_match_features(matches, history, promotions)

    target_id = matches.iloc[900]["match_id"]
    changed_matches = matches.copy()
    index = changed_matches.index[changed_matches["match_id"].eq(target_id)][0]
    changed_matches.loc[index, ["home_goals", "away_goals"]] = [9, 0]
    changed_matches.loc[index, "result"] = "H"
    changed_matches.loc[
        index,
        [
            "home_shots",
            "away_shots",
            "home_shots_on_target",
            "away_shots_on_target",
            "home_corners",
            "away_corners",
        ],
    ] = [40, 1, 20, 0, 18, 0]
    changed_history = build_team_match_history(changed_matches)
    changed, _, _ = build_match_features(
        changed_matches,
        changed_history,
        promotions,
    )

    excluded = {
        "target_ftr",
        "target_class",
        "odds_b365_home",
        "odds_b365_draw",
        "odds_b365_away",
        "odds_avg_home",
        "odds_avg_draw",
        "odds_avg_away",
        "odds_max_home",
        "odds_max_draw",
        "odds_max_away",
    }
    compare_columns = [
        column
        for column in original.columns
        if column not in excluded
    ]
    original_row = original.loc[
        original["match_id"].eq(target_id),
        compare_columns,
    ].reset_index(drop=True)
    changed_row = changed.loc[
        changed["match_id"].eq(target_id),
        compare_columns,
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        original_row,
        changed_row,
        check_dtype=False,
    )


def test_locked_temporal_split() -> None:
    run_phase2()
    features = pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "laliga_match_features.csv"
    )
    assert features.loc[
        features["season"].eq("2025/26"),
        "temporal_split",
    ].eq("test").all()
    assert features.loc[
        features["season"].isin(["2023/24", "2024/25"]),
        "temporal_split",
    ].eq("validation").all()
