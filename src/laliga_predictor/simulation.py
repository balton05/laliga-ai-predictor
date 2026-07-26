from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import poisson

from .config import PROCESSED_DIR, REPORTS_DIR


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


SIMULATIONS = 50_000
RANDOM_SEED = 42
MAX_GOALS = 10
CONVERGENCE_CHECKPOINTS = (1_000, 5_000, 10_000, 25_000, 50_000)
PROBABILITY_COLUMNS = [
    "probability_home",
    "probability_draw",
    "probability_away",
]


def _load_simulation_inputs() -> pd.DataFrame:
    ensemble_path = (
        PROCESSED_DIR / "fixtures_2026_27_ensemble_predictions.csv"
    )
    goal_path = PROCESSED_DIR / "fixtures_2026_27_goal_predictions.csv"
    if not ensemble_path.exists() or not goal_path.exists():
        raise FileNotFoundError(
            "Run Phases 5 and 7 before the Phase 8 simulation."
        )

    ensemble = pd.read_csv(ensemble_path)
    goals = pd.read_csv(goal_path)
    goal_columns = [
        "fixture_id",
        "expected_home_goals",
        "expected_away_goals",
        "promoted_adjustment_applied",
    ]
    inputs = ensemble.merge(
        goals[goal_columns],
        on="fixture_id",
        how="left",
        validate="one_to_one",
    )
    inputs["scoreline_model"] = "poisson_conditioned_on_ensemble_1x2"
    return inputs.sort_values(["matchday", "fixture_id"]).reset_index(drop=True)


def _scoreline_distributions(
    expected_home_goals: float,
    expected_away_goals: float,
) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    goals = np.arange(MAX_GOALS + 1)
    home_pmf = poisson.pmf(goals, expected_home_goals)
    away_pmf = poisson.pmf(goals, expected_away_goals)
    matrix = np.outer(home_pmf, away_pmf)
    home_scores, away_scores = np.indices(matrix.shape)
    distributions: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    masks = {
        0: home_scores > away_scores,
        1: home_scores == away_scores,
        2: home_scores < away_scores,
    }
    for outcome, mask in masks.items():
        weights = matrix[mask].astype(float)
        weights /= weights.sum()
        distributions[outcome] = (
            home_scores[mask].astype(np.int8),
            away_scores[mask].astype(np.int8),
            np.cumsum(weights),
        )
        distributions[outcome][2][-1] = 1.0
    return distributions


def _sample_conditioned_scorelines(
    rng: np.random.Generator,
    outcomes: np.ndarray,
    distributions: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    home_goals = np.empty(len(outcomes), dtype=np.int8)
    away_goals = np.empty(len(outcomes), dtype=np.int8)
    for outcome in (0, 1, 2):
        mask = outcomes == outcome
        count = int(mask.sum())
        if not count:
            continue
        possible_home, possible_away, cumulative = distributions[outcome]
        sampled = np.searchsorted(
            cumulative,
            rng.random(count),
            side="right",
        )
        home_goals[mask] = possible_home[sampled]
        away_goals[mask] = possible_away[sampled]
    return home_goals, away_goals


def _rank_tables(
    points: np.ndarray,
    goals_for: np.ndarray,
    goals_against: np.ndarray,
    head_to_head_points: np.ndarray,
    head_to_head_goal_difference: np.ndarray,
) -> np.ndarray:
    simulations, teams = points.shape
    ranks = np.empty((simulations, teams), dtype=np.int8)
    alphabetical_fallback = np.arange(teams)
    goal_difference = goals_for - goals_against

    for simulation in range(simulations):
        initial = np.lexsort(
            (
                alphabetical_fallback,
                -goals_for[simulation],
                -goal_difference[simulation],
                -points[simulation],
            )
        )
        ordered: list[int] = []
        start = 0
        while start < teams:
            end = start + 1
            tied_points = points[simulation, initial[start]]
            while (
                end < teams
                and points[simulation, initial[end]] == tied_points
            ):
                end += 1
            group = initial[start:end]
            if len(group) > 1:
                mini_points = head_to_head_points[
                    simulation
                ][np.ix_(group, group)].sum(axis=1)
                mini_goal_difference = head_to_head_goal_difference[
                    simulation
                ][np.ix_(group, group)].sum(axis=1)
                group_order = np.lexsort(
                    (
                        alphabetical_fallback[group],
                        -goals_for[simulation, group],
                        -goal_difference[simulation, group],
                        -mini_goal_difference,
                        -mini_points,
                    )
                )
                group = group[group_order]
            ordered.extend(group.tolist())
            start = end
        ranks[simulation, np.asarray(ordered)] = np.arange(
            1,
            teams + 1,
            dtype=np.int8,
        )
    return ranks


def _simulate(
    inputs: pd.DataFrame,
    simulations: int = SIMULATIONS,
    seed: int = RANDOM_SEED,
) -> dict[str, np.ndarray | list[str]]:
    rng = np.random.default_rng(seed)
    team_frame = pd.concat(
        [
            inputs[["home_team_id", "home_team"]].rename(
                columns={"home_team_id": "team_id", "home_team": "team"}
            ),
            inputs[["away_team_id", "away_team"]].rename(
                columns={"away_team_id": "team_id", "away_team": "team"}
            ),
        ],
        ignore_index=True,
    ).drop_duplicates()
    team_frame = team_frame.sort_values("team").reset_index(drop=True)
    team_ids = team_frame["team_id"].tolist()
    team_names = team_frame["team"].tolist()
    team_index = {team_id: index for index, team_id in enumerate(team_ids)}
    team_count = len(team_ids)

    points = np.zeros((simulations, team_count), dtype=np.int16)
    goals_for = np.zeros_like(points)
    goals_against = np.zeros_like(points)
    head_to_head_points = np.zeros(
        (simulations, team_count, team_count),
        dtype=np.int8,
    )
    head_to_head_goal_difference = np.zeros_like(head_to_head_points)
    outcome_counts = np.zeros(3, dtype=np.int64)
    rows = np.arange(simulations)

    for fixture in inputs.itertuples(index=False):
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
            rng,
            outcomes,
            distributions,
        )
        home_points = np.select(
            [outcomes == 0, outcomes == 1],
            [3, 1],
            default=0,
        ).astype(np.int8)
        away_points = np.select(
            [outcomes == 2, outcomes == 1],
            [3, 1],
            default=0,
        ).astype(np.int8)

        points[:, home] += home_points
        points[:, away] += away_points
        goals_for[:, home] += home_goals
        goals_against[:, home] += away_goals
        goals_for[:, away] += away_goals
        goals_against[:, away] += home_goals
        head_to_head_points[rows, home, away] += home_points
        head_to_head_points[rows, away, home] += away_points
        goal_difference = (home_goals - away_goals).astype(np.int8)
        head_to_head_goal_difference[rows, home, away] += goal_difference
        head_to_head_goal_difference[rows, away, home] -= goal_difference

    ranks = _rank_tables(
        points,
        goals_for,
        goals_against,
        head_to_head_points,
        head_to_head_goal_difference,
    )
    return {
        "team_ids": team_ids,
        "team_names": team_names,
        "points": points,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "ranks": ranks,
        "outcome_counts": outcome_counts,
    }


def _summary_table(simulation: dict) -> pd.DataFrame:
    points = simulation["points"]
    goals_for = simulation["goals_for"]
    goals_against = simulation["goals_against"]
    ranks = simulation["ranks"]
    simulations = len(points)
    records: list[dict] = []
    for index, (team_id, team) in enumerate(
        zip(simulation["team_ids"], simulation["team_names"])
    ):
        team_points = points[:, index]
        team_ranks = ranks[:, index]
        records.append(
            {
                "team_id": team_id,
                "team": team,
                "simulations": simulations,
                "expected_points": float(team_points.mean()),
                "median_points": float(np.median(team_points)),
                "points_p05": float(np.quantile(team_points, 0.05)),
                "points_p95": float(np.quantile(team_points, 0.95)),
                "expected_goals_for": float(goals_for[:, index].mean()),
                "expected_goals_against": float(
                    goals_against[:, index].mean()
                ),
                "expected_goal_difference": float(
                    (goals_for[:, index] - goals_against[:, index]).mean()
                ),
                "expected_position": float(team_ranks.mean()),
                "median_position": float(np.median(team_ranks)),
                "champion_probability": float(np.mean(team_ranks == 1)),
                "top4_probability": float(np.mean(team_ranks <= 4)),
                "top6_probability": float(np.mean(team_ranks <= 6)),
                "europe_top7_probability": float(np.mean(team_ranks <= 7)),
                "relegation_probability": float(np.mean(team_ranks >= 18)),
                "last_place_probability": float(np.mean(team_ranks == 20)),
            }
        )
    return pd.DataFrame(records).sort_values(
        ["expected_position", "expected_points"],
        ascending=[True, False],
    ).reset_index(drop=True)


def _position_distribution(simulation: dict) -> pd.DataFrame:
    ranks = simulation["ranks"]
    simulations = len(ranks)
    records: list[dict] = []
    for team_index, (team_id, team) in enumerate(
        zip(simulation["team_ids"], simulation["team_names"])
    ):
        counts = np.bincount(ranks[:, team_index], minlength=21)[1:]
        for position, count in enumerate(counts, start=1):
            records.append(
                {
                    "team_id": team_id,
                    "team": team,
                    "position": position,
                    "count": int(count),
                    "probability": float(count / simulations),
                }
            )
    return pd.DataFrame(records)


def _convergence_table(simulation: dict) -> pd.DataFrame:
    ranks = simulation["ranks"]
    points = simulation["points"]
    final = {
        "champion": np.mean(ranks == 1, axis=0),
        "top4": np.mean(ranks <= 4, axis=0),
        "top7": np.mean(ranks <= 7, axis=0),
        "relegation": np.mean(ranks >= 18, axis=0),
        "expected_points": np.mean(points, axis=0),
    }
    records: list[dict] = []
    for checkpoint in CONVERGENCE_CHECKPOINTS:
        checkpoint = min(checkpoint, len(ranks))
        current = {
            "champion": np.mean(ranks[:checkpoint] == 1, axis=0),
            "top4": np.mean(ranks[:checkpoint] <= 4, axis=0),
            "top7": np.mean(ranks[:checkpoint] <= 7, axis=0),
            "relegation": np.mean(ranks[:checkpoint] >= 18, axis=0),
            "expected_points": np.mean(points[:checkpoint], axis=0),
        }
        records.append(
            {
                "simulations": checkpoint,
                "max_abs_champion_change": float(
                    np.max(np.abs(current["champion"] - final["champion"]))
                ),
                "max_abs_top4_change": float(
                    np.max(np.abs(current["top4"] - final["top4"]))
                ),
                "max_abs_top7_change": float(
                    np.max(np.abs(current["top7"] - final["top7"]))
                ),
                "max_abs_relegation_change": float(
                    np.max(
                        np.abs(
                            current["relegation"] - final["relegation"]
                        )
                    )
                ),
                "max_abs_expected_points_change": float(
                    np.max(
                        np.abs(
                            current["expected_points"]
                            - final["expected_points"]
                        )
                    )
                ),
            }
        )
        if checkpoint == len(ranks):
            break
    return pd.DataFrame(records).drop_duplicates("simulations")


def _write_figures(
    summary: pd.DataFrame,
    positions: pd.DataFrame,
) -> list[str]:
    figure_dir = REPORTS_DIR / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    champion = summary.sort_values("champion_probability", ascending=True)
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(
        champion["team"],
        champion["champion_probability"],
        color="#0F766E",
    )
    ax.set_title("Probabilidad de campeón — LaLiga 2026/27")
    ax.set_xlabel("Probabilidad")
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    fig.tight_layout()
    path = figure_dir / "27_champion_probabilities.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    zones = summary.sort_values("expected_position").set_index("team")[
        ["top4_probability", "europe_top7_probability", "relegation_probability"]
    ]
    fig, ax = plt.subplots(figsize=(11, 7))
    zones.plot(
        kind="barh",
        ax=ax,
        color=["#2563EB", "#F59E0B", "#DC2626"],
    )
    ax.invert_yaxis()
    ax.set_title("Probabilidades por zona — LaLiga 2026/27")
    ax.set_xlabel("Probabilidad")
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    ax.legend(["Top 4", "Top 7 europeo", "Descenso"])
    fig.tight_layout()
    path = figure_dir / "28_zone_probabilities.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    points = summary.sort_values("expected_points")
    fig, ax = plt.subplots(figsize=(9, 7))
    lower = points["expected_points"] - points["points_p05"]
    upper = points["points_p95"] - points["expected_points"]
    ax.errorbar(
        points["expected_points"],
        points["team"],
        xerr=np.vstack([lower, upper]),
        fmt="o",
        color="#0F766E",
        ecolor="#94A3B8",
        capsize=3,
    )
    ax.set_title("Puntos esperados e intervalo central del 90 %")
    ax.set_xlabel("Puntos")
    fig.tight_layout()
    path = figure_dir / "29_points_intervals.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    order = summary.sort_values("expected_position")["team"].tolist()
    heatmap = positions.pivot(
        index="team",
        columns="position",
        values="probability",
    ).loc[order]
    fig, ax = plt.subplots(figsize=(13, 8))
    image = ax.imshow(heatmap, aspect="auto", cmap="YlGnBu")
    ax.set_yticks(np.arange(len(heatmap)), heatmap.index)
    ax.set_xticks(np.arange(20), np.arange(1, 21))
    ax.set_xlabel("Posición final")
    ax.set_title("Distribución de posición final — 50,000 simulaciones")
    fig.colorbar(image, ax=ax, label="Probabilidad")
    fig.tight_layout()
    path = figure_dir / "30_position_heatmap.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))
    return files


def _quality_checks(
    inputs: pd.DataFrame,
    simulation: dict,
    summary: pd.DataFrame,
    positions: pd.DataFrame,
    convergence: pd.DataFrame,
) -> pd.DataFrame:
    probabilities = inputs[PROBABILITY_COLUMNS].to_numpy(dtype=float)
    ranks = simulation["ranks"]
    points = simulation["points"]
    simulated_outcome_rates = simulation["outcome_counts"] / (
        len(inputs) * len(ranks)
    )
    expected_outcome_rates = probabilities.mean(axis=0)
    position_sums_by_team = positions.groupby("team")["probability"].sum()
    position_sums_by_position = positions.groupby("position")[
        "probability"
    ].sum()
    final_convergence = convergence.iloc[-2] if len(convergence) > 1 else None
    checks = [
        ("fixtures_complete_380", len(inputs) == 380),
        ("matchdays_complete_38", inputs.groupby("matchday").size().eq(10).all()),
        (
            "twenty_teams_each_play_38",
            pd.concat([inputs["home_team"], inputs["away_team"]])
            .value_counts()
            .eq(38)
            .all(),
        ),
        ("ensemble_sports_only", inputs["model"].eq("ensemble_sports").all()),
        (
            "fixture_probabilities_sum_to_one",
            np.allclose(probabilities.sum(axis=1), 1.0),
        ),
        (
            "fixture_probabilities_in_range",
            ((probabilities >= 0.0) & (probabilities <= 1.0)).all(),
        ),
        (
            "positive_expected_goals",
            inputs[
                ["expected_home_goals", "expected_away_goals"]
            ].gt(0.0).all().all(),
        ),
        ("simulations_complete", len(ranks) == SIMULATIONS),
        (
            "valid_unique_ranks_each_season",
            np.all(np.sort(ranks, axis=1) == np.arange(1, 21)),
        ),
        (
            "points_in_valid_range",
            ((points >= 0) & (points <= 114)).all(),
        ),
        (
            "league_point_totals_valid",
            ((points.sum(axis=1) >= 760) & (points.sum(axis=1) <= 1140)).all(),
        ),
        (
            "simulated_outcomes_match_inputs",
            np.max(np.abs(simulated_outcome_rates - expected_outcome_rates))
            < 0.001,
        ),
        (
            "position_probabilities_sum_by_team",
            np.allclose(position_sums_by_team, 1.0),
        ),
        (
            "one_team_per_position_in_expectation",
            np.allclose(position_sums_by_position, 1.0),
        ),
        (
            "champion_probabilities_sum_to_one",
            np.isclose(summary["champion_probability"].sum(), 1.0),
        ),
        (
            "top4_probabilities_sum_to_four",
            np.isclose(summary["top4_probability"].sum(), 4.0),
        ),
        (
            "top7_probabilities_sum_to_seven",
            np.isclose(summary["europe_top7_probability"].sum(), 7.0),
        ),
        (
            "relegation_probabilities_sum_to_three",
            np.isclose(summary["relegation_probability"].sum(), 3.0),
        ),
        (
            "zone_probabilities_are_monotonic",
            (
                summary["champion_probability"]
                <= summary["top4_probability"]
            ).all()
            and (
                summary["top4_probability"] <= summary["top6_probability"]
            ).all()
            and (
                summary["top6_probability"]
                <= summary["europe_top7_probability"]
            ).all(),
        ),
        (
            "checkpoint_25000_is_stable",
            final_convergence is not None
            and max(
                final_convergence["max_abs_champion_change"],
                final_convergence["max_abs_top4_change"],
                final_convergence["max_abs_top7_change"],
                final_convergence["max_abs_relegation_change"],
            )
            < 0.012,
        ),
        (
            "promoted_teams_present",
            {
                "racing_santander",
                "deportivo",
                "malaga",
            }.issubset(set(summary["team_id"])),
        ),
        ("no_missing_summary_values", not summary.isna().any().any()),
    ]
    return pd.DataFrame(checks, columns=["check", "passed"]).assign(
        detail=lambda frame: np.where(frame["passed"], "OK", "FAILED")
    )


def run_phase8(
    simulations: int = SIMULATIONS,
    seed: int = RANDOM_SEED,
) -> dict:
    if simulations != SIMULATIONS:
        raise ValueError(
            f"Phase 8 production run requires {SIMULATIONS:,} simulations."
        )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    inputs = _load_simulation_inputs()
    inputs.to_csv(
        PROCESSED_DIR / "fixtures_2026_27_simulation_inputs.csv",
        index=False,
    )
    simulation = _simulate(inputs, simulations=simulations, seed=seed)
    summary = _summary_table(simulation)
    positions = _position_distribution(simulation)
    convergence = _convergence_table(simulation)
    summary.to_csv(
        REPORTS_DIR / "season_simulation_summary.csv",
        index=False,
    )
    positions.to_csv(
        REPORTS_DIR / "season_position_distribution.csv",
        index=False,
    )
    convergence.to_csv(
        REPORTS_DIR / "simulation_convergence.csv",
        index=False,
    )
    figures = _write_figures(summary, positions)
    checks = _quality_checks(
        inputs,
        simulation,
        summary,
        positions,
        convergence,
    )
    checks.to_csv(
        REPORTS_DIR / "phase8_quality_checks.csv",
        index=False,
    )
    if not checks["passed"].all():
        failed = checks.loc[~checks["passed"], "check"].tolist()
        raise AssertionError(f"Phase 8 quality checks failed: {failed}")

    champion = summary.iloc[0]
    title_favorite = summary.sort_values(
        "champion_probability",
        ascending=False,
    ).iloc[0]
    relegation = summary.sort_values(
        "relegation_probability",
        ascending=False,
    ).head(3)
    result = {
        "quality_passed": True,
        "quality_checks": len(checks),
        "simulations": simulations,
        "random_seed": seed,
        "fixtures": len(inputs),
        "teams": len(summary),
        "scoreline_method": "poisson_conditioned_on_ensemble_1x2",
        "ranking_method": (
            "points, mini-league head-to-head points, mini-league goal "
            "difference, overall goal difference, goals scored"
        ),
        "title_favorite": title_favorite["team"],
        "title_favorite_probability": float(
            title_favorite["champion_probability"]
        ),
        "highest_expected_points_team": champion["team"],
        "highest_expected_points": float(champion["expected_points"]),
        "highest_relegation_risk_teams": relegation["team"].tolist(),
        "highest_relegation_risks": relegation[
            "relegation_probability"
        ].tolist(),
        "europe_definition": (
            "Top 7 league-position proxy; cup winners and UEFA performance "
            "spots can change the final allocation."
        ),
        "preseason_snapshot": True,
        "requires_dynamic_update": True,
        "figures": figures,
    }
    (REPORTS_DIR / "phase8_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result
