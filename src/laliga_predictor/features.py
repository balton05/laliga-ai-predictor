from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import PROCESSED_DIR, REPORTS_DIR, TEAM_NAMES
from .pipeline import (
    build_promotions,
    load_fixtures,
    load_historical_matches,
    write_csv,
)


TARGET_CLASS = {"H": 0, "D": 1, "A": 2}
DIVISION_BASE_ELO = {"SP1": 1500.0, "SP2": 1350.0}
ELO_K = 20.0
ELO_HOME_ADVANTAGE = 60.0
ELO_SEASON_REGRESSION = 0.25

ROLLING_METRICS = [
    "points",
    "_win",
    "_draw",
    "_loss",
    "goals_for",
    "goals_against",
    "_goal_difference",
    "shots_for",
    "shots_against",
    "shots_on_target_for",
    "shots_on_target_against",
    "corners_for",
    "corners_against",
    "yellow_cards_for",
    "yellow_cards_against",
]

ROLLING_NAMES = {
    "points": "ppg",
    "_win": "win_rate",
    "_draw": "draw_rate",
    "_loss": "loss_rate",
    "goals_for": "goals_for_avg",
    "goals_against": "goals_against_avg",
    "_goal_difference": "goal_difference_avg",
    "shots_for": "shots_for_avg",
    "shots_against": "shots_against_avg",
    "shots_on_target_for": "shots_on_target_for_avg",
    "shots_on_target_against": "shots_on_target_against_avg",
    "corners_for": "corners_for_avg",
    "corners_against": "corners_against_avg",
    "yellow_cards_for": "yellow_cards_for_avg",
    "yellow_cards_against": "yellow_cards_against_avg",
}

CORE_MODEL_FEATURES = [
    "home_promoted",
    "away_promoted",
    "home_segunda_position",
    "away_segunda_position",
    "history_ready_5",
    "history_ready_10",
    "home_season_matches_pre",
    "away_season_matches_pre",
    "home_days_rest",
    "away_days_rest",
    "home_division_changed",
    "away_division_changed",
    *[
        f"{side}_{metric}"
        for side in ("home", "away")
        for metric in (
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
            "venue_ppg_5",
            "venue_win_rate_5",
            "venue_goals_for_avg_5",
            "venue_goals_against_avg_5",
            "venue_shots_on_target_for_avg_5",
            "season_ppg_pre",
            "season_win_rate_pre",
            "season_goals_for_avg_pre",
            "season_goals_against_avg_pre",
            "season_goal_difference_avg_pre",
            "league_position_pre",
        )
    ],
    "home_elo_pre",
    "away_elo_pre",
    "elo_difference_pre",
    "elo_expected_home",
    "market_overround",
    "market_probability_home",
    "market_probability_draw",
    "market_probability_away",
    "season_ppg_difference",
    "season_win_rate_difference",
    "season_goal_difference_avg",
    "form_ppg_5_difference",
    "form_ppg_10_difference",
    "form_goal_difference_5_difference",
    "form_shots_on_target_5_difference",
    "venue_ppg_5_difference",
    "days_rest_difference",
    "league_position_advantage",
]

MODEL_ID_COLUMNS = [
    "match_id",
    "season",
    "date",
    "home_team_id",
    "home_team",
    "away_team_id",
    "away_team",
    "target_ftr",
    "target_class",
    "temporal_split",
]


def _prepare_history(team_history: pd.DataFrame) -> pd.DataFrame:
    history = team_history.copy()
    history["date"] = pd.to_datetime(history["date"], errors="raise")
    history = history.sort_values(["team_id", "date", "match_id"]).reset_index(drop=True)
    history["_one"] = 1
    history["_win"] = history["team_result"].eq("W").astype(int)
    history["_draw"] = history["team_result"].eq("D").astype(int)
    history["_loss"] = history["team_result"].eq("L").astype(int)
    history["_goal_difference"] = history["goals_for"] - history["goals_against"]
    return history


def _shifted_rolling(
    frame: pd.DataFrame,
    group_columns: list[str],
    value_column: str,
    window: int,
    aggregation: str,
) -> pd.Series:
    return frame.groupby(group_columns, sort=False)[value_column].transform(
        lambda values: (
            values.shift(1)
            .rolling(window=window, min_periods=1)
            .agg(aggregation)
        )
    )


def _shifted_expanding_sum(
    frame: pd.DataFrame,
    group_columns: list[str],
    value_column: str,
) -> pd.Series:
    values = pd.to_numeric(frame[value_column], errors="coerce").fillna(0.0)
    cumulative = values.groupby(
        [frame[column] for column in group_columns],
        sort=False,
    ).cumsum()
    return cumulative - values


def _league_positions_before_match(matches: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []

    for (division, season), season_matches in matches.groupby(
        ["division", "season"],
        sort=False,
    ):
        teams = sorted(
            set(season_matches["home_team_id"])
            | set(season_matches["away_team_id"])
        )
        state = {
            team: {
                "played": 0,
                "points": 0,
                "goals_for": 0,
                "goals_against": 0,
            }
            for team in teams
        }
        season_matches = season_matches.sort_values(["date", "match_id"])

        for _, day_matches in season_matches.groupby("date", sort=True):
            total_played = sum(team_state["played"] for team_state in state.values())
            if total_played:
                ordered = sorted(
                    teams,
                    key=lambda team: (
                        -state[team]["points"],
                        -(state[team]["goals_for"] - state[team]["goals_against"]),
                        -state[team]["goals_for"],
                        team,
                    ),
                )
                positions = {team: index + 1 for index, team in enumerate(ordered)}
            else:
                positions = {team: pd.NA for team in teams}

            for row in day_matches.itertuples(index=False):
                records.extend(
                    [
                        {
                            "match_id": row.match_id,
                            "team_id": row.home_team_id,
                            "league_position_pre": positions[row.home_team_id],
                            "league_size": len(teams),
                        },
                        {
                            "match_id": row.match_id,
                            "team_id": row.away_team_id,
                            "league_position_pre": positions[row.away_team_id],
                            "league_size": len(teams),
                        },
                    ]
                )

            # All matches on the same date are applied together. This prevents
            # an arbitrary CSV row order from changing the pre-match table.
            for row in day_matches.itertuples(index=False):
                home = state[row.home_team_id]
                away = state[row.away_team_id]
                home["played"] += 1
                away["played"] += 1
                home["goals_for"] += int(row.home_goals)
                home["goals_against"] += int(row.away_goals)
                away["goals_for"] += int(row.away_goals)
                away["goals_against"] += int(row.home_goals)
                if row.result == "H":
                    home["points"] += 3
                elif row.result == "A":
                    away["points"] += 3
                else:
                    home["points"] += 1
                    away["points"] += 1

    return pd.DataFrame(records)


def compute_elo_features(
    matches: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    ratings: dict[str, float] = {}
    last_season: dict[str, str] = {}
    last_division: dict[str, str] = {}
    records: list[dict] = []

    ordered = matches.sort_values(["date", "division", "match_id"])
    for row in ordered.itertuples(index=False):
        for team_id in (row.home_team_id, row.away_team_id):
            base = DIVISION_BASE_ELO[row.division]
            if team_id not in ratings:
                ratings[team_id] = base
            elif last_season[team_id] != row.season:
                ratings[team_id] = (
                    (1.0 - ELO_SEASON_REGRESSION) * ratings[team_id]
                    + ELO_SEASON_REGRESSION * base
                )
            last_season[team_id] = row.season
            last_division[team_id] = row.division

        home_pre = ratings[row.home_team_id]
        away_pre = ratings[row.away_team_id]
        expected_home = 1.0 / (
            1.0
            + 10.0
            ** (
                (
                    away_pre
                    - (home_pre + ELO_HOME_ADVANTAGE)
                )
                / 400.0
            )
        )
        score_home = {"H": 1.0, "D": 0.5, "A": 0.0}[row.result]
        change = ELO_K * (score_home - expected_home)

        records.append(
            {
                "match_id": row.match_id,
                "home_elo_pre": home_pre,
                "away_elo_pre": away_pre,
                "elo_difference_pre": home_pre - away_pre,
                "elo_expected_home": expected_home,
            }
        )
        ratings[row.home_team_id] = home_pre + change
        ratings[row.away_team_id] = away_pre - change

    final_state = {
        team_id: {
            "elo_final": rating,
            "last_season": last_season[team_id],
            "last_division": last_division[team_id],
        }
        for team_id, rating in ratings.items()
    }
    return pd.DataFrame(records), final_state


def build_team_pre_match_features(
    matches: pd.DataFrame,
    team_history: pd.DataFrame,
) -> pd.DataFrame:
    history = _prepare_history(team_history)
    team_group = ["team_id"]
    season_group = ["team_id", "division", "season"]
    venue_group = ["team_id", "venue"]
    season_venue_group = ["team_id", "division", "season", "venue"]

    history["career_matches_pre"] = history.groupby(
        "team_id",
        sort=False,
    ).cumcount()
    history["season_matches_pre"] = history.groupby(
        season_group,
        sort=False,
    ).cumcount()
    history["venue_matches_pre"] = history.groupby(
        venue_group,
        sort=False,
    ).cumcount()
    history["season_venue_matches_pre"] = history.groupby(
        season_venue_group,
        sort=False,
    ).cumcount()

    previous_date = history.groupby("team_id", sort=False)["date"].shift(1)
    history["days_rest"] = (history["date"] - previous_date).dt.days
    history["previous_division"] = history.groupby(
        "team_id",
        sort=False,
    )["division"].shift(1)
    history["previous_season"] = history.groupby(
        "team_id",
        sort=False,
    )["season"].shift(1)
    history["division_changed"] = (
        history["previous_division"].notna()
        & history["previous_division"].ne(history["division"])
    ).astype(int)

    for window in (5, 10):
        history[f"form_matches_{window}"] = _shifted_rolling(
            history,
            team_group,
            "_one",
            window,
            "count",
        )
        for metric in ROLLING_METRICS:
            history[f"form_{ROLLING_NAMES[metric]}_{window}"] = _shifted_rolling(
                history,
                team_group,
                metric,
                window,
                "mean",
            )
        history[f"form_points_{window}"] = _shifted_rolling(
            history,
            team_group,
            "points",
            window,
            "sum",
        )

    history["venue_matches_5"] = _shifted_rolling(
        history,
        venue_group,
        "_one",
        5,
        "count",
    )
    for metric in (
        "points",
        "_win",
        "goals_for",
        "goals_against",
        "_goal_difference",
        "shots_on_target_for",
        "shots_on_target_against",
    ):
        history[f"venue_{ROLLING_NAMES[metric]}_5"] = _shifted_rolling(
            history,
            venue_group,
            metric,
            5,
            "mean",
        )

    season_sum_columns = {
        "points": "season_points_pre",
        "_win": "season_wins_pre",
        "_draw": "season_draws_pre",
        "_loss": "season_losses_pre",
        "goals_for": "season_goals_for_pre",
        "goals_against": "season_goals_against_pre",
        "shots_for": "season_shots_for_pre",
        "shots_against": "season_shots_against_pre",
        "shots_on_target_for": "season_shots_on_target_for_pre",
        "shots_on_target_against": "season_shots_on_target_against_pre",
    }
    for source, target in season_sum_columns.items():
        history[target] = _shifted_expanding_sum(history, season_group, source)

    season_games = history["season_matches_pre"].replace(0, np.nan)
    history["season_ppg_pre"] = history["season_points_pre"] / season_games
    history["season_win_rate_pre"] = history["season_wins_pre"] / season_games
    history["season_draw_rate_pre"] = history["season_draws_pre"] / season_games
    history["season_loss_rate_pre"] = history["season_losses_pre"] / season_games
    history["season_goals_for_avg_pre"] = (
        history["season_goals_for_pre"] / season_games
    )
    history["season_goals_against_avg_pre"] = (
        history["season_goals_against_pre"] / season_games
    )
    history["season_goal_difference_pre"] = (
        history["season_goals_for_pre"] - history["season_goals_against_pre"]
    )
    history["season_goal_difference_avg_pre"] = (
        history["season_goal_difference_pre"] / season_games
    )
    history["season_shots_for_avg_pre"] = (
        history["season_shots_for_pre"] / season_games
    )
    history["season_shots_against_avg_pre"] = (
        history["season_shots_against_pre"] / season_games
    )
    history["season_shots_on_target_for_avg_pre"] = (
        history["season_shots_on_target_for_pre"] / season_games
    )
    history["season_shots_on_target_against_avg_pre"] = (
        history["season_shots_on_target_against_pre"] / season_games
    )

    for source, target in (
        ("points", "season_venue_points_pre"),
        ("_win", "season_venue_wins_pre"),
        ("goals_for", "season_venue_goals_for_pre"),
        ("goals_against", "season_venue_goals_against_pre"),
    ):
        history[target] = _shifted_expanding_sum(
            history,
            season_venue_group,
            source,
        )
    season_venue_games = history["season_venue_matches_pre"].replace(0, np.nan)
    history["season_venue_ppg_pre"] = (
        history["season_venue_points_pre"] / season_venue_games
    )
    history["season_venue_win_rate_pre"] = (
        history["season_venue_wins_pre"] / season_venue_games
    )
    history["season_venue_goals_for_avg_pre"] = (
        history["season_venue_goals_for_pre"] / season_venue_games
    )
    history["season_venue_goals_against_avg_pre"] = (
        history["season_venue_goals_against_pre"] / season_venue_games
    )

    positions = _league_positions_before_match(matches)
    history = history.merge(
        positions,
        on=["match_id", "team_id"],
        how="left",
        validate="one_to_one",
    )

    identity = [
        "match_id",
        "season",
        "division",
        "date",
        "team_id",
        "team",
        "opponent_id",
        "opponent",
        "venue",
    ]
    excluded = {
        "team_result",
        "points",
        "goals_for",
        "goals_against",
        "shots_for",
        "shots_against",
        "shots_on_target_for",
        "shots_on_target_against",
        "corners_for",
        "corners_against",
        "yellow_cards_for",
        "yellow_cards_against",
        "red_cards_for",
        "red_cards_against",
        "_one",
        "_win",
        "_draw",
        "_loss",
        "_goal_difference",
    }
    feature_columns = [
        column
        for column in history.columns
        if column not in identity and column not in excluded
    ]
    return history[identity + feature_columns]


def _market_probabilities(features: pd.DataFrame) -> pd.DataFrame:
    result = features.copy()
    avg_complete = result[
        ["odds_avg_home", "odds_avg_draw", "odds_avg_away"]
    ].gt(1.0).all(axis=1)
    b365_complete = result[
        ["odds_b365_home", "odds_b365_draw", "odds_b365_away"]
    ].gt(1.0).all(axis=1)

    result["market_source"] = pd.Series(pd.NA, index=result.index, dtype="string")
    result.loc[avg_complete, "market_source"] = "average"
    result.loc[~avg_complete & b365_complete, "market_source"] = "bet365"

    for outcome in ("home", "draw", "away"):
        result[f"market_odds_{outcome}"] = result[f"odds_avg_{outcome}"].where(
            avg_complete,
            result[f"odds_b365_{outcome}"].where(b365_complete),
        )
        result[f"market_raw_probability_{outcome}"] = (
            1.0 / result[f"market_odds_{outcome}"]
        )

    raw_columns = [
        "market_raw_probability_home",
        "market_raw_probability_draw",
        "market_raw_probability_away",
    ]
    result["market_overround"] = result[raw_columns].sum(axis=1, min_count=3)
    for outcome in ("home", "draw", "away"):
        result[f"market_probability_{outcome}"] = (
            result[f"market_raw_probability_{outcome}"]
            / result["market_overround"]
        )
    return result


def _prefix_team_features(
    team_features: pd.DataFrame,
    venue: str,
    prefix: str,
) -> pd.DataFrame:
    selected = team_features[team_features["venue"] == venue].copy()
    identifiers = {
        "match_id",
        "season",
        "division",
        "date",
        "team_id",
        "team",
        "opponent_id",
        "opponent",
        "venue",
    }
    feature_columns = [
        column for column in selected.columns if column not in identifiers
    ]
    selected = selected[["match_id", *feature_columns]]
    return selected.rename(
        columns={column: f"{prefix}_{column}" for column in feature_columns}
    )


def _promotion_context(
    features: pd.DataFrame,
    promotions: pd.DataFrame,
) -> pd.DataFrame:
    result = features.copy()
    lookup = promotions[
        ["team_id", "laliga_season", "promotion_type", "segunda_position"]
    ].rename(columns={"laliga_season": "season"})

    for side in ("home", "away"):
        side_lookup = lookup.rename(
            columns={
                "team_id": f"{side}_team_id",
                "promotion_type": f"{side}_promotion_type",
                "segunda_position": f"{side}_segunda_position",
            }
        )
        result = result.merge(
            side_lookup,
            on=[f"{side}_team_id", "season"],
            how="left",
            validate="many_to_one",
        )
        result[f"{side}_promoted"] = (
            result[f"{side}_promotion_type"].notna()
            & result["division"].eq("SP1")
        ).astype(int)
    return result


def build_match_features(
    matches: pd.DataFrame,
    team_history: pd.DataFrame,
    promotions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict]]:
    ordered_matches = matches.copy()
    ordered_matches["date"] = pd.to_datetime(ordered_matches["date"], errors="raise")
    ordered_matches = ordered_matches.sort_values(
        ["date", "division", "match_id"]
    ).reset_index(drop=True)

    team_features = build_team_pre_match_features(
        ordered_matches,
        team_history,
    )
    home = _prefix_team_features(team_features, "home", "home")
    away = _prefix_team_features(team_features, "away", "away")
    elo, elo_state = compute_elo_features(ordered_matches)

    base_columns = [
        "match_id",
        "season",
        "division",
        "date",
        "home_team_id",
        "home_team",
        "away_team_id",
        "away_team",
        "result",
        "odds_b365_home",
        "odds_b365_draw",
        "odds_b365_away",
        "odds_avg_home",
        "odds_avg_draw",
        "odds_avg_away",
        "odds_max_home",
        "odds_max_draw",
        "odds_max_away",
    ]
    features = ordered_matches[base_columns].rename(
        columns={"result": "target_ftr"}
    )
    features["target_class"] = features["target_ftr"].map(TARGET_CLASS).astype(int)
    features = features.merge(home, on="match_id", how="left", validate="one_to_one")
    features = features.merge(away, on="match_id", how="left", validate="one_to_one")
    features = features.merge(elo, on="match_id", how="left", validate="one_to_one")
    features = _promotion_context(features, promotions)
    features = _market_probabilities(features)

    split_map = {
        **{season: "train" for season in (
            "2016/17",
            "2017/18",
            "2018/19",
            "2019/20",
            "2020/21",
            "2021/22",
            "2022/23",
        )},
        "2023/24": "validation",
        "2024/25": "validation",
        "2025/26": "test",
    }
    features["temporal_split"] = features["season"].map(split_map)
    features["history_ready_5"] = (
        features["home_form_matches_5"].ge(5)
        & features["away_form_matches_5"].ge(5)
    ).astype(int)
    features["history_ready_10"] = (
        features["home_form_matches_10"].ge(10)
        & features["away_form_matches_10"].ge(10)
    ).astype(int)

    difference_pairs = {
        "season_ppg_pre": "season_ppg_difference",
        "season_win_rate_pre": "season_win_rate_difference",
        "season_goal_difference_avg_pre": "season_goal_difference_avg",
        "form_ppg_5": "form_ppg_5_difference",
        "form_ppg_10": "form_ppg_10_difference",
        "form_goals_for_avg_5": "form_goals_for_5_difference",
        "form_goals_against_avg_5": "form_goals_against_5_difference",
        "form_goal_difference_avg_5": "form_goal_difference_5_difference",
        "form_shots_on_target_for_avg_5": "form_shots_on_target_5_difference",
        "venue_ppg_5": "venue_ppg_5_difference",
        "venue_win_rate_5": "venue_win_rate_5_difference",
        "days_rest": "days_rest_difference",
    }
    for source, output in difference_pairs.items():
        features[output] = features[f"home_{source}"] - features[f"away_{source}"]
    features["league_position_advantage"] = (
        features["away_league_position_pre"]
        - features["home_league_position_pre"]
    )

    leading = [
        "match_id",
        "season",
        "division",
        "date",
        "home_team_id",
        "home_team",
        "away_team_id",
        "away_team",
        "target_ftr",
        "target_class",
        "temporal_split",
        "home_promoted",
        "away_promoted",
        "home_promotion_type",
        "away_promotion_type",
        "history_ready_5",
        "history_ready_10",
    ]
    remaining = [column for column in features.columns if column not in leading]
    features = features[leading + remaining]
    return features, team_features, elo_state


def _final_table_for_season(matches: pd.DataFrame) -> pd.DataFrame:
    home = matches[
        ["home_team_id", "home_goals", "away_goals", "result"]
    ].rename(
        columns={
            "home_team_id": "team_id",
            "home_goals": "goals_for",
            "away_goals": "goals_against",
        }
    )
    home["points"] = home["result"].map({"H": 3, "D": 1, "A": 0})
    away = matches[
        ["away_team_id", "away_goals", "home_goals", "result"]
    ].rename(
        columns={
            "away_team_id": "team_id",
            "away_goals": "goals_for",
            "home_goals": "goals_against",
        }
    )
    away["points"] = away["result"].map({"H": 0, "D": 1, "A": 3})
    long = pd.concat([home, away], ignore_index=True)
    table = long.groupby("team_id", as_index=False).agg(
        played=("team_id", "size"),
        points=("points", "sum"),
        goals_for=("goals_for", "sum"),
        goals_against=("goals_against", "sum"),
    )
    table["goal_difference"] = table["goals_for"] - table["goals_against"]
    table = table.sort_values(
        ["points", "goal_difference", "goals_for", "team_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    table["position"] = np.arange(1, len(table) + 1)
    return table


def _mean_last(rows: pd.DataFrame, column: str, window: int) -> float:
    values = pd.to_numeric(rows[column], errors="coerce").tail(window)
    return float(values.mean()) if values.notna().any() else np.nan


def build_preseason_state(
    matches: pd.DataFrame,
    team_history: pd.DataFrame,
    fixtures: pd.DataFrame,
    promotions: pd.DataFrame,
    elo_state: dict[str, dict],
) -> pd.DataFrame:
    history = _prepare_history(team_history)
    fixture_teams = sorted(
        set(fixtures["home_team_id"]) | set(fixtures["away_team_id"])
    )
    snapshot_date = pd.to_datetime(fixtures["reference_date"]).min()
    promoted_lookup = promotions[
        promotions["laliga_season"].eq("2026/27")
    ].set_index("team_id")
    records: list[dict] = []

    for team_id in fixture_teams:
        rows = history[history["team_id"].eq(team_id)].sort_values(
            ["date", "match_id"]
        )
        if rows.empty:
            raise ValueError(f"No historical rows available for {team_id}")
        last = rows.iloc[-1]
        season_matches = matches[
            matches["season"].eq(last["season"])
            & matches["division"].eq(last["division"])
        ]
        table = _final_table_for_season(season_matches).set_index("team_id")
        table_row = table.loc[team_id]
        promoted = team_id in promoted_lookup.index
        promotion_type = (
            promoted_lookup.loc[team_id, "promotion_type"]
            if promoted
            else pd.NA
        )
        second_position = (
            promoted_lookup.loc[team_id, "segunda_position"]
            if promoted
            else pd.NA
        )
        final_elo = float(elo_state[team_id]["elo_final"])
        initial_elo = (
            (1.0 - ELO_SEASON_REGRESSION) * final_elo
            + ELO_SEASON_REGRESSION * DIVISION_BASE_ELO["SP1"]
        )
        home_rows = rows[rows["venue"].eq("home")]
        away_rows = rows[rows["venue"].eq("away")]

        record = {
            "team_id": team_id,
            "team": TEAM_NAMES[team_id],
            "target_season": "2026/27",
            "snapshot_date": snapshot_date.date().isoformat(),
            "promoted": int(promoted),
            "promotion_type": promotion_type,
            "segunda_position": second_position,
            "previous_division": last["division"],
            "previous_season": last["season"],
            "previous_position": int(table_row["position"]),
            "previous_played": int(table_row["played"]),
            "previous_points": int(table_row["points"]),
            "previous_ppg": float(table_row["points"] / table_row["played"]),
            "previous_goals_for": int(table_row["goals_for"]),
            "previous_goals_against": int(table_row["goals_against"]),
            "previous_goal_difference": int(table_row["goal_difference"]),
            "previous_goals_for_avg": float(
                table_row["goals_for"] / table_row["played"]
            ),
            "previous_goals_against_avg": float(
                table_row["goals_against"] / table_row["played"]
            ),
            "last_match_date": last["date"].date().isoformat(),
            "days_since_last_match_at_snapshot": int(
                (snapshot_date - last["date"]).days
            ),
            "elo_end_2025_26": final_elo,
            "elo_initial_2026_27": initial_elo,
        }
        for window in (5, 10):
            record[f"form_matches_{window}"] = min(window, len(rows))
            record[f"form_ppg_{window}"] = _mean_last(rows, "points", window)
            record[f"form_win_rate_{window}"] = float(
                rows["team_result"].tail(window).eq("W").mean()
            )
            record[f"form_goals_for_avg_{window}"] = _mean_last(
                rows,
                "goals_for",
                window,
            )
            record[f"form_goals_against_avg_{window}"] = _mean_last(
                rows,
                "goals_against",
                window,
            )
            record[f"form_shots_on_target_for_avg_{window}"] = _mean_last(
                rows,
                "shots_on_target_for",
                window,
            )
        record["home_ppg_last_5_home_matches"] = _mean_last(
            home_rows,
            "points",
            5,
        )
        record["away_ppg_last_5_away_matches"] = _mean_last(
            away_rows,
            "points",
            5,
        )
        records.append(record)

    return pd.DataFrame(records).sort_values(
        ["promoted", "elo_initial_2026_27", "team_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)


def build_fixture_seed_features(
    fixtures: pd.DataFrame,
    preseason_state: pd.DataFrame,
) -> pd.DataFrame:
    home = preseason_state.add_prefix("home_").rename(
        columns={"home_team_id": "home_team_id"}
    )
    away = preseason_state.add_prefix("away_").rename(
        columns={"away_team_id": "away_team_id"}
    )
    result = fixtures.merge(
        home,
        on="home_team_id",
        how="left",
        validate="many_to_one",
    ).merge(
        away,
        on="away_team_id",
        how="left",
        validate="many_to_one",
    )
    result["elo_difference_preseason"] = (
        result["home_elo_initial_2026_27"]
        - result["away_elo_initial_2026_27"]
    )
    result["form_ppg_5_difference_preseason"] = (
        result["home_form_ppg_5"] - result["away_form_ppg_5"]
    )
    result["previous_ppg_difference"] = (
        result["home_previous_ppg"] - result["away_previous_ppg"]
    )
    result["feature_snapshot_type"] = "preseason_static"
    result["requires_dynamic_update"] = result["matchday"].gt(1).astype(int)
    return result


def build_feature_manifest(features: pd.DataFrame) -> pd.DataFrame:
    identifier_columns = {
        "match_id",
        "season",
        "division",
        "date",
        "home_team_id",
        "home_team",
        "away_team_id",
        "away_team",
        "temporal_split",
    }
    target_columns = {"target_ftr", "target_class"}
    context_columns = {
        "home_promotion_type",
        "away_promotion_type",
        "market_source",
    }
    records: list[dict] = []

    for column in features.columns:
        if column in identifier_columns:
            role = "identifier"
        elif column in target_columns:
            role = "target"
        elif column in context_columns:
            role = "context"
        else:
            role = "feature"

        if column.startswith("odds_") or column.startswith("market_"):
            group = "market"
        elif "elo" in column:
            group = "elo"
        elif "promot" in column or "segunda" in column or "division" in column:
            group = "promotion_context"
        elif "form_" in column:
            group = "recent_form"
        elif "season_" in column or "league_position" in column:
            group = "season_to_date"
        elif "venue_" in column:
            group = "venue_form"
        elif "rest" in column:
            group = "rest"
        else:
            group = "identity_or_control"

        records.append(
            {
                "column": column,
                "role": role,
                "feature_group": group,
                "dtype": str(features[column].dtype),
                "missing_count": int(features[column].isna().sum()),
                "missing_rate": float(features[column].isna().mean()),
                "available_before_kickoff": role != "target",
                "recommended_baseline": column in CORE_MODEL_FEATURES,
            }
        )
    return pd.DataFrame(records)


def run_quality_checks(
    features: pd.DataFrame,
    team_features: pd.DataFrame,
    preseason_state: pd.DataFrame,
    fixture_features: pd.DataFrame,
) -> pd.DataFrame:
    probability_columns = [
        "market_probability_home",
        "market_probability_draw",
        "market_probability_away",
    ]
    probability_rows = features[probability_columns].notna().all(axis=1)
    probability_sums = features.loc[probability_rows, probability_columns].sum(axis=1)

    checks = {
        "unique_match_ids": features["match_id"].is_unique,
        "two_team_feature_rows_per_match": team_features.groupby(
            "match_id"
        ).size().eq(2).all(),
        "valid_targets": features["target_ftr"].isin(TARGET_CLASS).all(),
        "valid_target_classes": features["target_class"].isin({0, 1, 2}).all(),
        "elo_complete": features[
            ["home_elo_pre", "away_elo_pre", "elo_difference_pre"]
        ].notna().all().all(),
        "market_probabilities_sum_to_one": np.allclose(
            probability_sums,
            1.0,
            atol=1e-10,
        ),
        "no_negative_history_counts": features[
            [
                "home_career_matches_pre",
                "away_career_matches_pre",
                "home_season_matches_pre",
                "away_season_matches_pre",
            ]
        ].ge(0).all().all(),
        "first_team_rows_have_zero_prior_matches": team_features.sort_values(
            ["team_id", "date", "match_id"]
        ).groupby("team_id").head(1)["career_matches_pre"].eq(0).all(),
        "preseason_has_20_teams": len(preseason_state) == 20,
        "preseason_team_ids_unique": preseason_state["team_id"].is_unique,
        "fixture_seed_has_380_rows": len(fixture_features) == 380,
        "fixture_seed_ids_unique": fixture_features["fixture_id"].is_unique,
        "promoted_2026_27_count": preseason_state["promoted"].sum() == 3,
    }
    return pd.DataFrame(
        [
            {
                "check": name,
                "status": "PASS" if bool(passed) else "FAIL",
            }
            for name, passed in checks.items()
        ]
    )


def _count_model_features(manifest: pd.DataFrame) -> int:
    return int(manifest["role"].eq("feature").sum())


def run_phase2() -> dict:
    from .pipeline import build_team_match_history

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    matches = load_historical_matches()
    fixtures = load_fixtures()
    promotions = build_promotions(matches, fixtures)
    team_history = build_team_match_history(matches)
    features, team_features, elo_state = build_match_features(
        matches,
        team_history,
        promotions,
    )
    laliga_features = features[features["division"].eq("SP1")].reset_index(drop=True)
    missing_core = sorted(set(CORE_MODEL_FEATURES) - set(laliga_features.columns))
    if missing_core:
        raise ValueError(f"Missing core model features: {missing_core}")
    model_dataset = laliga_features[
        MODEL_ID_COLUMNS + CORE_MODEL_FEATURES
    ].copy()
    preseason_state = build_preseason_state(
        matches,
        team_history,
        fixtures,
        promotions,
        elo_state,
    )
    fixture_features = build_fixture_seed_features(fixtures, preseason_state)
    manifest = build_feature_manifest(laliga_features)
    quality = run_quality_checks(
        features,
        team_features,
        preseason_state,
        fixture_features,
    )
    missingness = manifest[
        ["column", "role", "feature_group", "missing_count", "missing_rate"]
    ].sort_values(["missing_rate", "column"], ascending=[False, True])

    if quality["status"].ne("PASS").any():
        failed = quality.loc[quality["status"].ne("PASS"), "check"].tolist()
        raise ValueError(f"Phase 2 quality checks failed: {failed}")

    write_csv(features, PROCESSED_DIR / "all_match_features.csv")
    write_csv(laliga_features, PROCESSED_DIR / "laliga_match_features.csv")
    write_csv(model_dataset, PROCESSED_DIR / "laliga_model_dataset.csv")
    write_csv(team_features, PROCESSED_DIR / "team_pre_match_features.csv")
    write_csv(preseason_state, PROCESSED_DIR / "team_preseason_state_2026_27.csv")
    write_csv(
        fixture_features,
        PROCESSED_DIR / "fixtures_2026_27_preseason_features.csv",
    )
    write_csv(manifest, REPORTS_DIR / "feature_manifest.csv")
    write_csv(missingness, REPORTS_DIR / "feature_missingness.csv")
    write_csv(quality, REPORTS_DIR / "phase2_quality_checks.csv")

    summary = {
        "quality_passed": bool(quality["status"].eq("PASS").all()),
        "historical_matches_with_features": int(len(features)),
        "laliga_matches_with_features": int(len(laliga_features)),
        "team_pre_match_rows": int(len(team_features)),
        "model_feature_columns": _count_model_features(manifest),
        "recommended_model_features": int(len(CORE_MODEL_FEATURES)),
        "laliga_train_rows": int(
            laliga_features["temporal_split"].eq("train").sum()
        ),
        "laliga_validation_rows": int(
            laliga_features["temporal_split"].eq("validation").sum()
        ),
        "laliga_test_rows": int(
            laliga_features["temporal_split"].eq("test").sum()
        ),
        "history_ready_5_rows": int(laliga_features["history_ready_5"].sum()),
        "history_ready_10_rows": int(laliga_features["history_ready_10"].sum()),
        "market_probability_rows": int(
            laliga_features[
                [
                    "market_probability_home",
                    "market_probability_draw",
                    "market_probability_away",
                ]
            ].notna().all(axis=1).sum()
        ),
        "preseason_teams": int(len(preseason_state)),
        "promoted_preseason_teams": preseason_state.loc[
            preseason_state["promoted"].eq(1),
            "team",
        ].tolist(),
        "fixture_seed_rows": int(len(fixture_features)),
        "elo_parameters": {
            "sp1_base": DIVISION_BASE_ELO["SP1"],
            "sp2_base": DIVISION_BASE_ELO["SP2"],
            "k": ELO_K,
            "home_advantage": ELO_HOME_ADVANTAGE,
            "season_regression": ELO_SEASON_REGRESSION,
        },
        "outputs": {
            "all_match_features": "data/processed/all_match_features.csv",
            "laliga_match_features": "data/processed/laliga_match_features.csv",
            "laliga_model_dataset": "data/processed/laliga_model_dataset.csv",
            "team_pre_match_features": "data/processed/team_pre_match_features.csv",
            "team_preseason_state": (
                "data/processed/team_preseason_state_2026_27.csv"
            ),
            "fixture_preseason_features": (
                "data/processed/fixtures_2026_27_preseason_features.csv"
            ),
            "feature_manifest": "reports/feature_manifest.csv",
            "feature_missingness": "reports/feature_missingness.csv",
            "quality_checks": "reports/phase2_quality_checks.csv",
        },
    }
    (REPORTS_DIR / "phase2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
