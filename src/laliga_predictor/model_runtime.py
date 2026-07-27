from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import PROJECT_ROOT


DEFAULT_MODEL_VERSION = "ensemble-v1-trained-through-2025-26"
DEFAULT_SPEC: dict[str, Any] = {
    "version": DEFAULT_MODEL_VERSION,
    "family": "ensemble",
    "transformation": "identity",
    "temperature": 1.0,
    "trained_through": "2025/26",
}
PROBABILITY_COLUMNS = [
    "probability_home",
    "probability_draw",
    "probability_away",
]


def active_model_path(project_root: Path = PROJECT_ROOT) -> Path:
    return Path(project_root) / "models" / "active_model.json"


def load_active_model(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    path = active_model_path(project_root)
    if not path.exists():
        return dict(DEFAULT_SPEC)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {**DEFAULT_SPEC, **payload}


def write_active_model(
    specification: dict[str, Any],
    project_root: Path = PROJECT_ROOT,
) -> Path:
    path = active_model_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(specification, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def active_model_version(project_root: Path = PROJECT_ROOT) -> str:
    return str(load_active_model(project_root)["version"])


def calibrate_probabilities(
    probabilities: np.ndarray,
    temperature: float,
) -> np.ndarray:
    values = np.clip(np.asarray(probabilities, dtype=float), 1e-15, 1.0)
    scaled = np.exp(np.log(values) / float(temperature))
    return scaled / scaled.sum(axis=1, keepdims=True)


def apply_active_model(
    predictions: pd.DataFrame,
    project_root: Path = PROJECT_ROOT,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    specification = load_active_model(project_root)
    output = predictions.copy()
    if output.empty:
        return output, specification

    transformation = str(specification.get("transformation", "identity"))
    if transformation == "temperature":
        calibrated = calibrate_probabilities(
            output[PROBABILITY_COLUMNS].to_numpy(dtype=float),
            float(specification["temperature"]),
        )
        output.loc[:, PROBABILITY_COLUMNS] = calibrated
    elif transformation != "identity":
        raise ValueError(
            f"Unsupported active model transformation: {transformation}"
        )

    values = output[PROBABILITY_COLUMNS].to_numpy(dtype=float)
    outcomes = np.asarray(["H", "D", "A"])
    order = np.argsort(values, axis=1)
    output["predicted_ftr"] = outcomes[values.argmax(axis=1)]
    output["probability_edge"] = (
        values[np.arange(len(values)), order[:, -1]]
        - values[np.arange(len(values)), order[:, -2]]
    )
    if "confidence" in output:
        output["confidence"] = pd.cut(
            values.max(axis=1),
            bins=[0.0, 0.45, 0.60, 1.0],
            labels=["low", "medium", "high"],
            include_lowest=True,
        ).astype(str)
    output["model_version"] = str(specification["version"])
    return output, specification
