from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.api.main import create_app  # noqa: E402
from laliga_predictor.api.settings import Settings  # noqa: E402


def run_phase10() -> dict:
    with TemporaryDirectory(prefix="laliga_phase10_build_") as temporary:
        database = Path(temporary) / "phase10.db"
        settings = Settings(
            database_url=f"sqlite:///{database}",
            project_root=PROJECT_ROOT,
            auto_sync=True,
        )
        with TestClient(create_app(settings)) as client:
            health = client.get("/health")
            fixtures = client.get("/fixtures")
            predictions = client.get("/predictions")
            standings = client.get("/standings")
            simulation = client.get("/simulation")
            latest = client.get("/updates/latest")
            openapi = client.get("/openapi.json")

    health_data = health.json()
    fixture_data = fixtures.json()
    prediction_data = predictions.json()
    standing_data = standings.json()
    simulation_data = simulation.json()
    latest_data = latest.json()
    probability_sums = [
        row["probability_home"]
        + row["probability_draw"]
        + row["probability_away"]
        for row in prediction_data
    ]
    required_routes = {
        "/health",
        "/fixtures",
        "/predictions",
        "/standings",
        "/simulation",
        "/updates/latest",
        "/update-matchday",
    }
    checks = [
        ("health_200", health.status_code == 200, health.status_code),
        (
            "phase9_update_id_preserved",
            health_data["latest_update_id"] == "7f6a923c1a4600d7",
            health_data["latest_update_id"],
        ),
        ("fixtures_380", len(fixture_data) == 380, len(fixture_data)),
        (
            "fixture_ids_unique",
            len({row["fixture_id"] for row in fixture_data}) == 380,
            len({row["fixture_id"] for row in fixture_data}),
        ),
        (
            "predictions_380",
            len(prediction_data) == 380,
            len(prediction_data),
        ),
        (
            "probabilities_sum_to_one",
            bool(np.allclose(probability_sums, 1.0)),
            float(np.max(np.abs(np.asarray(probability_sums) - 1))),
        ),
        (
            "preseason_uses_sports_ensemble",
            {row["model"] for row in prediction_data}
            == {"ensemble_sports"},
            ",".join(sorted({row["model"] for row in prediction_data})),
        ),
        ("standings_20", len(standing_data) == 20, len(standing_data)),
        (
            "simulation_20",
            len(simulation_data) == 20,
            len(simulation_data),
        ),
        (
            "champion_probability_reconciles",
            np.isclose(
                sum(row["champion_probability"] for row in simulation_data),
                1.0,
            ),
            sum(row["champion_probability"] for row in simulation_data),
        ),
        (
            "top4_probability_reconciles",
            np.isclose(
                sum(row["top4_probability"] for row in simulation_data), 4.0
            ),
            sum(row["top4_probability"] for row in simulation_data),
        ),
        (
            "top7_probability_reconciles",
            np.isclose(
                sum(
                    row["europe_top7_probability"]
                    for row in simulation_data
                ),
                7.0,
            ),
            sum(
                row["europe_top7_probability"] for row in simulation_data
            ),
        ),
        (
            "relegation_probability_reconciles",
            np.isclose(
                sum(
                    row["relegation_probability"]
                    for row in simulation_data
                ),
                3.0,
            ),
            sum(row["relegation_probability"] for row in simulation_data),
        ),
        (
            "openapi_required_routes",
            required_routes.issubset(openapi.json()["paths"]),
            len(required_routes & set(openapi.json()["paths"])),
        ),
        (
            "latest_update_quality_passed",
            latest_data["quality_passed"] is True,
            latest_data["quality_passed"],
        ),
    ]
    quality = pd.DataFrame(
        [
            {"check": name, "passed": bool(passed), "value": value}
            for name, passed, value in checks
        ]
    )
    if not quality["passed"].all():
        failed = quality.loc[~quality["passed"], "check"].tolist()
        raise AssertionError(f"Phase 10 checks failed: {failed}")

    summary = {
        "phase": 10,
        "api_framework": "FastAPI",
        "production_database": "PostgreSQL",
        "test_database": "SQLite",
        "season": "2026/27",
        "source_update_id": health_data["latest_update_id"],
        "fixtures": health_data["fixtures"],
        "predictions": health_data["predictions"],
        "completed_matches": health_data["completed_matches"],
        "simulations": health_data["simulations"],
        "endpoints": sorted(required_routes),
        "quality_checks": len(quality),
        "quality_passed": True,
    }
    reports = PROJECT_ROOT / "reports"
    reports.mkdir(exist_ok=True)
    quality.to_csv(
        reports / "phase10_quality_checks.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (reports / "phase10_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run_phase10(), ensure_ascii=False, indent=2))
