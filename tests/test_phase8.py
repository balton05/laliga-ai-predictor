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

from laliga_predictor.simulation import run_phase8  # noqa: E402


@pytest.fixture(scope="module")
def phase8_summary() -> dict:
    return run_phase8()


def test_phase8_outputs(phase8_summary: dict) -> None:
    assert phase8_summary["quality_passed"] is True
    assert phase8_summary["quality_checks"] == 22
    assert phase8_summary["simulations"] == 50_000
    assert phase8_summary["fixtures"] == 380
    assert phase8_summary["teams"] == 20


def test_zone_probabilities_reconcile(phase8_summary: dict) -> None:
    summary = pd.read_csv(
        PROJECT_ROOT / "reports" / "season_simulation_summary.csv"
    )
    assert np.isclose(summary["champion_probability"].sum(), 1.0)
    assert np.isclose(summary["top4_probability"].sum(), 4.0)
    assert np.isclose(summary["top6_probability"].sum(), 6.0)
    assert np.isclose(summary["europe_top7_probability"].sum(), 7.0)
    assert np.isclose(summary["relegation_probability"].sum(), 3.0)


def test_position_distribution_is_valid(phase8_summary: dict) -> None:
    positions = pd.read_csv(
        PROJECT_ROOT / "reports" / "season_position_distribution.csv"
    )
    assert len(positions) == 400
    assert positions.groupby("team")["probability"].sum().pipe(
        lambda values: np.allclose(values, 1.0)
    )
    assert positions.groupby("position")["probability"].sum().pipe(
        lambda values: np.allclose(values, 1.0)
    )


def test_simulation_inputs_are_preseason_sports_only(
    phase8_summary: dict,
) -> None:
    inputs = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "fixtures_2026_27_simulation_inputs.csv"
    )
    assert len(inputs) == 380
    assert inputs["model"].eq("ensemble_sports").all()
    assert not inputs["market_odds_available"].any()
    assert inputs["requires_dynamic_update"].all()


def test_expected_points_and_positions_are_plausible(
    phase8_summary: dict,
) -> None:
    summary = pd.read_csv(
        PROJECT_ROOT / "reports" / "season_simulation_summary.csv"
    )
    assert summary["expected_points"].between(0, 114).all()
    assert summary["expected_position"].between(1, 20).all()
    assert (
        summary["points_p05"]
        <= summary["expected_points"]
    ).all()
    assert (
        summary["expected_points"]
        <= summary["points_p95"]
    ).all()


def test_convergence_is_reported(phase8_summary: dict) -> None:
    convergence = pd.read_csv(
        PROJECT_ROOT / "reports" / "simulation_convergence.csv"
    )
    assert convergence["simulations"].tolist() == [
        1_000,
        5_000,
        10_000,
        25_000,
        50_000,
    ]
    assert convergence.iloc[-1].drop("simulations").eq(0.0).all()
    assert convergence.iloc[-2][
        [
            "max_abs_champion_change",
            "max_abs_top4_change",
            "max_abs_top7_change",
            "max_abs_relegation_change",
        ]
    ].max() < 0.012


def test_scoreline_and_ranking_methods_are_documented(
    phase8_summary: dict,
) -> None:
    persisted = json.loads(
        (
            PROJECT_ROOT / "reports" / "phase8_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        persisted["scoreline_method"]
        == "poisson_conditioned_on_ensemble_1x2"
    )
    assert "head-to-head" in persisted["ranking_method"]
    assert "Top 7" in persisted["europe_definition"]


def test_promoted_teams_are_included(phase8_summary: dict) -> None:
    summary = pd.read_csv(
        PROJECT_ROOT / "reports" / "season_simulation_summary.csv"
    )
    assert {"racing_santander", "deportivo", "malaga"}.issubset(
        set(summary["team_id"])
    )
