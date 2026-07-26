from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.api.main import create_app  # noqa: E402
from laliga_predictor.api.settings import Settings  # noqa: E402


DEMO = PROJECT_ROOT / "frontend" / "public" / "assets" / "demo"


def load(name: str):
    return json.loads((DEMO / name).read_text(encoding="utf-8"))


def test_angular_project_is_complete() -> None:
    frontend = PROJECT_ROOT / "frontend"
    required = [
        frontend / "package.json",
        frontend / "angular.json",
        frontend / "src" / "main.ts",
        frontend / "src" / "styles.scss",
        frontend / "src" / "app" / "app.component.ts",
        frontend / "src" / "app" / "data.service.ts",
    ]
    assert all(path.is_file() for path in required)
    package = json.loads((frontend / "package.json").read_text())
    assert package["dependencies"]["@angular/core"].startswith("20.")


def test_required_web_routes_are_declared() -> None:
    routes = (
        PROJECT_ROOT / "frontend" / "src" / "app" / "app.routes.ts"
    ).read_text(encoding="utf-8")
    for route in [
        "pronosticos",
        "calendario",
        "clasificacion",
        "simulacion",
    ]:
        assert f"path: '{route}'" in routes


def test_demo_snapshot_reproduces_operational_state() -> None:
    fixtures = load("fixtures.json")
    predictions = load("predictions.json")
    standings = load("standings.json")
    simulation = load("simulation.json")
    health = load("health.json")
    assert len(fixtures) == 380
    assert len(predictions) == 380
    assert len(standings) == 20
    assert len(simulation) == 20
    assert health["simulations"] == 50_000
    assert len({row["fixture_id"] for row in fixtures}) == 380


def test_demo_probability_contracts_are_valid() -> None:
    predictions = load("predictions.json")
    probabilities = np.asarray(
        [
            [
                row["probability_home"],
                row["probability_draw"],
                row["probability_away"],
            ]
            for row in predictions
        ]
    )
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert np.logical_and(probabilities >= 0, probabilities <= 1).all()
    assert {row["model"] for row in predictions} == {"ensemble_sports"}


def test_demo_simulation_zones_reconcile() -> None:
    simulation = load("simulation.json")
    assert np.isclose(
        sum(row["champion_probability"] for row in simulation), 1.0
    )
    assert np.isclose(
        sum(row["top4_probability"] for row in simulation), 4.0
    )
    assert np.isclose(
        sum(row["europe_top7_probability"] for row in simulation), 7.0
    )
    assert np.isclose(
        sum(row["relegation_probability"] for row in simulation), 3.0
    )


def test_demo_snapshot_keeps_preseason_champion() -> None:
    simulation = sorted(
        load("simulation.json"),
        key=lambda row: row["champion_probability"],
        reverse=True,
    )
    assert simulation[0]["team"] == "FC Barcelona"
    assert np.isclose(simulation[0]["champion_probability"], 0.53748)


def test_cors_allows_angular_development_origin(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'phase12.db'}",
        project_root=PROJECT_ROOT,
        auto_sync=False,
    )
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:4200",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://localhost:4200"
    )


def test_cors_rejects_unconfigured_origin(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'phase12_reject.db'}",
        project_root=PROJECT_ROOT,
        auto_sync=False,
    )
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in response.headers


def test_frontend_documents_data_source_state() -> None:
    service = (
        PROJECT_ROOT / "frontend" / "src" / "app" / "data.service.ts"
    ).read_text(encoding="utf-8")
    shell = (
        PROJECT_ROOT / "frontend" / "src" / "app" / "app.component.ts"
    ).read_text(encoding="utf-8")
    assert "API en línea" in service
    assert "Datos de pretemporada" in service
    assert "modeLabel()" in shell
