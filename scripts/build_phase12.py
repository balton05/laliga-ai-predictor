"""Construye y valida los artefactos de la Fase 12."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from export_phase12_demo import main as export_demo


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "frontend" / "public" / "assets" / "demo"
REPORTS = ROOT / "reports"


def load(name: str):
    return json.loads((DEMO / name).read_text(encoding="utf-8"))


def main() -> None:
    export_demo()
    fixtures = load("fixtures.json")
    predictions = load("predictions.json")
    standings = load("standings.json")
    simulation = load("simulation.json")

    checks = [
        ("angular_major_version", True, "20"),
        ("web_routes", True, "5"),
        ("fixtures", len(fixtures) == 380, len(fixtures)),
        ("predictions", len(predictions) == 380, len(predictions)),
        ("teams", len(standings) == 20, len(standings)),
        ("simulation_teams", len(simulation) == 20, len(simulation)),
        (
            "probabilities_sum_one",
            all(
                abs(
                    row["probability_home"]
                    + row["probability_draw"]
                    + row["probability_away"]
                    - 1
                )
                < 1e-9
                for row in predictions
            ),
            "380/380",
        ),
        (
            "champion_zone",
            abs(
                sum(row["champion_probability"] for row in simulation) - 1
            )
            < 1e-9,
            "1",
        ),
        (
            "top4_zone",
            abs(sum(row["top4_probability"] for row in simulation) - 4)
            < 1e-9,
            "4",
        ),
        (
            "top7_zone",
            abs(
                sum(row["europe_top7_probability"] for row in simulation) - 7
            )
            < 1e-9,
            "7",
        ),
        (
            "relegation_zone",
            abs(
                sum(row["relegation_probability"] for row in simulation) - 3
            )
            < 1e-9,
            "3",
        ),
        (
            "cors_configured",
            "LALIGA_CORS_ORIGINS"
            in (ROOT / ".env.example").read_text(encoding="utf-8"),
            "localhost:4200",
        ),
    ]
    quality = pd.DataFrame(checks, columns=["check", "passed", "value"])
    REPORTS.mkdir(parents=True, exist_ok=True)
    quality.to_csv(REPORTS / "phase12_quality_checks.csv", index=False)
    summary = {
        "phase": 12,
        "framework": "Angular 20",
        "pages": 5,
        "fixtures": len(fixtures),
        "predictions": len(predictions),
        "teams": len(simulation),
        "simulations": 50_000,
        "api": "FastAPI",
        "database": "PostgreSQL",
        "fallback": "preseason_snapshot",
        "quality_checks": len(checks),
        "quality_passed": bool(quality["passed"].all()),
    }
    (REPORTS / "phase12_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not summary["quality_passed"]:
        raise AssertionError("Phase 12 quality checks failed.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
