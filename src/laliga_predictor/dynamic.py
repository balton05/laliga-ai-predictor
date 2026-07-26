from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .config import PROJECT_ROOT, PROCESSED_DIR, REPORTS_DIR, TEAM_NAMES
from .ensembling import (
    PROBABILITY_COLUMNS,
    _combine_probabilities,
    _temperature_scale,
)
from .features import ELO_HOME_ADVANTAGE, ELO_K
from .goal_modeling import (
    MAX_GOALS,
    _fit_goal_model,
    _top_scorelines,
)
from .modeling import CLASS_LABELS, MARKET_FEATURES, SPORT_FEATURES
from .simulation import (
    RANDOM_SEED,
    SIMULATIONS,
    _position_distribution,
    _rank_tables,
    _sample_conditioned_scorelines,
    _scoreline_distributions,
    _summary_table,
)


SEASON = "2026/27"
INCOMING_DIR = PROJECT_ROOT / "data" / "incoming"
SNAPSHOT_DIR = PROJECT_ROOT / "snapshots"
DEFAULT_RESULTS_PATH = INCOMING_DIR / "results_2026_27.csv"
DEFAULT_ODDS_PATH = INCOMING_DIR / "odds_2026_27.csv"

RESULT_COLUMNS = [
    "fixture_id",
    "date",
    "home_goals",
    "away_goals",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "home_corners",
    "away_corners",
    "home_yellow_cards",
    "away_yellow_cards",
    "home_red_cards",
    "away_red_cards",
]
ODDS_COLUMNS = [
    "fixture_id",
    "captured_at",
    "odds_b365_home",
    "odds_b365_draw",
    "odds_b365_away",
]
OPTIONAL_RESULT_STATS = RESULT_COLUMNS[4:]
CURRENT_SEASON_NUMERIC = [
    "home_goals",
    "away_goals",
    *OPTIONAL_RESULT_STATS,
]


def _read_optional_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")
    return frame[columns].copy()


def _normalize_results(results: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    output = results.copy()
    if output.empty:
        return pd.DataFrame(
            columns=[
                *RESULT_COLUMNS,
                "season",
                "division",
                "matchday",
                "home_team_id",
                "home_team",
                "away_team_id",
                "away_team",
                "result",
                "match_id",
            ]
        )

    output["fixture_id"] = output["fixture_id"].astype("string").str.strip()
    if output["fixture_id"].isna().any() or output["fixture_id"].eq("").any():
        raise ValueError("Every result must include fixture_id.")
    if output["fixture_id"].duplicated().any():
        duplicated = output.loc[
            output["fixture_id"].duplicated(), "fixture_id"
        ].tolist()
        raise ValueError(f"Duplicated result fixture_id values: {duplicated}")

    known = set(fixtures["fixture_id"])
    unknown = sorted(set(output["fixture_id"]) - known)
    if unknown:
        raise ValueError(f"Unknown fixture_id values in results: {unknown[:5]}")

    output["date"] = pd.to_datetime(output["date"], errors="raise")
    for column in ["home_goals", "away_goals"]:
        output[column] = pd.to_numeric(output[column], errors="raise")
        if output[column].isna().any() or (output[column] < 0).any():
            raise ValueError(f"{column} must contain non-negative integers.")
        if not np.allclose(output[column], np.floor(output[column])):
            raise ValueError(f"{column} must contain integers.")
        output[column] = output[column].astype(int)
    for column in OPTIONAL_RESULT_STATS:
        output[column] = pd.to_numeric(output[column], errors="coerce")
        if (output[column].dropna() < 0).any():
            raise ValueError(f"{column} cannot contain negative values.")

    fixture_columns = [
        "fixture_id",
        "season",
        "matchday",
        "home_team_id",
        "home_team",
        "away_team_id",
        "away_team",
    ]
    output = output.merge(
        fixtures[fixture_columns],
        on="fixture_id",
        how="left",
        validate="one_to_one",
    )
    output["division"] = "SP1"
    output["result"] = np.select(
        [
            output["home_goals"].gt(output["away_goals"]),
            output["home_goals"].lt(output["away_goals"]),
        ],
        ["H", "A"],
        default="D",
    )
    output["match_id"] = output["fixture_id"]
    return output.sort_values(["date", "fixture_id"]).reset_index(drop=True)


def _normalize_odds(odds: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    output = odds.copy()
    if output.empty:
        return pd.DataFrame(
            columns=[
                *ODDS_COLUMNS,
                "market_probability_home",
                "market_probability_draw",
                "market_probability_away",
                "market_overround",
            ]
        )
    output["fixture_id"] = output["fixture_id"].astype("string").str.strip()
    known = set(fixtures["fixture_id"])
    unknown = sorted(set(output["fixture_id"]) - known)
    if unknown:
        raise ValueError(f"Unknown fixture_id values in odds: {unknown[:5]}")
    output["captured_at"] = pd.to_datetime(
        output["captured_at"], errors="raise", utc=True
    )
    for column in ODDS_COLUMNS[2:]:
        output[column] = pd.to_numeric(output[column], errors="raise")
        if (output[column] <= 1.0).any():
            raise ValueError(f"{column} values must be greater than 1.0.")

    output = (
        output.sort_values(["fixture_id", "captured_at"])
        .drop_duplicates("fixture_id", keep="last")
        .reset_index(drop=True)
    )
    raw = 1.0 / output[ODDS_COLUMNS[2:]].to_numpy(dtype=float)
    output["market_overround"] = raw.sum(axis=1)
    normalized = raw / raw.sum(axis=1, keepdims=True)
    output["market_probability_home"] = normalized[:, 0]
    output["market_probability_draw"] = normalized[:, 1]
    output["market_probability_away"] = normalized[:, 2]
    return output


def _validate_matchday_completeness(
    results: pd.DataFrame,
    allow_partial: bool,
) -> None:
    if results.empty or allow_partial:
        return
    counts = results.groupby("matchday")["fixture_id"].count()
    incomplete = counts[counts.ne(10)]
    if not incomplete.empty:
        detail = ", ".join(
            f"J{int(matchday)}={int(count)}"
            for matchday, count in incomplete.items()
        )
        raise ValueError(
            "A jornada update must contain all 10 results. "
            f"Incomplete: {detail}. Use allow_partial only for a live update."
        )


def _team_history_rows(results: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for row in results.itertuples(index=False):
        for venue in ("home", "away"):
            is_home = venue == "home"
            result = row.result
            team_result = (
                ("W" if result == "H" else "L" if result == "A" else "D")
                if is_home
                else ("W" if result == "A" else "L" if result == "H" else "D")
            )
            records.append(
                {
                    "match_id": row.match_id,
                    "season": row.season,
                    "division": row.division,
                    "date": row.date,
                    "team_id": row.home_team_id if is_home else row.away_team_id,
                    "team": row.home_team if is_home else row.away_team,
                    "opponent_id": (
                        row.away_team_id if is_home else row.home_team_id
                    ),
                    "opponent": row.away_team if is_home else row.home_team,
                    "venue": venue,
                    "team_result": team_result,
                    "points": 3 if team_result == "W" else 1 if team_result == "D" else 0,
                    "goals_for": row.home_goals if is_home else row.away_goals,
                    "goals_against": row.away_goals if is_home else row.home_goals,
                    "shots_for": row.home_shots if is_home else row.away_shots,
                    "shots_against": row.away_shots if is_home else row.home_shots,
                    "shots_on_target_for": (
                        row.home_shots_on_target
                        if is_home
                        else row.away_shots_on_target
                    ),
                    "shots_on_target_against": (
                        row.away_shots_on_target
                        if is_home
                        else row.home_shots_on_target
                    ),
                    "corners_for": row.home_corners if is_home else row.away_corners,
                    "corners_against": (
                        row.away_corners if is_home else row.home_corners
                    ),
                    "yellow_cards_for": (
                        row.home_yellow_cards
                        if is_home
                        else row.away_yellow_cards
                    ),
                    "yellow_cards_against": (
                        row.away_yellow_cards
                        if is_home
                        else row.home_yellow_cards
                    ),
                    "red_cards_for": (
                        row.home_red_cards if is_home else row.away_red_cards
                    ),
                    "red_cards_against": (
                        row.away_red_cards if is_home else row.home_red_cards
                    ),
                }
            )
    return pd.DataFrame(records)


def _mean(frame: pd.DataFrame, column: str) -> float:
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.mean()) if values.notna().any() else np.nan


def _rate(frame: pd.DataFrame, result: str) -> float:
    return float(frame["team_result"].eq(result).mean()) if len(frame) else np.nan


def _table_state(results: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    teams = pd.concat(
        [
            fixtures[["home_team_id", "home_team"]].rename(
                columns={"home_team_id": "team_id", "home_team": "team"}
            ),
            fixtures[["away_team_id", "away_team"]].rename(
                columns={"away_team_id": "team_id", "away_team": "team"}
            ),
        ],
        ignore_index=True,
    ).drop_duplicates("team_id")
    state = teams.assign(
        played=0,
        wins=0,
        draws=0,
        losses=0,
        goals_for=0,
        goals_against=0,
        points=0,
    ).set_index("team_id")
    for row in results.itertuples(index=False):
        for team, goals_for, goals_against, outcome in [
            (
                row.home_team_id,
                row.home_goals,
                row.away_goals,
                "W" if row.result == "H" else "L" if row.result == "A" else "D",
            ),
            (
                row.away_team_id,
                row.away_goals,
                row.home_goals,
                "W" if row.result == "A" else "L" if row.result == "H" else "D",
            ),
        ]:
            state.loc[team, "played"] += 1
            state.loc[team, "goals_for"] += int(goals_for)
            state.loc[team, "goals_against"] += int(goals_against)
            state.loc[team, {"W": "wins", "D": "draws", "L": "losses"}[outcome]] += 1
            state.loc[team, "points"] += {"W": 3, "D": 1, "L": 0}[outcome]
    state = state.reset_index()
    state["goal_difference"] = state["goals_for"] - state["goals_against"]
    state = state.sort_values(
        ["points", "goal_difference", "goals_for", "team"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    state["position"] = (
        np.arange(1, len(state) + 1)
        if state["played"].sum() > 0
        else np.nan
    )
    state["ppg"] = np.where(
        state["played"].gt(0), state["points"] / state["played"], np.nan
    )
    return state


def _elo_state(
    results: pd.DataFrame,
    preseason_state: pd.DataFrame,
) -> dict[str, float]:
    ratings = dict(
        zip(
            preseason_state["team_id"],
            pd.to_numeric(
                preseason_state["elo_initial_2026_27"], errors="raise"
            ),
        )
    )
    for row in results.sort_values(["date", "fixture_id"]).itertuples(index=False):
        home = ratings[row.home_team_id]
        away = ratings[row.away_team_id]
        expected_home = 1.0 / (
            1.0 + 10.0 ** ((away - (home + ELO_HOME_ADVANTAGE)) / 400.0)
        )
        score = {"H": 1.0, "D": 0.5, "A": 0.0}[row.result]
        change = ELO_K * (score - expected_home)
        ratings[row.home_team_id] = home + change
        ratings[row.away_team_id] = away - change
    return ratings


def _team_state(
    results: pd.DataFrame,
    fixtures: pd.DataFrame,
    snapshot_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    historical = pd.read_csv(
        PROCESSED_DIR / "team_match_history.csv",
        parse_dates=["date"],
    )
    current = _team_history_rows(results)
    if not current.empty:
        current["date"] = pd.to_datetime(current["date"])
        history = pd.concat([historical, current], ignore_index=True)
    else:
        history = historical
    history = history.sort_values(["team_id", "date", "match_id"])

    preseason = pd.read_csv(PROCESSED_DIR / "team_preseason_state_2026_27.csv")
    promoted = preseason.set_index("team_id")
    table = _table_state(results, fixtures)
    table_lookup = table.set_index("team_id")
    ratings = _elo_state(results, preseason)
    teams = sorted(set(fixtures["home_team_id"]) | set(fixtures["away_team_id"]))
    records: list[dict] = []
    for team_id in teams:
        rows = history[history["team_id"].eq(team_id)]
        season_rows = rows[rows["season"].eq(SEASON)]
        last5 = rows.tail(5)
        last10 = rows.tail(10)
        home5 = rows[rows["venue"].eq("home")].tail(5)
        away5 = rows[rows["venue"].eq("away")].tail(5)
        last_date = pd.to_datetime(rows["date"]).max()
        promotion_row = promoted.loc[team_id]
        table_row = table_lookup.loc[team_id]
        played = int(table_row["played"])
        records.append(
            {
                "team_id": team_id,
                "team": TEAM_NAMES[team_id],
                "snapshot_date": snapshot_date,
                "promoted": int(promotion_row["promoted"]),
                "segunda_position": promotion_row["segunda_position"],
                "division_changed": int(promotion_row["promoted"]),
                "history_matches": len(rows),
                "season_matches_pre": played,
                "days_since_last_match": (
                    int((snapshot_date - last_date).days)
                    if pd.notna(last_date)
                    else np.nan
                ),
                "form_matches_5": len(last5),
                "form_ppg_5": _mean(last5, "points"),
                "form_win_rate_5": _rate(last5, "W"),
                "form_draw_rate_5": _rate(last5, "D"),
                "form_goals_for_avg_5": _mean(last5, "goals_for"),
                "form_goals_against_avg_5": _mean(last5, "goals_against"),
                "form_goal_difference_avg_5": (
                    _mean(last5, "goals_for") - _mean(last5, "goals_against")
                ),
                "form_shots_on_target_for_avg_5": _mean(
                    last5, "shots_on_target_for"
                ),
                "form_shots_on_target_against_avg_5": _mean(
                    last5, "shots_on_target_against"
                ),
                "form_matches_10": len(last10),
                "form_ppg_10": _mean(last10, "points"),
                "form_goals_for_avg_10": _mean(last10, "goals_for"),
                "form_goals_against_avg_10": _mean(last10, "goals_against"),
                "form_goal_difference_avg_10": (
                    _mean(last10, "goals_for") - _mean(last10, "goals_against")
                ),
                "home_venue_ppg_5": _mean(home5, "points"),
                "home_venue_win_rate_5": _rate(home5, "W"),
                "home_venue_goals_for_avg_5": _mean(home5, "goals_for"),
                "home_venue_goals_against_avg_5": _mean(home5, "goals_against"),
                "home_venue_shots_on_target_for_avg_5": _mean(
                    home5, "shots_on_target_for"
                ),
                "away_venue_ppg_5": _mean(away5, "points"),
                "away_venue_win_rate_5": _rate(away5, "W"),
                "away_venue_goals_for_avg_5": _mean(away5, "goals_for"),
                "away_venue_goals_against_avg_5": _mean(
                    away5, "goals_against"
                ),
                "away_venue_shots_on_target_for_avg_5": _mean(
                    away5, "shots_on_target_for"
                ),
                "season_ppg_pre": _mean(season_rows, "points"),
                "season_win_rate_pre": _rate(season_rows, "W"),
                "season_goals_for_avg_pre": _mean(season_rows, "goals_for"),
                "season_goals_against_avg_pre": _mean(
                    season_rows, "goals_against"
                ),
                "season_goal_difference_avg_pre": (
                    _mean(season_rows, "goals_for")
                    - _mean(season_rows, "goals_against")
                ),
                "league_position_pre": (
                    float(table_row["position"]) if played else np.nan
                ),
                "elo_pre": ratings[team_id],
                "current_points": int(table_row["points"]),
                "current_goal_difference": int(table_row["goal_difference"]),
            }
        )
    return pd.DataFrame(records), table


def _fixture_features(
    remaining: pd.DataFrame,
    team_state: pd.DataFrame,
) -> pd.DataFrame:
    state = team_state.set_index("team_id")
    output = remaining.copy().reset_index(drop=True)
    features = pd.DataFrame(
        np.nan, index=output.index, columns=SPORT_FEATURES, dtype=float
    )
    for index, row in output.iterrows():
        home = state.loc[row["home_team_id"]]
        away = state.loc[row["away_team_id"]]
        date_value = row["scheduled_date"]
        if pd.isna(date_value):
            date_value = row["reference_date"]
        fixture_date = pd.to_datetime(date_value)
        for side, team in (("home", home), ("away", away)):
            for feature in [
                "promoted",
                "segunda_position",
                "division_changed",
                "season_matches_pre",
                "form_ppg_5",
                "form_win_rate_5",
                "form_draw_rate_5",
                "form_goals_for_avg_5",
                "form_goals_against_avg_5",
                "form_goal_difference_avg_5",
                "form_shots_on_target_for_avg_5",
                "form_shots_on_target_against_avg_5",
                "form_ppg_10",
                "form_goals_for_avg_10",
                "form_goals_against_avg_10",
                "form_goal_difference_avg_10",
                "season_ppg_pre",
                "season_win_rate_pre",
                "season_goals_for_avg_pre",
                "season_goals_against_avg_pre",
                "season_goal_difference_avg_pre",
                "league_position_pre",
            ]:
                features.loc[index, f"{side}_{feature}"] = team[feature]
            venue_prefix = "home" if side == "home" else "away"
            for feature in [
                "venue_ppg_5",
                "venue_win_rate_5",
                "venue_goals_for_avg_5",
                "venue_goals_against_avg_5",
                "venue_shots_on_target_for_avg_5",
            ]:
                features.loc[index, f"{side}_{feature}"] = team[
                    f"{venue_prefix}_{feature}"
                ]
            features.loc[index, f"{side}_days_rest"] = max(
                0.0,
                float(team["days_since_last_match"])
                + float((fixture_date - pd.to_datetime(team["snapshot_date"])).days),
            )
            features.loc[index, f"{side}_elo_pre"] = team["elo_pre"]

        features.loc[index, "history_ready_5"] = float(
            home["form_matches_5"] >= 5 and away["form_matches_5"] >= 5
        )
        features.loc[index, "history_ready_10"] = float(
            home["form_matches_10"] >= 10 and away["form_matches_10"] >= 10
        )

    features["elo_difference_pre"] = (
        features["home_elo_pre"] - features["away_elo_pre"]
    )
    features["elo_expected_home"] = 1.0 / (
        1.0
        + 10.0
        ** (
            (
                features["away_elo_pre"]
                - (features["home_elo_pre"] + ELO_HOME_ADVANTAGE)
            )
            / 400.0
        )
    )
    features["season_ppg_difference"] = (
        features["home_season_ppg_pre"] - features["away_season_ppg_pre"]
    )
    features["season_win_rate_difference"] = (
        features["home_season_win_rate_pre"]
        - features["away_season_win_rate_pre"]
    )
    features["season_goal_difference_avg"] = (
        features["home_season_goal_difference_avg_pre"]
        - features["away_season_goal_difference_avg_pre"]
    )
    features["form_ppg_5_difference"] = (
        features["home_form_ppg_5"] - features["away_form_ppg_5"]
    )
    features["form_ppg_10_difference"] = (
        features["home_form_ppg_10"] - features["away_form_ppg_10"]
    )
    features["form_goal_difference_5_difference"] = (
        features["home_form_goal_difference_avg_5"]
        - features["away_form_goal_difference_avg_5"]
    )
    features["form_shots_on_target_5_difference"] = (
        features["home_form_shots_on_target_for_avg_5"]
        - features["away_form_shots_on_target_for_avg_5"]
    )
    features["venue_ppg_5_difference"] = (
        features["home_venue_ppg_5"] - features["away_venue_ppg_5"]
    )
    features["days_rest_difference"] = (
        features["home_days_rest"] - features["away_days_rest"]
    )
    features["league_position_advantage"] = (
        features["away_league_position_pre"]
        - features["home_league_position_pre"]
    )
    return pd.concat([output, features], axis=1)


def _smooth(probabilities: np.ndarray, specification: dict) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    weight = float(specification.get("prior_blend", 0.0))
    if weight:
        values = (
            (1.0 - weight) * values
            + weight * np.asarray(specification["prior"]).reshape(1, -1)
        )
    values = np.clip(values, 1e-12, 1.0)
    return values / values.sum(axis=1, keepdims=True)


def _goal_model(
    results: pd.DataFrame,
    production: dict,
) -> tuple[object, dict[str, tuple[float, float]], str]:
    base_model = production["models"]["poisson"]
    base_overrides = production["promoted_overrides"]
    if results.empty:
        return base_model, base_overrides, "production_2025_26"

    historical = pd.read_csv(
        PROCESSED_DIR / "matches_master.csv",
        parse_dates=["date"],
    )
    train = historical[historical["division"].eq("SP1")][
        [
            "match_id",
            "season",
            "date",
            "home_team_id",
            "away_team_id",
            "home_goals",
            "away_goals",
        ]
    ].copy()
    current = results[
        [
            "match_id",
            "season",
            "date",
            "home_team_id",
            "away_team_id",
            "home_goals",
            "away_goals",
        ]
    ].copy()
    train = pd.concat([train, current], ignore_index=True)
    model = _fit_goal_model(
        train,
        "poisson",
        base_model.half_life_days,
        SEASON,
    )
    team_index = {team: index for index, team in enumerate(model.teams)}
    overrides: dict[str, tuple[float, float]] = {}
    appearances = pd.concat(
        [
            results["home_team_id"],
            results["away_team_id"],
        ]
    ).value_counts()
    for team, prior in base_overrides.items():
        matches = int(appearances.get(team, 0))
        weight = min(matches / 10.0, 1.0)
        if team in team_index:
            index = team_index[team]
            fitted = (
                float(model.attack[index]),
                float(model.defense[index]),
            )
            overrides[team] = (
                (1.0 - weight) * float(prior[0]) + weight * fitted[0],
                (1.0 - weight) * float(prior[1]) + weight * fitted[1],
            )
        else:
            overrides[team] = prior
    return model, overrides, "refit_through_current_results"


def _goal_predictions(
    remaining: pd.DataFrame,
    results: pd.DataFrame,
    production: dict,
) -> pd.DataFrame:
    model, overrides, source = _goal_model(results, production)
    records: list[dict] = []
    for row in remaining.itertuples(index=False):
        matrix, expected_home, expected_away = model.score_matrix(
            row.home_team_id,
            row.away_team_id,
            overrides,
        )
        probabilities = np.asarray(
            [
                np.tril(matrix, -1).sum(),
                np.trace(matrix),
                np.triu(matrix, 1).sum(),
            ],
            dtype=float,
        )
        probabilities /= probabilities.sum()
        top = _top_scorelines(matrix)
        records.append(
            {
                "fixture_id": row.fixture_id,
                "expected_home_goals": expected_home,
                "expected_away_goals": expected_away,
                "poisson_probability_home": probabilities[0],
                "poisson_probability_draw": probabilities[1],
                "poisson_probability_away": probabilities[2],
                "predicted_score": f"{top[0][0]}-{top[0][1]}",
                "predicted_score_probability": top[0][2],
                "goal_model_source": source,
                "promoted_adjustment_applied": int(
                    row.home_team_id in overrides or row.away_team_id in overrides
                ),
            }
        )
    return pd.DataFrame(records)


def _predict_remaining(
    features: pd.DataFrame,
    goal_predictions: pd.DataFrame,
    odds: pd.DataFrame,
) -> pd.DataFrame:
    phase7 = joblib.load(REPORTS_DIR / "phase7_production_ensemble.joblib")
    phase4 = joblib.load(REPORTS_DIR / "phase4_production_models.joblib")
    phase6 = joblib.load(REPORTS_DIR / "phase6_production_models.joblib")
    frame = features.merge(
        goal_predictions,
        on="fixture_id",
        how="left",
        validate="one_to_one",
    ).merge(
        odds,
        on="fixture_id",
        how="left",
        validate="one_to_one",
    )
    temperatures = phase7["temperatures"]

    logistic_sports = phase4["models"]["logistic_sports"]
    rf_sports = phase6["models"]["random_forest_sports"]
    sports_components = {
        "logistic_sports": _temperature_scale(
            logistic_sports["pipeline"].predict_proba(
                frame[logistic_sports["features"]]
            ),
            temperatures["logistic_sports"],
        ),
        "random_forest_sports": _temperature_scale(
            _smooth(
                rf_sports["pipeline"].predict_proba(frame[rf_sports["features"]]),
                rf_sports,
            ),
            temperatures["random_forest_sports"],
        ),
        "poisson": _temperature_scale(
            frame[
                [
                    "poisson_probability_home",
                    "poisson_probability_draw",
                    "poisson_probability_away",
                ]
            ].to_numpy(dtype=float),
            temperatures["poisson"],
        ),
    }
    sports_selection = phase7["ensembles"]["ensemble_sports"]
    sports_weights = np.asarray(
        [
            sports_selection["weights"][name]
            for name in sports_selection["components"]
        ]
    )
    sports_probability = _combine_probabilities(
        [sports_components[name] for name in sports_selection["components"]],
        sports_weights,
    )
    final_probability = sports_probability.copy()
    model = np.full(len(frame), "ensemble_sports", dtype=object)

    market_columns = [
        "market_probability_home",
        "market_probability_draw",
        "market_probability_away",
    ]
    market_available = frame[market_columns].notna().all(axis=1).to_numpy()
    if market_available.any():
        logistic_market = phase4["models"]["logistic_market"]
        rf_market = phase6["models"]["random_forest_market"]
        market_frame = frame.loc[market_available].copy()
        market_components = {
            "market": _temperature_scale(
                market_frame[market_columns].to_numpy(dtype=float),
                temperatures["market"],
            ),
            "logistic_market": _temperature_scale(
                logistic_market["pipeline"].predict_proba(
                    market_frame[logistic_market["features"]]
                ),
                temperatures["logistic_market"],
            ),
            "random_forest_market": _temperature_scale(
                _smooth(
                    rf_market["pipeline"].predict_proba(
                        market_frame[rf_market["features"]]
                    ),
                    rf_market,
                ),
                temperatures["random_forest_market"],
            ),
            "poisson": sports_components["poisson"][market_available],
        }
        selection = phase7["ensembles"]["ensemble_market"]
        weights = np.asarray(
            [selection["weights"][name] for name in selection["components"]]
        )
        final_probability[market_available] = _combine_probabilities(
            [
                market_components[name]
                for name in selection["components"]
            ],
            weights,
        )
        model[market_available] = "ensemble_market"

    predicted = final_probability.argmax(axis=1)
    ordered = np.sort(final_probability, axis=1)
    output_columns = [
        "fixture_id",
        "season",
        "matchday",
        "reference_date",
        "scheduled_date",
        "kickoff_time",
        "home_team_id",
        "home_team",
        "away_team_id",
        "away_team",
        "expected_home_goals",
        "expected_away_goals",
        "predicted_score",
        "predicted_score_probability",
        "goal_model_source",
        "promoted_adjustment_applied",
    ]
    output = frame[output_columns].copy()
    output["model"] = model
    output["probability_home"] = final_probability[:, 0]
    output["probability_draw"] = final_probability[:, 1]
    output["probability_away"] = final_probability[:, 2]
    output["predicted_ftr"] = pd.Series(predicted).map(
        dict(enumerate(CLASS_LABELS))
    )
    output["probability_edge"] = ordered[:, -1] - ordered[:, -2]
    output["confidence"] = np.select(
        [
            output["probability_edge"].lt(0.08),
            final_probability.max(axis=1) >= 0.60,
        ],
        ["low", "high"],
        default="medium",
    )
    output["market_odds_available"] = market_available
    output["feature_snapshot"] = "dynamic_current_results"
    output["requires_dynamic_update"] = False
    return output.sort_values(["matchday", "fixture_id"]).reset_index(drop=True)


def _preseason_predictions() -> pd.DataFrame:
    ensemble = pd.read_csv(
        PROCESSED_DIR / "fixtures_2026_27_ensemble_predictions.csv"
    )
    goals = pd.read_csv(
        PROCESSED_DIR / "fixtures_2026_27_goal_predictions.csv"
    )
    goal_columns = [
        "fixture_id",
        "expected_home_goals",
        "expected_away_goals",
        "predicted_score",
        "predicted_score_probability",
        "promoted_adjustment_applied",
    ]
    output = ensemble.merge(
        goals[goal_columns],
        on="fixture_id",
        how="left",
        validate="one_to_one",
    )
    output["goal_model_source"] = "production_2025_26"
    return output[
        [
            "fixture_id",
            "season",
            "matchday",
            "reference_date",
            "scheduled_date",
            "kickoff_time",
            "home_team_id",
            "home_team",
            "away_team_id",
            "away_team",
            "expected_home_goals",
            "expected_away_goals",
            "predicted_score",
            "predicted_score_probability",
            "goal_model_source",
            "promoted_adjustment_applied",
            "model",
            "probability_home",
            "probability_draw",
            "probability_away",
            "predicted_ftr",
            "probability_edge",
            "confidence",
            "market_odds_available",
            "feature_snapshot",
            "requires_dynamic_update",
        ]
    ].sort_values(["matchday", "fixture_id"]).reset_index(drop=True)


def _simulate_with_completed(
    predictions: pd.DataFrame,
    results: pd.DataFrame,
    fixtures: pd.DataFrame,
    simulations: int,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)
    team_frame = pd.concat(
        [
            fixtures[["home_team_id", "home_team"]].rename(
                columns={"home_team_id": "team_id", "home_team": "team"}
            ),
            fixtures[["away_team_id", "away_team"]].rename(
                columns={"away_team_id": "team_id", "away_team": "team"}
            ),
        ],
        ignore_index=True,
    ).drop_duplicates("team_id").sort_values("team")
    team_ids = team_frame["team_id"].tolist()
    team_names = team_frame["team"].tolist()
    team_index = {team_id: index for index, team_id in enumerate(team_ids)}
    team_count = len(team_ids)
    points = np.zeros((simulations, team_count), dtype=np.int16)
    goals_for = np.zeros_like(points)
    goals_against = np.zeros_like(points)
    h2h_points = np.zeros((simulations, team_count, team_count), dtype=np.int8)
    h2h_gd = np.zeros_like(h2h_points)
    rows = np.arange(simulations)
    outcome_counts = np.zeros(3, dtype=np.int64)

    for fixture in results.itertuples(index=False):
        home = team_index[fixture.home_team_id]
        away = team_index[fixture.away_team_id]
        home_points = 3 if fixture.result == "H" else 1 if fixture.result == "D" else 0
        away_points = 3 if fixture.result == "A" else 1 if fixture.result == "D" else 0
        points[:, home] += home_points
        points[:, away] += away_points
        goals_for[:, home] += int(fixture.home_goals)
        goals_against[:, home] += int(fixture.away_goals)
        goals_for[:, away] += int(fixture.away_goals)
        goals_against[:, away] += int(fixture.home_goals)
        h2h_points[:, home, away] += home_points
        h2h_points[:, away, home] += away_points
        goal_difference = int(fixture.home_goals - fixture.away_goals)
        h2h_gd[:, home, away] += goal_difference
        h2h_gd[:, away, home] -= goal_difference

    for fixture in predictions.itertuples(index=False):
        home = team_index[fixture.home_team_id]
        away = team_index[fixture.away_team_id]
        probabilities = np.asarray(
            [
                fixture.probability_home,
                fixture.probability_draw,
                fixture.probability_away,
            ],
            dtype=float,
        )
        draws = rng.random(simulations)
        outcomes = np.select(
            [
                draws < probabilities[0],
                draws < probabilities[0] + probabilities[1],
            ],
            [0, 1],
            default=2,
        ).astype(np.int8)
        outcome_counts += np.bincount(outcomes, minlength=3)
        distributions = _scoreline_distributions(
            fixture.expected_home_goals,
            fixture.expected_away_goals,
        )
        home_goals, away_goals = _sample_conditioned_scorelines(
            rng, outcomes, distributions
        )
        home_points = np.select(
            [outcomes == 0, outcomes == 1], [3, 1], default=0
        ).astype(np.int8)
        away_points = np.select(
            [outcomes == 2, outcomes == 1], [3, 1], default=0
        ).astype(np.int8)
        points[:, home] += home_points
        points[:, away] += away_points
        goals_for[:, home] += home_goals
        goals_against[:, home] += away_goals
        goals_for[:, away] += away_goals
        goals_against[:, away] += home_goals
        h2h_points[rows, home, away] += home_points
        h2h_points[rows, away, home] += away_points
        goal_difference = (home_goals - away_goals).astype(np.int8)
        h2h_gd[rows, home, away] += goal_difference
        h2h_gd[rows, away, home] -= goal_difference

    ranks = _rank_tables(points, goals_for, goals_against, h2h_points, h2h_gd)
    return {
        "team_ids": team_ids,
        "team_names": team_names,
        "points": points,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "ranks": ranks,
        "outcome_counts": outcome_counts,
    }


def _hash_frame(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    for column in normalized.select_dtypes(include=["datetime", "datetimetz"]):
        normalized[column] = normalized[column].astype("string")
    payload = normalized.fillna("").to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _update_id(results: pd.DataFrame, odds: pd.DataFrame) -> str:
    payload = f"{_hash_frame(results)}|{_hash_frame(odds)}|phase9-v1"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _quality_checks(
    fixtures: pd.DataFrame,
    results: pd.DataFrame,
    odds: pd.DataFrame,
    predictions: pd.DataFrame,
    simulation_summary: pd.DataFrame,
    position_distribution: pd.DataFrame,
) -> pd.DataFrame:
    probability_sum = (
        predictions[PROBABILITY_COLUMNS].sum(axis=1)
        if len(predictions)
        else pd.Series(dtype=float)
    )
    checks = [
        ("fixture_calendar_380", len(fixtures) == 380, len(fixtures)),
        ("fixture_ids_unique", fixtures["fixture_id"].is_unique, len(fixtures)),
        ("result_ids_unique", results["fixture_id"].is_unique, len(results)),
        (
            "results_and_predictions_partition_calendar",
            len(results) + len(predictions) == 380,
            len(results) + len(predictions),
        ),
        (
            "no_completed_fixture_is_predicted",
            set(results["fixture_id"]).isdisjoint(set(predictions["fixture_id"])),
            len(set(results["fixture_id"]) & set(predictions["fixture_id"])),
        ),
        (
            "prediction_probabilities_sum_to_one",
            bool(np.allclose(probability_sum, 1.0)) if len(predictions) else True,
            float((probability_sum - 1.0).abs().max()) if len(predictions) else 0.0,
        ),
        (
            "prediction_probabilities_in_range",
            bool(
                predictions[PROBABILITY_COLUMNS].ge(0).all().all()
                and predictions[PROBABILITY_COLUMNS].le(1).all().all()
            )
            if len(predictions)
            else True,
            len(predictions),
        ),
        (
            "market_model_only_with_odds",
            bool(
                predictions.loc[
                    predictions["model"].eq("ensemble_market"),
                    "market_odds_available",
                ].all()
            )
            if len(predictions)
            else True,
            int(predictions["model"].eq("ensemble_market").sum()),
        ),
        (
            "latest_odds_one_row_per_fixture",
            odds["fixture_id"].is_unique,
            len(odds),
        ),
        (
            "simulation_has_20_teams",
            len(simulation_summary) == 20,
            len(simulation_summary),
        ),
        (
            "champion_probability_reconciles",
            np.isclose(simulation_summary["champion_probability"].sum(), 1.0),
            simulation_summary["champion_probability"].sum(),
        ),
        (
            "top4_probability_reconciles",
            np.isclose(simulation_summary["top4_probability"].sum(), 4.0),
            simulation_summary["top4_probability"].sum(),
        ),
        (
            "top7_probability_reconciles",
            np.isclose(
                simulation_summary["europe_top7_probability"].sum(), 7.0
            ),
            simulation_summary["europe_top7_probability"].sum(),
        ),
        (
            "relegation_probability_reconciles",
            np.isclose(simulation_summary["relegation_probability"].sum(), 3.0),
            simulation_summary["relegation_probability"].sum(),
        ),
        (
            "position_distribution_400_rows",
            len(position_distribution) == 400,
            len(position_distribution),
        ),
        (
            "each_team_position_probabilities_sum_to_one",
            bool(
                np.allclose(
                    position_distribution.groupby("team")["probability"].sum(),
                    1.0,
                )
            ),
            len(position_distribution["team"].unique()),
        ),
    ]
    return pd.DataFrame(
        [
            {"check": check, "passed": bool(passed), "value": value}
            for check, passed, value in checks
        ]
    )


def _write_snapshot(
    update_id: str,
    files: list[Path],
    summary: dict,
) -> Path:
    destination = SNAPSHOT_DIR / update_id
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[dict] = []
    for source in files:
        if source.exists():
            target = destination / source.name
            shutil.copy2(source, target)
            copied.append(
                {
                    "file": source.name,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "bytes": target.stat().st_size,
                }
            )
    manifest = {
        "update_id": update_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "files": copied,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def _append_update_log(summary: dict) -> None:
    path = REPORTS_DIR / "phase9_update_log.csv"
    row = pd.DataFrame(
        [
            {
                "update_id": summary["update_id"],
                "created_at_utc": summary["created_at_utc"],
                "snapshot_date": summary["snapshot_date"],
                "completed_matches": summary["completed_matches"],
                "completed_matchdays": summary["completed_matchdays"],
                "remaining_matches": summary["remaining_matches"],
                "next_matchday": summary["next_matchday"],
                "market_predictions": summary["market_predictions"],
                "sports_predictions": summary["sports_predictions"],
                "simulations": summary["simulations"],
                "quality_passed": summary["quality_passed"],
            }
        ]
    )
    if path.exists():
        existing = pd.read_csv(path)
        existing = existing[~existing["update_id"].eq(summary["update_id"])]
        row = pd.concat([existing, row], ignore_index=True)
    row.to_csv(path, index=False, encoding="utf-8-sig")


def run_phase9(
    results_path: Path | str = DEFAULT_RESULTS_PATH,
    odds_path: Path | str = DEFAULT_ODDS_PATH,
    simulations: int = SIMULATIONS,
    seed: int = RANDOM_SEED,
    allow_partial: bool = False,
) -> dict:
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    results_path = Path(results_path)
    odds_path = Path(odds_path)

    fixtures = pd.read_csv(
        PROCESSED_DIR / "fixtures_2026_27.csv",
        parse_dates=["reference_date", "scheduled_date"],
    )
    raw_results = _read_optional_csv(results_path, RESULT_COLUMNS)
    raw_odds = _read_optional_csv(odds_path, ODDS_COLUMNS)
    results = _normalize_results(raw_results, fixtures)
    odds = _normalize_odds(raw_odds, fixtures)
    _validate_matchday_completeness(results, allow_partial)

    completed_ids = set(results["fixture_id"])
    remaining = fixtures[~fixtures["fixture_id"].isin(completed_ids)].copy()
    if results.empty:
        snapshot_date = pd.to_datetime(fixtures["reference_date"]).min()
    else:
        snapshot_date = pd.to_datetime(results["date"]).max() + pd.Timedelta(days=1)
    team_state, current_table = _team_state(results, fixtures, snapshot_date)
    features = _fixture_features(remaining, team_state)
    if results.empty and odds.empty:
        predictions = _preseason_predictions()
    else:
        goal_predictions = _goal_predictions(
            remaining,
            results,
            joblib.load(REPORTS_DIR / "phase7_production_ensemble.joblib"),
        )
        predictions = _predict_remaining(features, goal_predictions, odds)

    simulation = _simulate_with_completed(
        predictions,
        results,
        fixtures,
        simulations=simulations,
        seed=seed,
    )
    simulation_summary = _summary_table(simulation)
    position_distribution = _position_distribution(simulation)
    baseline = pd.read_csv(REPORTS_DIR / "season_simulation_summary.csv")
    comparison = simulation_summary.merge(
        baseline[
            [
                "team_id",
                "champion_probability",
                "top4_probability",
                "europe_top7_probability",
                "relegation_probability",
                "expected_points",
            ]
        ],
        on="team_id",
        suffixes=("_current", "_preseason"),
        validate="one_to_one",
    )
    for metric in [
        "champion_probability",
        "top4_probability",
        "europe_top7_probability",
        "relegation_probability",
        "expected_points",
    ]:
        comparison[f"{metric}_change"] = (
            comparison[f"{metric}_current"]
            - comparison[f"{metric}_preseason"]
        )

    next_matchday = (
        int(predictions["matchday"].min()) if len(predictions) else None
    )
    next_predictions = (
        predictions[predictions["matchday"].eq(next_matchday)].copy()
        if next_matchday is not None
        else predictions.copy()
    )
    quality = _quality_checks(
        fixtures,
        results,
        odds,
        predictions,
        simulation_summary,
        position_distribution,
    )
    quality_passed = bool(quality["passed"].all())
    if not quality_passed:
        failed = quality.loc[~quality["passed"], "check"].tolist()
        raise AssertionError(f"Phase 9 quality checks failed: {failed}")

    update_id = _update_id(results, odds)
    created_at = datetime.now(timezone.utc).isoformat()
    completed_matchdays = int(
        results.groupby("matchday").size().eq(10).sum()
    ) if len(results) else 0
    summary = {
        "phase": 9,
        "update_id": update_id,
        "created_at_utc": created_at,
        "season": SEASON,
        "snapshot_date": pd.Timestamp(snapshot_date).date().isoformat(),
        "completed_matches": len(results),
        "completed_matchdays": completed_matchdays,
        "remaining_matches": len(predictions),
        "next_matchday": next_matchday,
        "market_predictions": int(predictions["model"].eq("ensemble_market").sum()),
        "sports_predictions": int(predictions["model"].eq("ensemble_sports").sum()),
        "simulations": int(simulations),
        "seed": int(seed),
        "quality_checks": len(quality),
        "quality_passed": quality_passed,
        "pipeline_mode": "preseason_noop" if results.empty else "dynamic_update",
        "partial_update_allowed": bool(allow_partial),
        "market_policy": (
            "Use ensemble_market per fixture only when a complete current "
            "1X2 odds snapshot is available; otherwise use ensemble_sports."
        ),
        "model_retraining_policy": (
            "Classifiers remain frozen through 2025/26; sports features and "
            "Elo update each run; Poisson is refitted when 2026/27 results exist."
        ),
    }

    outputs = {
        PROCESSED_DIR / "current_results_2026_27.csv": results,
        PROCESSED_DIR / "current_team_state_2026_27.csv": team_state,
        PROCESSED_DIR / "current_fixture_features_2026_27.csv": features,
        PROCESSED_DIR / "current_predictions_2026_27.csv": predictions,
        REPORTS_DIR / "current_table_2026_27.csv": current_table,
        REPORTS_DIR / "dynamic_next_matchday_predictions.csv": next_predictions,
        REPORTS_DIR / "dynamic_season_simulation_summary.csv": simulation_summary,
        REPORTS_DIR / "dynamic_position_distribution.csv": position_distribution,
        REPORTS_DIR / "dynamic_preseason_comparison.csv": comparison,
        REPORTS_DIR / "phase9_quality_checks.csv": quality,
    }
    for path, frame in outputs.items():
        frame.to_csv(path, index=False, encoding="utf-8-sig")
    (REPORTS_DIR / "phase9_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _append_update_log(summary)
    snapshot_files = [*outputs.keys(), REPORTS_DIR / "phase9_summary.json"]
    snapshot_path = _write_snapshot(update_id, snapshot_files, summary)
    summary["snapshot_path"] = snapshot_path.relative_to(PROJECT_ROOT).as_posix()
    (REPORTS_DIR / "phase9_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
