"""Exporta una fotografía estática compatible con los contratos de FastAPI."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend" / "public" / "assets" / "demo"


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def write(name: str, payload: object) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_fixtures(ensemble: pd.DataFrame) -> list[dict]:
    rows = ensemble[
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
        ]
    ].copy()
    rows["scheduled_date"] = rows["scheduled_date"].where(
        rows["scheduled_date"].notna(), None
    )
    rows["kickoff_time"] = rows["kickoff_time"].where(
        rows["kickoff_time"].notna(), None
    )
    rows["status"] = "scheduled"
    return records(rows)


def build_predictions(
    ensemble: pd.DataFrame, goals: pd.DataFrame
) -> list[dict]:
    goal_columns = [
        "fixture_id",
        "expected_home_goals",
        "expected_away_goals",
        "predicted_score",
    ]
    rows = ensemble.merge(goals[goal_columns], on="fixture_id", how="left")
    columns = [
        "fixture_id",
        "matchday",
        "home_team",
        "away_team",
        "model",
        "probability_home",
        "probability_draw",
        "probability_away",
        "predicted_ftr",
        "confidence",
        "expected_home_goals",
        "expected_away_goals",
        "predicted_score",
        "market_odds_available",
    ]
    return records(rows[columns])


def build_standings() -> list[dict]:
    rows = pd.read_csv(ROOT / "reports" / "current_table_2026_27.csv")
    rows["position"] = rows["position"].where(rows["position"].notna(), None)
    rows["ppg"] = rows["ppg"].where(rows["ppg"].notna(), None)
    return records(rows)


def build_simulation() -> list[dict]:
    rows = pd.read_csv(ROOT / "reports" / "season_simulation_summary.csv")
    columns = [
        "team_id",
        "team",
        "simulations",
        "expected_points",
        "points_p05",
        "points_p95",
        "expected_position",
        "champion_probability",
        "top4_probability",
        "europe_top7_probability",
        "relegation_probability",
    ]
    return records(rows[columns])


def main() -> None:
    ensemble = pd.read_csv(
        ROOT
        / "data"
        / "processed"
        / "fixtures_2026_27_ensemble_predictions.csv"
    )
    goals = pd.read_csv(
        ROOT
        / "data"
        / "processed"
        / "fixtures_2026_27_goal_predictions.csv"
    )

    write("fixtures.json", build_fixtures(ensemble))
    write("predictions.json", build_predictions(ensemble, goals))
    write("standings.json", build_standings())
    write("simulation.json", build_simulation())
    write(
        "health.json",
        {
            "status": "ok",
            "database": "snapshot",
            "season": "2026/27",
            "latest_update_id": "7f6a923c1a4600d7",
            "fixtures": 380,
            "predictions": 380,
            "completed_matches": 0,
            "simulations": 50_000,
        },
    )

    manifest = {
        "phase": 12,
        "season": "2026/27",
        "fixtures": len(build_fixtures(ensemble)),
        "predictions": len(build_predictions(ensemble, goals)),
        "teams": len(build_simulation()),
        "simulations": 50_000,
        "source": "preseason_snapshot",
    }
    write("manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
