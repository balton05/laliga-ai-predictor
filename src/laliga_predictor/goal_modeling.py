from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

from .config import PROCESSED_DIR, REPORTS_DIR
from .modeling import (
    CLASS_IDS,
    CLASS_LABELS,
    TEST_SEASON,
    VALIDATION_SEASONS,
    evaluate_probabilities,
)


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


HALF_LIFE_CANDIDATES: tuple[float | None, ...] = (365.0, 730.0, 1460.0, None)
MAX_GOALS = 10
L2_STRENGTH = 0.02
GOAL_MODELS = ("poisson", "dixon_coles")
PROBABILITY_COLUMNS = [
    "probability_home",
    "probability_draw",
    "probability_away",
]


def _half_life_label(value: float | None) -> str:
    return "none" if value is None else str(int(value))


def _time_weights(
    dates: pd.Series,
    reference_date: pd.Timestamp,
    half_life_days: float | None,
) -> np.ndarray:
    if half_life_days is None:
        return np.ones(len(dates), dtype=float)
    age = (reference_date - pd.to_datetime(dates)).dt.days.clip(lower=0)
    weights = np.exp(-np.log(2.0) * age.to_numpy(dtype=float) / half_life_days)
    return weights / weights.mean()


def _dixon_coles_tau(
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    expected_home: np.ndarray,
    expected_away: np.ndarray,
    rho: float,
) -> np.ndarray:
    tau = np.ones(len(home_goals), dtype=float)
    zero_zero = (home_goals == 0) & (away_goals == 0)
    zero_one = (home_goals == 0) & (away_goals == 1)
    one_zero = (home_goals == 1) & (away_goals == 0)
    one_one = (home_goals == 1) & (away_goals == 1)
    tau[zero_zero] = 1.0 - expected_home[zero_zero] * expected_away[zero_zero] * rho
    tau[zero_one] = 1.0 + expected_home[zero_one] * rho
    tau[one_zero] = 1.0 + expected_away[one_zero] * rho
    tau[one_one] = 1.0 - rho
    return tau


@dataclass
class GoalStrengthModel:
    model_name: str
    teams: list[str]
    intercept: float
    home_advantage: float
    attack: np.ndarray
    defense: np.ndarray
    rho: float
    half_life_days: float | None
    fitted_through: str
    optimization_success: bool
    optimization_iterations: int
    objective_value: float

    def _team_effect(
        self,
        team: str,
        values: np.ndarray,
        overrides: dict[str, tuple[float, float]] | None,
        effect_index: int,
    ) -> float:
        if overrides and team in overrides:
            return float(overrides[team][effect_index])
        mapping = {name: index for index, name in enumerate(self.teams)}
        return float(values[mapping[team]]) if team in mapping else 0.0

    def expected_goals(
        self,
        home_team: str,
        away_team: str,
        overrides: dict[str, tuple[float, float]] | None = None,
    ) -> tuple[float, float]:
        home_attack = self._team_effect(home_team, self.attack, overrides, 0)
        away_attack = self._team_effect(away_team, self.attack, overrides, 0)
        home_defense = self._team_effect(home_team, self.defense, overrides, 1)
        away_defense = self._team_effect(away_team, self.defense, overrides, 1)
        expected_home = np.exp(
            self.intercept + self.home_advantage + home_attack + away_defense
        )
        expected_away = np.exp(self.intercept + away_attack + home_defense)
        return float(expected_home), float(expected_away)

    def score_matrix(
        self,
        home_team: str,
        away_team: str,
        overrides: dict[str, tuple[float, float]] | None = None,
        max_goals: int = MAX_GOALS,
    ) -> tuple[np.ndarray, float, float]:
        expected_home, expected_away = self.expected_goals(
            home_team,
            away_team,
            overrides,
        )
        goals = np.arange(max_goals + 1)
        matrix = np.outer(
            poisson.pmf(goals, expected_home),
            poisson.pmf(goals, expected_away),
        )
        if self.model_name == "dixon_coles":
            matrix[0, 0] *= 1.0 - expected_home * expected_away * self.rho
            matrix[0, 1] *= 1.0 + expected_home * self.rho
            matrix[1, 0] *= 1.0 + expected_away * self.rho
            matrix[1, 1] *= 1.0 - self.rho
        matrix = np.clip(matrix, 0.0, None)
        matrix /= matrix.sum()
        return matrix, expected_home, expected_away


def _fit_goal_model(
    matches: pd.DataFrame,
    model_name: str,
    half_life_days: float | None,
    fitted_through: str,
) -> GoalStrengthModel:
    if model_name not in GOAL_MODELS:
        raise ValueError(f"Unknown goal model: {model_name}")
    data = matches.sort_values(["date", "match_id"]).copy()
    teams = sorted(set(data["home_team_id"]) | set(data["away_team_id"]))
    team_index = {team: index for index, team in enumerate(teams)}
    home_index = data["home_team_id"].map(team_index).to_numpy(dtype=int)
    away_index = data["away_team_id"].map(team_index).to_numpy(dtype=int)
    home_goals = data["home_goals"].to_numpy(dtype=int)
    away_goals = data["away_goals"].to_numpy(dtype=int)
    reference_date = pd.to_datetime(data["date"]).max() + pd.Timedelta(days=1)
    weights = _time_weights(data["date"], reference_date, half_life_days)
    team_count = len(teams)

    away_mean = max(float(away_goals.mean()), 0.20)
    home_mean = max(float(home_goals.mean()), 0.20)
    initial = np.zeros(2 + 2 * team_count + (1 if model_name == "dixon_coles" else 0))
    initial[0] = np.log(away_mean)
    initial[1] = np.log(home_mean / away_mean)
    if model_name == "dixon_coles":
        initial[-1] = -0.05

    bounds = [(-1.5, 1.5), (-0.5, 1.0)]
    bounds += [(-1.5, 1.5)] * (2 * team_count)
    if model_name == "dixon_coles":
        bounds += [(-0.20, 0.15)]

    def unpack(parameters: np.ndarray) -> tuple[float, float, np.ndarray, np.ndarray, float]:
        intercept = float(parameters[0])
        home_advantage = float(parameters[1])
        attack_raw = parameters[2 : 2 + team_count]
        defense_raw = parameters[2 + team_count : 2 + 2 * team_count]
        attack = attack_raw - attack_raw.mean()
        defense = defense_raw - defense_raw.mean()
        rho = float(parameters[-1]) if model_name == "dixon_coles" else 0.0
        return intercept, home_advantage, attack, defense, rho

    def objective(parameters: np.ndarray) -> float:
        intercept, home_advantage, attack, defense, rho = unpack(parameters)
        log_home = np.clip(
            intercept + home_advantage + attack[home_index] + defense[away_index],
            -3.0,
            3.0,
        )
        log_away = np.clip(
            intercept + attack[away_index] + defense[home_index],
            -3.0,
            3.0,
        )
        expected_home = np.exp(log_home)
        expected_away = np.exp(log_away)
        log_likelihood = (
            home_goals * log_home
            - expected_home
            - gammaln(home_goals + 1)
            + away_goals * log_away
            - expected_away
            - gammaln(away_goals + 1)
        )
        if model_name == "dixon_coles":
            tau = _dixon_coles_tau(
                home_goals,
                away_goals,
                expected_home,
                expected_away,
                rho,
            )
            if (tau <= 1e-10).any() or not np.isfinite(tau).all():
                return 1e8
            log_likelihood += np.log(tau)
        regularization = L2_STRENGTH * (
            np.mean(attack**2) + np.mean(defense**2)
        )
        return float(-(weights * log_likelihood).mean() + regularization)

    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 700, "ftol": 1e-10, "maxls": 50},
    )
    intercept, home_advantage, attack, defense, rho = unpack(result.x)
    return GoalStrengthModel(
        model_name=model_name,
        teams=teams,
        intercept=intercept,
        home_advantage=home_advantage,
        attack=attack,
        defense=defense,
        rho=rho,
        half_life_days=half_life_days,
        fitted_through=fitted_through,
        optimization_success=bool(result.success),
        optimization_iterations=int(result.nit),
        objective_value=float(result.fun),
    )


def _top_scorelines(matrix: np.ndarray, count: int = 3) -> list[tuple[int, int, float]]:
    order = np.argsort(matrix.ravel())[::-1][:count]
    return [
        (
            int(index // matrix.shape[1]),
            int(index % matrix.shape[1]),
            float(matrix.ravel()[index]),
        )
        for index in order
    ]


def _predict_matches(
    model: GoalStrengthModel,
    matches: pd.DataFrame,
    split: str,
    overrides: dict[str, tuple[float, float]] | None = None,
) -> pd.DataFrame:
    records: list[dict] = []
    for row in matches.itertuples(index=False):
        matrix, expected_home, expected_away = model.score_matrix(
            row.home_team_id,
            row.away_team_id,
            overrides,
        )
        probability_home = float(np.tril(matrix, -1).sum())
        probability_draw = float(np.trace(matrix))
        probability_away = float(np.triu(matrix, 1).sum())
        probabilities = np.array(
            [probability_home, probability_draw, probability_away],
            dtype=float,
        )
        probabilities /= probabilities.sum()
        top = _top_scorelines(matrix)
        predicted_class = int(probabilities.argmax())
        actual_score_probability = (
            float(matrix[int(row.home_goals), int(row.away_goals)])
            if row.home_goals <= MAX_GOALS and row.away_goals <= MAX_GOALS
            else np.nan
        )
        records.append(
            {
                "model": model.model_name,
                "split": split,
                "match_id": row.match_id,
                "season": row.season,
                "date": row.date,
                "home_team_id": row.home_team_id,
                "home_team": row.home_team,
                "away_team_id": row.away_team_id,
                "away_team": row.away_team,
                "home_goals": int(row.home_goals),
                "away_goals": int(row.away_goals),
                "target_ftr": row.result,
                "target_class": CLASS_LABELS.index(row.result),
                "expected_home_goals": expected_home,
                "expected_away_goals": expected_away,
                "probability_home": probabilities[0],
                "probability_draw": probabilities[1],
                "probability_away": probabilities[2],
                "predicted_class": predicted_class,
                "predicted_ftr": CLASS_LABELS[predicted_class],
                "predicted_score": f"{top[0][0]}-{top[0][1]}",
                "predicted_score_probability": top[0][2],
                "top_2_score": f"{top[1][0]}-{top[1][1]}",
                "top_2_score_probability": top[1][2],
                "top_3_score": f"{top[2][0]}-{top[2][1]}",
                "top_3_score_probability": top[2][2],
                "actual_score_probability": actual_score_probability,
                "row_log_loss": -np.log(
                    max(probabilities[CLASS_LABELS.index(row.result)], 1e-12)
                ),
            }
        )
    return pd.DataFrame(records)


def _goal_metrics(rows: pd.DataFrame) -> dict[str, float]:
    result_metrics = evaluate_probabilities(
        rows["target_class"],
        rows[PROBABILITY_COLUMNS].to_numpy(dtype=float),
    )
    home_error = rows["expected_home_goals"] - rows["home_goals"]
    away_error = rows["expected_away_goals"] - rows["away_goals"]
    actual_total = rows["home_goals"] + rows["away_goals"]
    expected_total = rows["expected_home_goals"] + rows["expected_away_goals"]
    exact_score = rows["predicted_score"].eq(
        rows["home_goals"].astype(str) + "-" + rows["away_goals"].astype(str)
    )
    score_probability = rows["actual_score_probability"].clip(lower=1e-12)
    return {
        **result_metrics,
        "goal_mae": float(
            (home_error.abs().mean() + away_error.abs().mean()) / 2.0
        ),
        "goal_rmse": float(
            np.sqrt(
                (
                    np.square(home_error).mean()
                    + np.square(away_error).mean()
                )
                / 2.0
            )
        ),
        "total_goals_mae": float((expected_total - actual_total).abs().mean()),
        "exact_score_accuracy": float(exact_score.mean()),
        "score_log_loss": float(-np.log(score_probability).mean()),
    }


def _walk_forward(
    matches: pd.DataFrame,
    model_name: str,
    half_life_days: float | None,
) -> tuple[pd.DataFrame, list[GoalStrengthModel]]:
    pieces: list[pd.DataFrame] = []
    fitted_models: list[GoalStrengthModel] = []
    for season in VALIDATION_SEASONS:
        evaluation = matches[matches["season"].eq(season)].copy()
        train = matches[
            pd.to_datetime(matches["date"]).lt(pd.to_datetime(evaluation["date"]).min())
        ].copy()
        fitted_through = str(train.sort_values("date").iloc[-1]["season"])
        model = _fit_goal_model(
            train,
            model_name,
            half_life_days,
            fitted_through,
        )
        fitted_models.append(model)
        pieces.append(_predict_matches(model, evaluation, "validation"))
    return pd.concat(pieces, ignore_index=True), fitted_models


def _candidate_search(
    matches: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float | None], dict[str, pd.DataFrame]]:
    records: list[dict] = []
    selected: dict[str, float | None] = {}
    selected_predictions: dict[str, pd.DataFrame] = {}
    for model_name in GOAL_MODELS:
        predictions_by_candidate: dict[str, pd.DataFrame] = {}
        for half_life in HALF_LIFE_CANDIDATES:
            predictions, fitted = _walk_forward(matches, model_name, half_life)
            label = _half_life_label(half_life)
            predictions_by_candidate[label] = predictions
            for season, rows in predictions.groupby("season", sort=True):
                records.append(
                    {
                        "model": model_name,
                        "half_life_days": label,
                        "fold": season,
                        "train_end_season": (
                            "2022/23" if season == "2023/24" else "2023/24"
                        ),
                        "rows": len(rows),
                        "rho": fitted[0 if season == "2023/24" else 1].rho,
                        "optimization_success": fitted[
                            0 if season == "2023/24" else 1
                        ].optimization_success,
                        **_goal_metrics(rows),
                    }
                )
            records.append(
                {
                    "model": model_name,
                    "half_life_days": label,
                    "fold": "COMBINED",
                    "train_end_season": "walk_forward",
                    "rows": len(predictions),
                    "rho": float(np.mean([item.rho for item in fitted])),
                    "optimization_success": all(
                        item.optimization_success for item in fitted
                    ),
                    **_goal_metrics(predictions),
                }
            )
        candidates = pd.DataFrame(records)
        best = candidates[
            candidates["model"].eq(model_name)
            & candidates["fold"].eq("COMBINED")
        ].sort_values(
            ["log_loss", "brier_score", "score_log_loss"],
            ascending=True,
        ).iloc[0]
        best_label = str(best["half_life_days"])
        selected[model_name] = None if best_label == "none" else float(best_label)
        selected_predictions[model_name] = predictions_by_candidate[best_label]
    return pd.DataFrame(records), selected, selected_predictions


def _evaluate_test(
    matches: pd.DataFrame,
    selected: dict[str, float | None],
) -> tuple[pd.DataFrame, dict[str, GoalStrengthModel]]:
    test = matches[matches["season"].eq(TEST_SEASON)].copy()
    train = matches[
        pd.to_datetime(matches["date"]).lt(pd.to_datetime(test["date"]).min())
    ].copy()
    pieces: list[pd.DataFrame] = []
    fitted: dict[str, GoalStrengthModel] = {}
    for model_name in GOAL_MODELS:
        model = _fit_goal_model(
            train,
            model_name,
            selected[model_name],
            "2024/25",
        )
        fitted[model_name] = model
        pieces.append(_predict_matches(model, test, "test"))
    return pd.concat(pieces, ignore_index=True), fitted


def _metrics_table(
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict] = []
    predictions = pd.concat([validation, test], ignore_index=True)
    for (split, model), rows in predictions.groupby(["split", "model"], sort=True):
        records.append(
            {
                "split": split,
                "model": model,
                "rows": len(rows),
                **_goal_metrics(rows),
            }
        )
    return pd.DataFrame(records).sort_values(
        ["split", "log_loss", "brier_score"]
    ).reset_index(drop=True)


def _baseline_comparison(goal_metrics: pd.DataFrame) -> pd.DataFrame:
    phase4 = pd.read_csv(REPORTS_DIR / "model_metrics.csv")
    keep = phase4["model"].isin(
        ["market", "logistic_sports", "logistic_market", "elo_multinomial"]
    )
    baseline = phase4.loc[
        keep,
        [
            "split",
            "model",
            "rows",
            "log_loss",
            "brier_score",
            "accuracy",
            "macro_f1",
            "ece_10_bins",
        ],
    ].copy()
    goal = goal_metrics[
        [
            "split",
            "model",
            "rows",
            "log_loss",
            "brier_score",
            "accuracy",
            "macro_f1",
            "ece_10_bins",
        ]
    ].copy()
    output = pd.concat([baseline, goal], ignore_index=True)
    return output.sort_values(["split", "log_loss", "brier_score"]).reset_index(
        drop=True
    )


def _promotion_adjustments(
    production_model: GoalStrengthModel,
) -> tuple[pd.DataFrame, dict[str, tuple[float, float]]]:
    promotions = pd.read_csv(PROCESSED_DIR / "historical_promotions.csv")
    historical = promotions[
        promotions["has_segunda_statistics"].eq(True)
        & promotions["laliga_played"].notna()
    ].copy()
    historical["attack_ratio"] = (
        historical["laliga_goals_for"] / historical["laliga_played"]
    ) / (historical["segunda_goals_for"] / historical["segunda_played"])
    historical["defense_ratio"] = (
        historical["laliga_goals_against"] / historical["laliga_played"]
    ) / (historical["segunda_goals_against"] / historical["segunda_played"])
    overall_attack = float(historical["attack_ratio"].median())
    overall_defense = float(historical["defense_ratio"].median())
    historical["segunda_attack_rate"] = (
        historical["segunda_goals_for"] / historical["segunda_played"]
    )
    historical["segunda_defense_rate"] = (
        historical["segunda_goals_against"] / historical["segunda_played"]
    )
    historical["laliga_attack_rate"] = (
        historical["laliga_goals_for"] / historical["laliga_played"]
    )
    historical["laliga_defense_rate"] = (
        historical["laliga_goals_against"] / historical["laliga_played"]
    )

    current = promotions[
        promotions["laliga_season"].eq("2026/27")
        & promotions["has_segunda_statistics"].eq(True)
    ].copy()
    records: list[dict] = []
    overrides: dict[str, tuple[float, float]] = {}
    baseline_rate = float(np.exp(production_model.intercept))
    for row in current.itertuples(index=False):
        peer = historical[historical["promotion_type"].eq(row.promotion_type)]
        attack_ratio = (
            float(peer["attack_ratio"].median())
            if len(peer) >= 3
            else overall_attack
        )
        defense_ratio = (
            float(peer["defense_ratio"].median())
            if len(peer) >= 3
            else overall_defense
        )
        segunda_attack = row.segunda_goals_for / row.segunda_played
        segunda_defense = row.segunda_goals_against / row.segunda_played
        peer_segunda_attack = float(peer["segunda_attack_rate"].median())
        peer_segunda_defense = float(peer["segunda_defense_rate"].median())
        peer_laliga_attack = float(peer["laliga_attack_rate"].median())
        peer_laliga_defense = float(peer["laliga_defense_rate"].median())
        # With only 12 complete promoted cohorts, a direct rate conversion is
        # too volatile. Use the peer cohort as the anchor and let the current
        # Segunda performance modify it with a conservative 0.35 elasticity.
        expected_laliga_attack = float(
            peer_laliga_attack
            * (segunda_attack / peer_segunda_attack) ** 0.35
        )
        expected_laliga_defense = float(
            peer_laliga_defense
            * (segunda_defense / peer_segunda_defense) ** 0.35
        )
        attack_effect = float(
            np.clip(
                0.75 * np.log(expected_laliga_attack / baseline_rate),
                -0.45,
                0.45,
            )
        )
        defense_effect = float(
            np.clip(
                0.75 * np.log(expected_laliga_defense / baseline_rate),
                -0.45,
                0.45,
            )
        )
        overrides[row.team_id] = (attack_effect, defense_effect)
        records.append(
            {
                "team_id": row.team_id,
                "team": row.team,
                "promotion_type": row.promotion_type,
                "segunda_goals_for_per_match": segunda_attack,
                "segunda_goals_against_per_match": segunda_defense,
                "historical_attack_ratio": attack_ratio,
                "historical_defense_ratio": defense_ratio,
                "peer_laliga_goals_for_per_match": peer_laliga_attack,
                "peer_laliga_goals_against_per_match": peer_laliga_defense,
                "segunda_rate_elasticity": 0.35,
                "initial_laliga_goals_for_per_match": expected_laliga_attack,
                "initial_laliga_goals_against_per_match": expected_laliga_defense,
                "attack_effect": attack_effect,
                "defense_effect": defense_effect,
                "historical_promoted_peers": len(peer),
                "confidence": "low",
            }
        )
    return pd.DataFrame(records), overrides


def _production_predictions(
    model: GoalStrengthModel,
    overrides: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    fixtures = pd.read_csv(PROCESSED_DIR / "fixtures_2026_27.csv")
    records: list[dict] = []
    for row in fixtures.itertuples(index=False):
        matrix, expected_home, expected_away = model.score_matrix(
            row.home_team_id,
            row.away_team_id,
            overrides,
        )
        probabilities = np.array(
            [
                np.tril(matrix, -1).sum(),
                np.trace(matrix),
                np.triu(matrix, 1).sum(),
            ],
            dtype=float,
        )
        probabilities /= probabilities.sum()
        top = _top_scorelines(matrix)
        promoted_involved = (
            row.home_team_id in overrides or row.away_team_id in overrides
        )
        records.append(
            {
                "fixture_id": row.fixture_id,
                "season": row.season,
                "matchday": int(row.matchday),
                "reference_date": row.reference_date,
                "scheduled_date": row.scheduled_date,
                "kickoff_time": row.kickoff_time,
                "home_team_id": row.home_team_id,
                "home_team": row.home_team,
                "away_team_id": row.away_team_id,
                "away_team": row.away_team,
                "model": model.model_name,
                "expected_home_goals": expected_home,
                "expected_away_goals": expected_away,
                "probability_home": probabilities[0],
                "probability_draw": probabilities[1],
                "probability_away": probabilities[2],
                "predicted_ftr": CLASS_LABELS[int(probabilities.argmax())],
                "predicted_score": f"{top[0][0]}-{top[0][1]}",
                "predicted_score_probability": top[0][2],
                "top_2_score": f"{top[1][0]}-{top[1][1]}",
                "top_2_score_probability": top[1][2],
                "top_3_score": f"{top[2][0]}-{top[2][1]}",
                "top_3_score_probability": top[2][2],
                "confidence": "low" if promoted_involved else "medium",
                "promoted_adjustment_applied": int(promoted_involved),
                "feature_snapshot": "preseason_static",
                "requires_dynamic_update": True,
            }
        )
    return pd.DataFrame(records)


def _team_strengths(
    production_models: dict[str, GoalStrengthModel],
    selected_model: str,
    promotion_adjustments: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict] = []
    promoted = promotion_adjustments.set_index("team_id")
    for model_name, model in production_models.items():
        for index, team in enumerate(model.teams):
            attack = float(model.attack[index])
            defense = float(model.defense[index])
            source = "laliga_history"
            if model_name == selected_model and team in promoted.index:
                attack = float(promoted.loc[team, "attack_effect"])
                defense = float(promoted.loc[team, "defense_effect"])
                source = "segunda_promotion_adjustment"
            records.append(
                {
                    "model": model_name,
                    "team_id": team,
                    "attack_strength": attack,
                    "defense_vulnerability": defense,
                    "home_advantage": model.home_advantage,
                    "rho": model.rho,
                    "half_life_days": _half_life_label(model.half_life_days),
                    "strength_source": source,
                }
            )
    for team, row in promoted.iterrows():
        if not (
            (pd.DataFrame(records)["model"].eq(selected_model))
            & (pd.DataFrame(records)["team_id"].eq(team))
        ).any():
            model = production_models[selected_model]
            records.append(
                {
                    "model": selected_model,
                    "team_id": team,
                    "attack_strength": float(row["attack_effect"]),
                    "defense_vulnerability": float(row["defense_effect"]),
                    "home_advantage": model.home_advantage,
                    "rho": model.rho,
                    "half_life_days": _half_life_label(model.half_life_days),
                    "strength_source": "segunda_promotion_adjustment",
                }
            )
    return pd.DataFrame(records).sort_values(
        ["model", "attack_strength"],
        ascending=[True, False],
    )


def _write_figures(
    comparison: pd.DataFrame,
    goal_metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    strengths: pd.DataFrame,
    selected_model: str,
) -> list[str]:
    figure_dir = REPORTS_DIR / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    colors = {
        "market": "#7C3AED",
        "logistic_sports": "#0EA5E9",
        "logistic_market": "#10B981",
        "elo_multinomial": "#F59E0B",
        "poisson": "#2563EB",
        "dixon_coles": "#E11D48",
    }
    files: list[str] = []

    for split, filename, title in [
        ("validation", "13_goles_validacion.png", "Validación walk-forward"),
        ("test", "14_goles_prueba.png", "Prueba final 2025/26"),
    ]:
        rows = comparison[comparison["split"].eq(split)].sort_values("log_loss")
        fig, ax = plt.subplots(figsize=(10, 5.5))
        ax.barh(
            rows["model"],
            rows["log_loss"],
            color=[colors.get(model, "#64748B") for model in rows["model"]],
        )
        ax.invert_yaxis()
        ax.set_xlabel("Log Loss — menor es mejor")
        ax.set_title(f"{title}: modelos de goles frente a baselines")
        ax.axvline(
            rows.loc[rows["model"].eq("market"), "log_loss"].iloc[0],
            color="#7C3AED",
            linestyle="--",
            linewidth=1,
        )
        fig.tight_layout()
        path = figure_dir / filename
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        files.append(str(path.relative_to(REPORTS_DIR)))

    test_rows = predictions[
        predictions["split"].eq("test")
        & predictions["model"].eq(selected_model)
    ]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(
        test_rows["expected_home_goals"],
        test_rows["home_goals"],
        alpha=0.45,
        label="Local",
        color="#2563EB",
    )
    ax.scatter(
        test_rows["expected_away_goals"],
        test_rows["away_goals"],
        alpha=0.45,
        label="Visitante",
        color="#E11D48",
    )
    ax.plot([0, 5], [0, 5], "--", color="#64748B")
    ax.set(
        xlabel="Goles esperados",
        ylabel="Goles observados",
        title=f"Goles esperados vs. observados — {selected_model}",
    )
    ax.legend()
    fig.tight_layout()
    path = figure_dir / "15_goles_esperados_observados.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    score_counts = (
        test_rows.assign(
            actual_score=lambda frame: frame["home_goals"].astype(str)
            + "-"
            + frame["away_goals"].astype(str)
        )
        .groupby(["predicted_score", "actual_score"])
        .size()
        .reset_index(name="matches")
    )
    top_predicted = test_rows["predicted_score"].value_counts().head(6).index
    top_actual = (
        test_rows["home_goals"].astype(str)
        + "-"
        + test_rows["away_goals"].astype(str)
    ).value_counts().head(6).index
    matrix = (
        score_counts[
            score_counts["predicted_score"].isin(top_predicted)
            & score_counts["actual_score"].isin(top_actual)
        ]
        .pivot(index="actual_score", columns="predicted_score", values="matches")
        .reindex(index=top_actual, columns=top_predicted)
        .fillna(0)
    )
    fig, ax = plt.subplots(figsize=(8, 6))
    image = ax.imshow(matrix.to_numpy(), cmap="Blues")
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            ax.text(
                column,
                row,
                int(matrix.iloc[row, column]),
                ha="center",
                va="center",
            )
    ax.set_xticks(range(len(matrix.columns)), matrix.columns)
    ax.set_yticks(range(len(matrix.index)), matrix.index)
    ax.set_xlabel("Marcador modal predicho")
    ax.set_ylabel("Marcador real")
    ax.set_title("Marcadores más frecuentes — prueba 2025/26")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    path = figure_dir / "16_marcadores_prueba.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    strength_rows = strengths[strengths["model"].eq(selected_model)].copy()
    strength_rows["overall_strength"] = (
        strength_rows["attack_strength"] - strength_rows["defense_vulnerability"]
    )
    strength_rows = strength_rows.sort_values("overall_strength")
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.barh(
        strength_rows["team_id"],
        strength_rows["overall_strength"],
        color=np.where(
            strength_rows["strength_source"].eq("segunda_promotion_adjustment"),
            "#F59E0B",
            "#2563EB",
        ),
    )
    ax.axvline(0.0, color="#64748B", linewidth=1)
    ax.set_xlabel("Ataque − vulnerabilidad defensiva")
    ax.set_title(f"Fuerza inicial 2026/27 — {selected_model}")
    fig.tight_layout()
    path = figure_dir / "17_fuerza_equipos_2026_27.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))
    return files


def _quality_checks(
    validation: pd.DataFrame,
    test: pd.DataFrame,
    candidates: pd.DataFrame,
    comparison: pd.DataFrame,
    fixtures: pd.DataFrame,
    promotions: pd.DataFrame,
) -> pd.DataFrame:
    predictions = pd.concat([validation, test], ignore_index=True)
    probability_values = predictions[PROBABILITY_COLUMNS].to_numpy(dtype=float)
    checks = [
        ("validation_rows_per_goal_model", validation.groupby("model").size().eq(760).all()),
        ("test_rows_per_goal_model", test.groupby("model").size().eq(380).all()),
        ("two_goal_models_evaluated", set(validation["model"]) == set(GOAL_MODELS)),
        ("candidate_grid_complete", len(candidates[candidates["fold"].eq("COMBINED")]) == 8),
        ("probabilities_sum_to_one", np.allclose(probability_values.sum(axis=1), 1.0)),
        ("probabilities_are_finite", np.isfinite(probability_values).all()),
        ("probabilities_within_bounds", ((probability_values >= 0) & (probability_values <= 1)).all()),
        ("expected_goals_are_positive", predictions[["expected_home_goals", "expected_away_goals"]].gt(0).all().all()),
        ("test_season_is_2025_26", test["season"].eq(TEST_SEASON).all()),
        ("validation_uses_only_locked_seasons", set(validation["season"]) == set(VALIDATION_SEASONS)),
        ("baseline_comparison_contains_market", comparison["model"].eq("market").any()),
        ("fixtures_are_complete", len(fixtures) == 380 and fixtures["fixture_id"].is_unique),
        ("fixture_probabilities_sum_to_one", np.allclose(fixtures[PROBABILITY_COLUMNS].sum(axis=1), 1.0)),
        ("three_promoted_adjustments", len(promotions) == 3),
    ]
    return pd.DataFrame(
        [{"check": name, "passed": bool(passed)} for name, passed in checks]
    )


def run_phase5() -> dict:
    matches_path = PROCESSED_DIR / "matches_master.csv"
    if not matches_path.exists():
        raise FileNotFoundError("Run Phase 1 before Phase 5: matches_master.csv is missing.")
    if not (REPORTS_DIR / "model_metrics.csv").exists():
        raise FileNotFoundError("Run Phase 4 before Phase 5: model_metrics.csv is missing.")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    matches = pd.read_csv(matches_path)
    matches = matches[matches["division"].eq("SP1")].copy()
    matches["date"] = pd.to_datetime(matches["date"])
    matches = matches.sort_values(["date", "match_id"]).reset_index(drop=True)

    candidates, selected_half_life, validation_predictions = _candidate_search(matches)
    validation = pd.concat(validation_predictions.values(), ignore_index=True)
    test, fitted_test_models = _evaluate_test(matches, selected_half_life)
    goal_metrics = _metrics_table(validation, test)
    comparison = _baseline_comparison(goal_metrics)

    production_models: dict[str, GoalStrengthModel] = {}
    for model_name in GOAL_MODELS:
        production_models[model_name] = _fit_goal_model(
            matches,
            model_name,
            selected_half_life[model_name],
            TEST_SEASON,
        )
    validation_goal = goal_metrics[goal_metrics["split"].eq("validation")]
    selected_goal_model = str(
        validation_goal.sort_values(["log_loss", "brier_score"]).iloc[0]["model"]
    )
    promotion_adjustments, overrides = _promotion_adjustments(
        production_models[selected_goal_model]
    )
    fixture_predictions = _production_predictions(
        production_models[selected_goal_model],
        overrides,
    )
    strengths = _team_strengths(
        production_models,
        selected_goal_model,
        promotion_adjustments,
    )

    all_goal_predictions = pd.concat([validation, test], ignore_index=True)
    figures = _write_figures(
        comparison,
        goal_metrics,
        all_goal_predictions,
        strengths,
        selected_goal_model,
    )
    quality = _quality_checks(
        validation,
        test,
        candidates,
        comparison,
        fixture_predictions,
        promotion_adjustments,
    )

    candidates.to_csv(REPORTS_DIR / "goal_model_candidate_validation.csv", index=False)
    validation.to_csv(
        REPORTS_DIR / "goal_model_predictions_validation.csv",
        index=False,
    )
    test.to_csv(REPORTS_DIR / "goal_model_predictions_test.csv", index=False)
    goal_metrics.to_csv(REPORTS_DIR / "goal_model_metrics.csv", index=False)
    comparison.to_csv(REPORTS_DIR / "phase5_model_comparison.csv", index=False)
    strengths.to_csv(REPORTS_DIR / "goal_model_team_strengths.csv", index=False)
    promotion_adjustments.to_csv(
        REPORTS_DIR / "promoted_strength_adjustment.csv",
        index=False,
    )
    fixture_predictions.to_csv(
        PROCESSED_DIR / "fixtures_2026_27_goal_predictions.csv",
        index=False,
    )
    quality.to_csv(REPORTS_DIR / "phase5_quality_checks.csv", index=False)
    joblib.dump(
        {
            "models": fitted_test_models,
            "selected_half_life": selected_half_life,
            "trained_through": "2024/25",
        },
        REPORTS_DIR / "phase5_fitted_models.joblib",
    )
    joblib.dump(
        {
            "models": production_models,
            "selected_goal_model": selected_goal_model,
            "selected_half_life": selected_half_life,
            "promoted_overrides": overrides,
            "trained_through": TEST_SEASON,
        },
        REPORTS_DIR / "phase5_production_models.joblib",
    )

    selection = {
        "validation_protocol": [
            {"train": "2016/17–2022/23", "evaluate": "2023/24"},
            {"train": "2016/17–2023/24", "evaluate": "2024/25"},
        ],
        "test_protocol": {
            "train": "2016/17–2024/25",
            "evaluate_once": TEST_SEASON,
        },
        "half_life_candidates_days": [
            _half_life_label(value) for value in HALF_LIFE_CANDIDATES
        ],
        "selected_half_life_days": {
            model: _half_life_label(value)
            for model, value in selected_half_life.items()
        },
        "selected_goal_model_by_validation_log_loss": selected_goal_model,
        "max_goals_in_score_matrix": MAX_GOALS,
    }
    (REPORTS_DIR / "goal_model_selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    selected_test = goal_metrics[
        goal_metrics["split"].eq("test")
        & goal_metrics["model"].eq(selected_goal_model)
    ].iloc[0]
    market_test = comparison[
        comparison["split"].eq("test") & comparison["model"].eq("market")
    ].iloc[0]
    sports_test = comparison[
        comparison["split"].eq("test")
        & comparison["model"].eq("logistic_sports")
    ].iloc[0]
    summary = {
        "quality_passed": bool(quality["passed"].all()),
        "quality_checks": len(quality),
        "goal_models_evaluated": len(GOAL_MODELS),
        "candidate_configurations": 8,
        "validation_rows_per_model": 760,
        "test_rows_per_model": 380,
        "selected_half_life_days": selection["selected_half_life_days"],
        "selected_goal_model": selected_goal_model,
        "selected_goal_model_test_log_loss": float(selected_test["log_loss"]),
        "selected_goal_model_test_accuracy": float(selected_test["accuracy"]),
        "selected_goal_model_test_exact_score_accuracy": float(
            selected_test["exact_score_accuracy"]
        ),
        "market_test_log_loss": float(market_test["log_loss"]),
        "sports_baseline_test_log_loss": float(sports_test["log_loss"]),
        "beats_market_on_test": bool(
            selected_test["log_loss"] < market_test["log_loss"]
        ),
        "beats_sports_baseline_on_test": bool(
            selected_test["log_loss"] < sports_test["log_loss"]
        ),
        "promoted_adjustments": len(promotion_adjustments),
        "fixture_predictions_2026_27": len(fixture_predictions),
        "production_models_trained_through": TEST_SEASON,
        "figures": figures,
    }
    (REPORTS_DIR / "phase5_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
