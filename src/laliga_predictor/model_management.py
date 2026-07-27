from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from laliga_predictor.api.models import (
    ModelTrainingRun,
    ModelVersion,
    PredictionEvaluation,
)
from laliga_predictor.model_runtime import (
    DEFAULT_MODEL_VERSION,
    calibrate_probabilities,
    load_active_model,
    write_active_model,
)


OUTCOMES = ("H", "D", "A")
TEMPERATURES = np.round(np.arange(0.70, 1.31, 0.02), 2)
PROMOTION_LOG_LOSS_MARGIN = 0.002
BRIER_TOLERANCE = 0.002
_TRAINING_LOCK = Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _artifact_checksum(project_root: Path) -> str:
    path = project_root / "reports" / "phase7_production_ensemble.joblib"
    if not path.exists():
        return hashlib.sha256(DEFAULT_MODEL_VERSION.encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _historical_metrics(project_root: Path) -> dict[str, float | int | None]:
    path = project_root / "reports" / "ensemble_metrics.csv"
    if not path.exists():
        return {
            "rows": 380,
            "log_loss": None,
            "brier_score": None,
            "accuracy": None,
            "macro_f1": None,
        }
    metrics = pd.read_csv(path)
    row = metrics[
        metrics["split"].eq("test")
        & metrics["model"].eq("ensemble_sports")
    ]
    if row.empty:
        return {
            "rows": 380,
            "log_loss": None,
            "brier_score": None,
            "accuracy": None,
            "macro_f1": None,
        }
    record = row.iloc[0]
    return {
        "rows": int(record["rows"]),
        "log_loss": float(record["log_loss"]),
        "brier_score": float(record["brier_score"]),
        "accuracy": float(record["accuracy"]),
        "macro_f1": float(record["macro_f1"]),
    }


def bootstrap_model_registry(session: Session, project_root: Path) -> None:
    if session.scalar(select(func.count()).select_from(ModelVersion)):
        return
    specification = load_active_model(project_root)
    metrics = _historical_metrics(project_root)
    now = _utcnow()
    session.add(
        ModelVersion(
            version=str(specification["version"]),
            family="ensemble",
            stage="active",
            created_at_utc=now,
            activated_at_utc=now,
            trained_through=str(specification["trained_through"]),
            training_matches=3420,
            validation_matches=int(metrics["rows"] or 380),
            transformation=str(
                specification.get("transformation", "identity")
            ),
            parameters_json=json.dumps(specification, ensure_ascii=False),
            artifact_checksum=_artifact_checksum(project_root),
            validation_log_loss=metrics["log_loss"],
            validation_brier_score=metrics["brier_score"],
            validation_accuracy=metrics["accuracy"],
            validation_macro_f1=metrics["macro_f1"],
            eligible_for_promotion=True,
            parent_version=None,
            training_run_id=None,
            notes=(
                "Campeón inicial validado temporalmente en 2025/26. "
                "Parámetros seleccionados sin observar esa temporada."
            ),
        )
    )
    session.flush()


def active_model(session: Session) -> ModelVersion:
    model = session.scalar(
        select(ModelVersion)
        .where(ModelVersion.stage == "active")
        .order_by(ModelVersion.activated_at_utc.desc())
        .limit(1)
    )
    if model is None:
        raise RuntimeError("No active model is registered.")
    return model


def list_models(session: Session) -> list[ModelVersion]:
    return list(
        session.scalars(
            select(ModelVersion).order_by(
                ModelVersion.created_at_utc.desc(),
                ModelVersion.version,
            )
        )
    )


def list_training_runs(
    session: Session, limit: int = 20
) -> list[ModelTrainingRun]:
    return list(
        session.scalars(
            select(ModelTrainingRun)
            .order_by(ModelTrainingRun.started_at_utc.desc())
            .limit(limit)
        )
    )


def _score(probabilities: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    values = np.clip(probabilities, 1e-15, 1.0)
    target = np.asarray([OUTCOMES.index(item) for item in actual], dtype=int)
    predicted = values.argmax(axis=1)
    one_hot = np.eye(3)[target]
    return {
        "log_loss": float(
            -np.log(values[np.arange(len(values)), target]).mean()
        ),
        "brier_score": float(np.square(values - one_hot).sum(axis=1).mean()),
        "accuracy": float(accuracy_score(target, predicted)),
        "macro_f1": float(
            f1_score(
                target,
                predicted,
                labels=[0, 1, 2],
                average="macro",
                zero_division=0,
            )
        ),
    }


def _training_frame(session: Session) -> pd.DataFrame:
    rows = list(
        session.scalars(
            select(PredictionEvaluation).order_by(
                PredictionEvaluation.played_date,
                PredictionEvaluation.matchday,
                PredictionEvaluation.fixture_id,
            )
        )
    )
    return pd.DataFrame(
        [
            {
                "fixture_id": row.fixture_id,
                "matchday": row.matchday,
                "played_date": row.played_date,
                "actual_ftr": row.actual_ftr,
                "probability_home": row.probability_home,
                "probability_draw": row.probability_draw,
                "probability_away": row.probability_away,
            }
            for row in rows
        ]
    )


class ModelTrainingService:
    """Fit a shadow calibration challenger without touching production."""

    def __init__(
        self,
        project_root: Path,
        session_factory: sessionmaker[Session],
        *,
        minimum_matches: int = 80,
        minimum_matchdays: int = 8,
    ) -> None:
        self.project_root = Path(project_root)
        self.session_factory = session_factory
        self.minimum_matches = minimum_matches
        self.minimum_matchdays = minimum_matchdays

    def run_once(self, trigger: str = "manual") -> ModelTrainingRun:
        if not _TRAINING_LOCK.acquire(blocking=False):
            raise ValueError("Another model training run is already active.")
        started = _utcnow()
        timer = time.perf_counter()
        try:
            with self.session_factory.begin() as session:
                champion = active_model(session)
                frame = _training_frame(session)
                completed_matchdays = (
                    int(frame["matchday"].nunique()) if len(frame) else 0
                )
                run = ModelTrainingRun(
                    run_id=uuid4().hex,
                    trigger=trigger,
                    status="running",
                    started_at_utc=started,
                    finished_at_utc=None,
                    champion_version=champion.version,
                    candidate_version=None,
                    evaluated_matches=len(frame),
                    completed_matchdays=completed_matchdays,
                    minimum_matches=self.minimum_matches,
                    minimum_matchdays=self.minimum_matchdays,
                    train_matches=0,
                    validation_matches=0,
                    champion_log_loss=None,
                    candidate_log_loss=None,
                    log_loss_improvement=None,
                    champion_brier_score=None,
                    candidate_brier_score=None,
                    selected_temperature=None,
                    eligible_for_promotion=False,
                    duration_seconds=None,
                    error_message=None,
                )
                session.add(run)
                if (
                    len(frame) < self.minimum_matches
                    or completed_matchdays < self.minimum_matchdays
                ):
                    run.status = "not_ready"
                    run.finished_at_utc = _utcnow()
                    run.duration_seconds = time.perf_counter() - timer
                    run.error_message = (
                        "Aún no hay una muestra suficiente para entrenar "
                        "un challenger fiable."
                    )
                    return run

                split = max(
                    int(math.floor(len(frame) * 0.70)),
                    len(frame) - max(20, int(len(frame) * 0.30)),
                )
                train = frame.iloc[:split]
                validation = frame.iloc[split:]
                probability_columns = [
                    "probability_home",
                    "probability_draw",
                    "probability_away",
                ]
                train_probabilities = train[probability_columns].to_numpy(
                    dtype=float
                )
                train_actual = train["actual_ftr"].to_numpy()
                candidates = []
                for temperature in TEMPERATURES:
                    metrics = _score(
                        calibrate_probabilities(
                            train_probabilities, float(temperature)
                        ),
                        train_actual,
                    )
                    candidates.append((metrics["log_loss"], temperature))
                selected_temperature = float(min(candidates)[1])

                validation_probabilities = validation[
                    probability_columns
                ].to_numpy(dtype=float)
                validation_actual = validation["actual_ftr"].to_numpy()
                champion_metrics = _score(
                    validation_probabilities, validation_actual
                )
                challenger_metrics = _score(
                    calibrate_probabilities(
                        validation_probabilities, selected_temperature
                    ),
                    validation_actual,
                )
                improvement = (
                    champion_metrics["log_loss"]
                    - challenger_metrics["log_loss"]
                )
                eligible = bool(
                    improvement >= PROMOTION_LOG_LOSS_MARGIN
                    and challenger_metrics["brier_score"]
                    <= champion_metrics["brier_score"] + BRIER_TOLERANCE
                )
                parent_spec = json.loads(champion.parameters_json)
                absolute_temperature = float(
                    parent_spec.get("temperature", 1.0)
                ) * selected_temperature
                trained_through = (
                    f"2026/27-J{int(frame['matchday'].max()):02d}"
                )
                signature = json.dumps(
                    {
                        "parent": champion.version,
                        "temperature": absolute_temperature,
                        "fixtures": frame["fixture_id"].tolist(),
                    },
                    sort_keys=True,
                ).encode()
                checksum = hashlib.sha256(signature).hexdigest()
                version = (
                    f"ensemble-v2-calibrated-through-"
                    f"j{int(frame['matchday'].max()):02d}-"
                    f"{checksum[:8]}"
                )
                candidate = ModelVersion(
                    version=version,
                    family="calibrated_ensemble",
                    stage="candidate" if eligible else "rejected",
                    created_at_utc=_utcnow(),
                    activated_at_utc=None,
                    trained_through=trained_through,
                    training_matches=len(train),
                    validation_matches=len(validation),
                    transformation="temperature",
                    parameters_json=json.dumps(
                        {
                            "version": version,
                            "family": "calibrated_ensemble",
                            "transformation": "temperature",
                            "temperature": absolute_temperature,
                            "trained_through": trained_through,
                        },
                        ensure_ascii=False,
                    ),
                    artifact_checksum=checksum,
                    validation_log_loss=challenger_metrics["log_loss"],
                    validation_brier_score=challenger_metrics["brier_score"],
                    validation_accuracy=challenger_metrics["accuracy"],
                    validation_macro_f1=challenger_metrics["macro_f1"],
                    eligible_for_promotion=eligible,
                    parent_version=champion.version,
                    training_run_id=run.run_id,
                    notes=(
                        "Challenger de calibración entrenado con un bloque "
                        "temporal anterior y evaluado en el bloque posterior."
                    ),
                )
                session.merge(candidate)
                run.status = "candidate_ready" if eligible else "rejected"
                run.candidate_version = version
                run.train_matches = len(train)
                run.validation_matches = len(validation)
                run.champion_log_loss = champion_metrics["log_loss"]
                run.candidate_log_loss = challenger_metrics["log_loss"]
                run.log_loss_improvement = improvement
                run.champion_brier_score = champion_metrics["brier_score"]
                run.candidate_brier_score = challenger_metrics["brier_score"]
                run.selected_temperature = absolute_temperature
                run.eligible_for_promotion = eligible
                run.finished_at_utc = _utcnow()
                run.duration_seconds = time.perf_counter() - timer
                return run
        finally:
            _TRAINING_LOCK.release()


def promotion_readiness(
    session: Session,
    minimum_matches: int,
    minimum_matchdays: int,
) -> dict[str, Any]:
    bootstrap = active_model(session)
    evaluated = int(
        session.scalar(
            select(func.count()).select_from(PredictionEvaluation)
        )
        or 0
    )
    completed_matchdays = int(
        session.scalar(
            select(func.count(func.distinct(PredictionEvaluation.matchday)))
        )
        or 0
    )
    latest = session.scalar(
        select(ModelTrainingRun)
        .order_by(ModelTrainingRun.started_at_utc.desc())
        .limit(1)
    )
    return {
        "active_model": bootstrap.version,
        "active_trained_through": bootstrap.trained_through,
        "evaluated_matches": evaluated,
        "completed_matchdays": completed_matchdays,
        "minimum_matches": minimum_matches,
        "minimum_matchdays": minimum_matchdays,
        "ready_to_retrain": (
            evaluated >= minimum_matches
            and completed_matchdays >= minimum_matchdays
        ),
        "latest_training_run": latest,
    }


def promote_model(
    session: Session,
    project_root: Path,
    version: str,
) -> tuple[ModelVersion, str]:
    candidate = session.get(ModelVersion, version)
    if candidate is None:
        raise LookupError("Model version not found.")
    if not candidate.eligible_for_promotion:
        raise ValueError("The model did not pass the promotion gates.")
    previous = active_model(session)
    if previous.version == candidate.version:
        return candidate, previous.version
    previous.stage = "archived"
    candidate.stage = "active"
    candidate.activated_at_utc = _utcnow()
    specification = json.loads(candidate.parameters_json)
    write_active_model(specification, project_root)
    session.flush()
    return candidate, previous.version
