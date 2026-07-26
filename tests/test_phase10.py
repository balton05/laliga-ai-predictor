from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.api.main import create_app  # noqa: E402
from laliga_predictor.api.settings import Settings  # noqa: E402
from laliga_predictor.dynamic import run_phase9  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory):
    # La Fase 9 incluye una prueba de actualización sintética que modifica las
    # salidas canónicas. Restablecemos explícitamente la fotografía real de
    # pretemporada para que estas pruebas no dependan del orden de ejecución.
    run_phase9(simulations=50_000)
    database = tmp_path_factory.mktemp("phase10") / "api.db"
    settings = Settings(
        database_url=f"sqlite:///{database}",
        project_root=PROJECT_ROOT,
        auto_sync=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_reproduces_phase9_preseason(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "ok",
        "database": "connected",
        "season": "2026/27",
        "latest_update_id": "7f6a923c1a4600d7",
        "fixtures": 380,
        "predictions": 380,
        "completed_matches": 0,
        "simulations": 50_000,
    }


def test_fixture_filters_and_calendar_integrity(client: TestClient) -> None:
    all_fixtures = client.get("/fixtures").json()
    first_matchday = client.get("/fixtures?matchday=1").json()
    barcelona = client.get("/fixtures?team=Barcelona").json()
    assert len(all_fixtures) == 380
    assert len({row["fixture_id"] for row in all_fixtures}) == 380
    assert len(first_matchday) == 10
    assert len(barcelona) == 38
    assert all(row["status"] == "scheduled" for row in all_fixtures)


def test_prediction_probabilities_are_valid(client: TestClient) -> None:
    predictions = client.get("/predictions").json()
    assert len(predictions) == 380
    assert {row["model"] for row in predictions} == {"ensemble_sports"}
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


def test_standings_reproduce_preseason(client: TestClient) -> None:
    standings = client.get("/standings").json()
    assert len(standings) == 20
    assert all(row["played"] == 0 for row in standings)
    assert all(row["points"] == 0 for row in standings)


def test_simulation_zones_reconcile(client: TestClient) -> None:
    simulation = client.get("/simulation").json()
    assert len(simulation) == 20
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
    assert simulation[0]["team"] == "FC Barcelona"
    assert np.isclose(simulation[0]["champion_probability"], 0.53748)


def test_latest_update_is_auditable(client: TestClient) -> None:
    response = client.get("/updates/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["update_id"] == "7f6a923c1a4600d7"
    assert payload["pipeline_mode"] == "preseason_noop"
    assert payload["quality_passed"] is True
    assert payload["remaining_matches"] == 380


def test_openapi_documents_required_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    required = {
        "/health",
        "/fixtures",
        "/predictions",
        "/standings",
        "/simulation",
        "/updates/latest",
        "/update-matchday",
    }
    assert required.issubset(schema["paths"])


def test_update_payload_validation(client: TestClient) -> None:
    empty = client.post("/update-matchday", json={})
    invalid_odds = client.post(
        "/update-matchday",
        json={
            "odds": [
                {
                    "fixture_id": "laliga_102249",
                    "captured_at": "2026-08-15T12:00:00Z",
                    "odds_b365_home": 1.0,
                    "odds_b365_draw": 3.2,
                    "odds_b365_away": 4.2,
                }
            ]
        },
    )
    assert empty.status_code == 422
    assert invalid_odds.status_code == 422
