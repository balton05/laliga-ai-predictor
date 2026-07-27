from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.api.main import create_app  # noqa: E402
from laliga_predictor.api.models import (  # noqa: E402
    ModelTrainingRun,
    ModelVersion,
    PredictionEvaluation,
)
from laliga_predictor.api.settings import Settings  # noqa: E402
from laliga_predictor.model_runtime import (  # noqa: E402
    apply_active_model,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'phase15.db'}",
        project_root=tmp_path,
        auto_sync=False,
        automation_enabled=True,
        retraining_minimum_matches=80,
        retraining_minimum_matchdays=8,
    )


def _evaluation(index: int) -> PredictionEvaluation:
    outcomes = ("H", "D", "A")
    actual = outcomes[index % 3]
    probabilities = {
        "H": (0.70, 0.15, 0.15),
        "D": (0.15, 0.70, 0.15),
        "A": (0.15, 0.15, 0.70),
    }[actual]
    played = date(2026, 8, 1) + timedelta(days=index)
    now = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return PredictionEvaluation(
        fixture_id=f"fixture-{index:03d}",
        snapshot_id=f"snapshot-{index:03d}",
        season="2026/27",
        matchday=(index // 10) + 1,
        played_date=played,
        home_team=f"Home {index}",
        away_team=f"Away {index}",
        home_goals=1,
        away_goals=0 if actual == "H" else 1,
        actual_ftr=actual,
        predicted_ftr=actual,
        probability_home=probabilities[0],
        probability_draw=probabilities[1],
        probability_away=probabilities[2],
        correct=True,
        log_loss=float(-np.log(max(probabilities))),
        brier_score=0.135,
        market_predicted_ftr=None,
        market_log_loss=None,
        market_brier_score=None,
        model_version="ensemble-v1-trained-through-2025-26",
        prediction_captured_at_utc=now - timedelta(days=1),
        evaluated_at_utc=now,
    )


def test_registry_bootstraps_and_retraining_waits_for_evidence(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        status = client.get("/models/status")
        versions = client.get("/models")
        retrain = client.post("/models/retrain")

        assert status.status_code == 200
        assert status.json()["active_model"].startswith("ensemble-v1")
        assert status.json()["ready_to_retrain"] is False
        assert versions.status_code == 200
        assert versions.json()[0]["stage"] == "active"
        assert retrain.status_code == 201
        assert retrain.json()["status"] == "not_ready"
        assert retrain.json()["eligible_for_promotion"] is False


def test_challenger_is_versioned_and_requires_explicit_promotion(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        with app.state.session_factory.begin() as session:
            session.add_all([_evaluation(index) for index in range(90)])

        retrain = client.post("/models/retrain")
        assert retrain.status_code == 201
        payload = retrain.json()
        assert payload["status"] == "candidate_ready"
        assert payload["eligible_for_promotion"] is True
        assert payload["candidate_log_loss"] < payload["champion_log_loss"]

        version = payload["candidate_version"]
        denied = client.post(
            f"/models/{version}/promote", json={"confirm": False}
        )
        assert denied.status_code == 422

        promoted = client.post(
            f"/models/{version}/promote", json={"confirm": True}
        )
        assert promoted.status_code == 200
        assert promoted.json()["active_model"] == version

        with app.state.session_factory() as session:
            active = session.scalar(
                select(ModelVersion).where(ModelVersion.stage == "active")
            )
            latest = session.scalar(
                select(ModelTrainingRun).order_by(
                    ModelTrainingRun.started_at_utc.desc()
                )
            )
            assert active.version == version
            assert latest.candidate_version == version

        specification = json.loads(
            (tmp_path / "models" / "active_model.json").read_text()
        )
        assert specification["version"] == version
        assert specification["transformation"] == "temperature"


def test_active_temperature_model_preserves_probability_simplex(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "active_model.json").write_text(
        json.dumps(
            {
                "version": "candidate-test",
                "transformation": "temperature",
                "temperature": 0.8,
                "trained_through": "2026/27-J08",
            }
        )
    )
    frame = __import__("pandas").DataFrame(
        [
            {
                "probability_home": 0.50,
                "probability_draw": 0.30,
                "probability_away": 0.20,
                "predicted_ftr": "H",
                "probability_edge": 0.20,
                "confidence": "medium",
            }
        ]
    )
    transformed, specification = apply_active_model(frame, tmp_path)
    assert np.isclose(
        transformed[
            [
                "probability_home",
                "probability_draw",
                "probability_away",
            ]
        ].sum(axis=1).iloc[0],
        1.0,
    )
    assert specification["version"] == "candidate-test"
    assert transformed["model_version"].iloc[0] == "candidate-test"
