from __future__ import annotations

import json
from itertools import product
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from .advanced_modeling import _fixture_sports_features
from .config import PROCESSED_DIR, REPORTS_DIR
from .modeling import (
    CLASS_IDS,
    CLASS_LABELS,
    TEST_SEASON,
    VALIDATION_SEASONS,
    evaluate_probabilities,
)


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


PROBABILITY_COLUMNS = [
    "probability_home",
    "probability_draw",
    "probability_away",
]
TEMPERATURE_BOUNDS = (0.60, 1.80)
WEIGHT_STEP = 0.05
BOOTSTRAP_REPETITIONS = 10_000

COMPONENT_SOURCES = {
    "market": "model",
    "logistic_sports": "model",
    "logistic_market": "model",
    "random_forest_sports": "advanced",
    "random_forest_market": "advanced",
    "poisson": "goal",
}
ENSEMBLE_COMPONENTS = {
    "ensemble_sports": [
        "random_forest_sports",
        "logistic_sports",
        "poisson",
    ],
    "ensemble_market": [
        "market",
        "random_forest_market",
        "logistic_market",
        "poisson",
    ],
}
REFERENCE_MODELS = {
    "ensemble_sports": ["random_forest_sports", "logistic_sports"],
    "ensemble_market": ["market", "random_forest_market"],
}


def _clip_probabilities(probabilities: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1.0)
    return values / values.sum(axis=1, keepdims=True)


def _temperature_scale(
    probabilities: np.ndarray,
    temperature: float,
) -> np.ndarray:
    logits = np.log(np.clip(probabilities, 1e-12, 1.0)) / float(temperature)
    logits -= logits.max(axis=1, keepdims=True)
    values = np.exp(logits)
    return _clip_probabilities(values)


def _load_prediction_sources() -> dict[str, dict[str, pd.DataFrame]]:
    file_map = {
        "model": {
            "validation": "model_predictions_validation.csv",
            "test": "model_predictions_test.csv",
        },
        "advanced": {
            "validation": "advanced_model_predictions_validation.csv",
            "test": "advanced_model_predictions_test.csv",
        },
        "goal": {
            "validation": "goal_model_predictions_validation.csv",
            "test": "goal_model_predictions_test.csv",
        },
    }
    sources: dict[str, dict[str, pd.DataFrame]] = {}
    for family, split_files in file_map.items():
        sources[family] = {}
        for split, filename in split_files.items():
            path = REPORTS_DIR / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"Run the earlier phases before Phase 7: {filename} is missing."
                )
            sources[family][split] = pd.read_csv(path)
    return sources


def _component_frame(
    sources: dict[str, dict[str, pd.DataFrame]],
    model: str,
    split: str,
) -> pd.DataFrame:
    family = COMPONENT_SOURCES[model]
    frame = sources[family][split]
    output = frame[frame["model"].eq(model)].copy()
    if output.empty:
        raise ValueError(f"No {split} predictions found for {model}.")
    return output.sort_values("match_id").reset_index(drop=True)


def _validate_alignment(frames: list[pd.DataFrame]) -> None:
    reference = frames[0][["match_id", "target_class"]].reset_index(drop=True)
    for frame in frames[1:]:
        candidate = frame[["match_id", "target_class"]].reset_index(drop=True)
        if not reference.equals(candidate):
            raise ValueError("Component predictions are not aligned by match_id.")


def _select_temperatures(
    sources: dict[str, dict[str, pd.DataFrame]],
) -> tuple[dict[str, float], pd.DataFrame]:
    temperatures: dict[str, float] = {}
    records: list[dict] = []
    for model in COMPONENT_SOURCES:
        validation = _component_frame(sources, model, "validation")
        raw = validation[PROBABILITY_COLUMNS].to_numpy(dtype=float)
        target = validation["target_class"].to_numpy(dtype=int)
        result = minimize_scalar(
            lambda value: evaluate_probabilities(
                target,
                _temperature_scale(raw, value),
            )["log_loss"],
            bounds=TEMPERATURE_BOUNDS,
            method="bounded",
            options={"xatol": 1e-7},
        )
        temperature = float(result.x)
        temperatures[model] = temperature
        for split in ("validation", "test"):
            frame = _component_frame(sources, model, split)
            probabilities = frame[PROBABILITY_COLUMNS].to_numpy(dtype=float)
            target = frame["target_class"].to_numpy(dtype=int)
            raw_metrics = evaluate_probabilities(target, probabilities)
            calibrated_metrics = evaluate_probabilities(
                target,
                _temperature_scale(probabilities, temperature),
            )
            records.append(
                {
                    "model": model,
                    "split": split,
                    "temperature": temperature,
                    "rows": len(frame),
                    "raw_log_loss": raw_metrics["log_loss"],
                    "calibrated_log_loss": calibrated_metrics["log_loss"],
                    "log_loss_change": (
                        calibrated_metrics["log_loss"]
                        - raw_metrics["log_loss"]
                    ),
                    "raw_brier_score": raw_metrics["brier_score"],
                    "calibrated_brier_score": calibrated_metrics["brier_score"],
                    "raw_ece_10_bins": raw_metrics["ece_10_bins"],
                    "calibrated_ece_10_bins": calibrated_metrics["ece_10_bins"],
                }
            )
    return temperatures, pd.DataFrame(records)


def _simplex_weights(component_count: int) -> list[np.ndarray]:
    units = int(round(1.0 / WEIGHT_STEP))
    weights: list[np.ndarray] = []

    def build(position: int, remaining: int, prefix: list[int]) -> None:
        if position == component_count - 1:
            weights.append(
                np.asarray(prefix + [remaining], dtype=float) * WEIGHT_STEP
            )
            return
        for value in range(remaining + 1):
            build(position + 1, remaining - value, prefix + [value])

    build(0, units, [])
    return weights


def _combine_probabilities(
    probability_arrays: list[np.ndarray],
    weights: np.ndarray,
) -> np.ndarray:
    combined = np.zeros_like(probability_arrays[0], dtype=float)
    for weight, probabilities in zip(weights, probability_arrays):
        combined += float(weight) * probabilities
    return _clip_probabilities(combined)


def _select_ensemble_weights(
    sources: dict[str, dict[str, pd.DataFrame]],
    temperatures: dict[str, float],
) -> tuple[dict[str, dict], pd.DataFrame]:
    selections: dict[str, dict] = {}
    records: list[dict] = []
    for ensemble, components in ENSEMBLE_COMPONENTS.items():
        frames = [
            _component_frame(sources, model, "validation")
            for model in components
        ]
        _validate_alignment(frames)
        target = frames[0]["target_class"].to_numpy(dtype=int)
        calibrated = [
            _temperature_scale(
                frame[PROBABILITY_COLUMNS].to_numpy(dtype=float),
                temperatures[model],
            )
            for model, frame in zip(components, frames)
        ]
        best: tuple[float, float, float, np.ndarray] | None = None
        for weights in _simplex_weights(len(components)):
            probabilities = _combine_probabilities(calibrated, weights)
            metrics = evaluate_probabilities(target, probabilities)
            record = {
                "ensemble": ensemble,
                "weight_step": WEIGHT_STEP,
                "rows": len(target),
                **{
                    f"weight_{model}": float(weight)
                    for model, weight in zip(components, weights)
                },
                **metrics,
            }
            records.append(record)
            score = (
                metrics["log_loss"],
                metrics["brier_score"],
                -metrics["macro_f1"],
            )
            if best is None or score < best[:3]:
                best = (*score, weights.copy())

        assert best is not None
        selected_weights = best[3]
        selections[ensemble] = {
            "components": components,
            "weights": {
                model: float(weight)
                for model, weight in zip(components, selected_weights)
            },
            "validation_log_loss": float(best[0]),
            "weight_step": WEIGHT_STEP,
        }
    return selections, pd.DataFrame(records).fillna(0.0)


def _ensemble_prediction_frame(
    sources: dict[str, dict[str, pd.DataFrame]],
    ensemble: str,
    split: str,
    temperatures: dict[str, float],
    selection: dict,
) -> pd.DataFrame:
    components = selection["components"]
    frames = [_component_frame(sources, model, split) for model in components]
    _validate_alignment(frames)
    calibrated = [
        _temperature_scale(
            frame[PROBABILITY_COLUMNS].to_numpy(dtype=float),
            temperatures[model],
        )
        for model, frame in zip(components, frames)
    ]
    weights = np.asarray(
        [selection["weights"][model] for model in components],
        dtype=float,
    )
    probabilities = _combine_probabilities(calibrated, weights)
    predicted = probabilities.argmax(axis=1)
    output = frames[0][
        [
            "match_id",
            "season",
            "date",
            "home_team",
            "away_team",
            "target_ftr",
            "target_class",
        ]
    ].copy()
    output.insert(0, "split", split)
    output.insert(0, "model", ensemble)
    output["probability_home"] = probabilities[:, 0]
    output["probability_draw"] = probabilities[:, 1]
    output["probability_away"] = probabilities[:, 2]
    output["predicted_class"] = predicted
    output["predicted_ftr"] = pd.Series(predicted).map(
        dict(enumerate(CLASS_LABELS))
    ).to_numpy()
    output["correct"] = (
        output["predicted_class"].eq(output["target_class"]).astype(int)
    )
    output["row_log_loss"] = -np.log(
        probabilities[
            np.arange(len(output)),
            output["target_class"].to_numpy(dtype=int),
        ]
    )
    return output


def _metrics_table(
    sources: dict[str, dict[str, pd.DataFrame]],
    ensemble_predictions: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict] = []
    reference_models = [
        "market",
        "random_forest_market",
        "logistic_market",
        "random_forest_sports",
        "logistic_sports",
        "poisson",
    ]
    for split in ("validation", "test"):
        for model in reference_models:
            rows = _component_frame(sources, model, split)
            metrics = evaluate_probabilities(
                rows["target_class"],
                rows[PROBABILITY_COLUMNS].to_numpy(dtype=float),
            )
            records.append(
                {"split": split, "model": model, "rows": len(rows), **metrics}
            )
        for ensemble, rows in ensemble_predictions[
            ensemble_predictions["split"].eq(split)
        ].groupby("model", sort=True):
            metrics = evaluate_probabilities(
                rows["target_class"],
                rows[PROBABILITY_COLUMNS].to_numpy(dtype=float),
            )
            records.append(
                {
                    "split": split,
                    "model": ensemble,
                    "rows": len(rows),
                    **metrics,
                }
            )
    return pd.DataFrame(records).sort_values(
        ["split", "log_loss", "brier_score"],
    ).reset_index(drop=True)


def _calibration_table(
    predictions: pd.DataFrame,
    bins: int = 10,
) -> pd.DataFrame:
    edges = np.linspace(0.0, 1.0, bins + 1)
    records: list[dict] = []
    for (split, model), rows in predictions.groupby(
        ["split", "model"],
        sort=True,
    ):
        for class_id, class_label, column in zip(
            CLASS_IDS,
            CLASS_LABELS,
            PROBABILITY_COLUMNS,
        ):
            predicted = rows[column].to_numpy(dtype=float)
            observed = rows["target_class"].eq(class_id).to_numpy(dtype=float)
            bin_ids = np.clip(np.digitize(predicted, edges[1:-1]), 0, bins - 1)
            for bin_id in range(bins):
                mask = bin_ids == bin_id
                if not mask.any():
                    continue
                records.append(
                    {
                        "split": split,
                        "model": model,
                        "class": class_label,
                        "bin": bin_id + 1,
                        "lower_bound": edges[bin_id],
                        "upper_bound": edges[bin_id + 1],
                        "observations": int(mask.sum()),
                        "mean_probability": float(predicted[mask].mean()),
                        "observed_rate": float(observed[mask].mean()),
                        "calibration_gap": float(
                            observed[mask].mean() - predicted[mask].mean()
                        ),
                    }
                )
    return pd.DataFrame(records)


def _paired_bootstrap(
    sources: dict[str, dict[str, pd.DataFrame]],
    ensemble_predictions: pd.DataFrame,
) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    records: list[dict] = []
    for split in ("validation", "test"):
        split_ensembles = ensemble_predictions[
            ensemble_predictions["split"].eq(split)
        ]
        for ensemble, references in REFERENCE_MODELS.items():
            ensemble_rows = split_ensembles[
                split_ensembles["model"].eq(ensemble)
            ][["match_id", "row_log_loss"]].rename(
                columns={"row_log_loss": "ensemble_row_log_loss"}
            )
            for reference in references:
                reference_rows = _component_frame(
                    sources,
                    reference,
                    split,
                )[["match_id", "row_log_loss"]].rename(
                    columns={"row_log_loss": "reference_row_log_loss"}
                )
                paired = ensemble_rows.merge(
                    reference_rows,
                    on="match_id",
                    validate="one_to_one",
                )
                differences = (
                    paired["ensemble_row_log_loss"]
                    - paired["reference_row_log_loss"]
                ).to_numpy(dtype=float)
                indices = rng.integers(
                    0,
                    len(differences),
                    size=(BOOTSTRAP_REPETITIONS, len(differences)),
                )
                means = differences[indices].mean(axis=1)
                lower, upper = np.quantile(means, [0.025, 0.975])
                records.append(
                    {
                        "split": split,
                        "ensemble": ensemble,
                        "reference": reference,
                        "rows": len(differences),
                        "mean_log_loss_difference": float(differences.mean()),
                        "ci_95_lower": float(lower),
                        "ci_95_upper": float(upper),
                        "bootstrap_probability_better": float(
                            np.mean(means < 0.0)
                        ),
                        "statistically_clear_improvement": bool(upper < 0.0),
                    }
                )
    return pd.DataFrame(records)


def _fixture_component_probabilities(
    temperatures: dict[str, float],
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    fixture_path = PROCESSED_DIR / "fixtures_2026_27_preseason_features.csv"
    advanced_path = (
        PROCESSED_DIR / "fixtures_2026_27_advanced_predictions.csv"
    )
    goal_path = PROCESSED_DIR / "fixtures_2026_27_goal_predictions.csv"
    fixtures = pd.read_csv(fixture_path)
    advanced = pd.read_csv(advanced_path).sort_values("fixture_id").reset_index(
        drop=True
    )
    goal = pd.read_csv(goal_path).sort_values("fixture_id").reset_index(drop=True)
    fixtures = fixtures.sort_values("fixture_id").reset_index(drop=True)
    if not (
        fixtures["fixture_id"].equals(advanced["fixture_id"])
        and fixtures["fixture_id"].equals(goal["fixture_id"])
    ):
        raise ValueError("Fixture prediction sources are not aligned.")

    phase4 = joblib.load(REPORTS_DIR / "phase4_production_models.joblib")
    logistic = phase4["models"]["logistic_sports"]
    sports_features = _fixture_sports_features(fixtures)
    logistic_probabilities = logistic["pipeline"].predict_proba(
        sports_features[logistic["features"]]
    )
    component_probabilities = {
        "random_forest_sports": _temperature_scale(
            advanced[PROBABILITY_COLUMNS].to_numpy(dtype=float),
            temperatures["random_forest_sports"],
        ),
        "logistic_sports": _temperature_scale(
            logistic_probabilities,
            temperatures["logistic_sports"],
        ),
        "poisson": _temperature_scale(
            goal[PROBABILITY_COLUMNS].to_numpy(dtype=float),
            temperatures["poisson"],
        ),
    }
    return fixtures, component_probabilities


def _fixture_predictions(
    temperatures: dict[str, float],
    sports_selection: dict,
) -> pd.DataFrame:
    fixtures, components = _fixture_component_probabilities(temperatures)
    ordered_components = sports_selection["components"]
    weights = np.asarray(
        [
            sports_selection["weights"][model]
            for model in ordered_components
        ],
        dtype=float,
    )
    probabilities = _combine_probabilities(
        [components[model] for model in ordered_components],
        weights,
    )
    prediction = probabilities.argmax(axis=1)
    sorted_probabilities = np.sort(probabilities, axis=1)
    output = fixtures[
        [
            "fixture_id",
            "season",
            "matchday",
            "reference_date",
            "scheduled_date",
            "kickoff_time",
            "home_team_id",
            "home_team_official",
            "away_team_id",
            "away_team_official",
        ]
    ].copy()
    output = output.rename(
        columns={
            "home_team_official": "home_team",
            "away_team_official": "away_team",
        }
    )
    output["model"] = "ensemble_sports"
    output["probability_home"] = probabilities[:, 0]
    output["probability_draw"] = probabilities[:, 1]
    output["probability_away"] = probabilities[:, 2]
    output["predicted_ftr"] = pd.Series(prediction).map(
        dict(enumerate(CLASS_LABELS))
    ).to_numpy()
    output["probability_edge"] = (
        sorted_probabilities[:, -1] - sorted_probabilities[:, -2]
    )
    output["confidence"] = np.select(
        [
            output["probability_edge"].lt(0.08),
            probabilities.max(axis=1) >= 0.60,
        ],
        ["low", "high"],
        default="medium",
    )
    promoted = (
        fixtures["home_promoted"].fillna(0).astype(bool)
        | fixtures["away_promoted"].fillna(0).astype(bool)
    )
    output.loc[promoted, "confidence"] = "low"
    output["market_odds_available"] = False
    output["feature_snapshot"] = "preseason_static"
    output["requires_dynamic_update"] = True
    return output.sort_values(["matchday", "fixture_id"]).reset_index(drop=True)


def _production_package(
    temperatures: dict[str, float],
    selections: dict[str, dict],
) -> dict:
    phase4 = joblib.load(REPORTS_DIR / "phase4_production_models.joblib")
    phase5 = joblib.load(REPORTS_DIR / "phase5_production_models.joblib")
    phase6 = joblib.load(REPORTS_DIR / "phase6_production_models.joblib")
    return {
        "classes": CLASS_LABELS,
        "trained_through": TEST_SEASON,
        "selection_metric": "walk_forward_validation_log_loss",
        "temperatures": temperatures,
        "ensembles": selections,
        "models": {
            "logistic_sports": phase4["models"]["logistic_sports"],
            "random_forest_sports": phase6["models"][
                "random_forest_sports"
            ],
            "poisson": phase5["models"]["poisson"],
        },
        "promoted_overrides": phase5["promoted_overrides"],
        "market_policy": (
            "Use ensemble_market only when current normalized 1X2 market "
            "probabilities are available."
        ),
    }


def _write_figures(
    metrics: pd.DataFrame,
    calibration: pd.DataFrame,
    bootstrap: pd.DataFrame,
    fixtures: pd.DataFrame,
) -> list[str]:
    figure_dir = REPORTS_DIR / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    colors = {
        "ensemble_market": "#7C3AED",
        "ensemble_sports": "#0F766E",
        "market": "#A78BFA",
        "random_forest_market": "#38BDF8",
        "random_forest_sports": "#0284C7",
        "logistic_market": "#FB923C",
        "logistic_sports": "#F59E0B",
        "poisson": "#64748B",
    }
    files: list[str] = []

    test = metrics[metrics["split"].eq("test")].sort_values("log_loss")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(
        test["model"],
        test["log_loss"],
        color=[colors.get(model, "#94A3B8") for model in test["model"]],
    )
    ax.invert_yaxis()
    ax.set_title("Fase 7 — Log Loss en prueba 2025/26")
    ax.set_xlabel("Menor es mejor")
    for index, value in enumerate(test["log_loss"]):
        ax.text(value + 0.001, index, f"{value:.4f}", va="center", fontsize=8)
    fig.tight_layout()
    path = figure_dir / "23_ensemble_test_log_loss.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    fig, ax = plt.subplots(figsize=(7, 6))
    rows = calibration[calibration["split"].eq("test")]
    for model, model_rows in rows.groupby("model", sort=True):
        grouped = model_rows.groupby("bin", as_index=False).agg(
            mean_probability=("mean_probability", "mean"),
            observed_rate=("observed_rate", "mean"),
        )
        ax.plot(
            grouped["mean_probability"],
            grouped["observed_rate"],
            marker="o",
            label=model,
            color=colors[model],
        )
    ax.plot([0, 1], [0, 1], "--", color="#0F172A", label="ideal")
    ax.set_xlabel("Probabilidad media")
    ax.set_ylabel("Frecuencia observada")
    ax.set_title("Calibración de ensembles — prueba 2025/26")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = figure_dir / "24_ensemble_calibration.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    test_bootstrap = bootstrap[bootstrap["split"].eq("test")].copy()
    labels = (
        test_bootstrap["ensemble"]
        + " vs "
        + test_bootstrap["reference"]
    )
    means = test_bootstrap["mean_log_loss_difference"]
    lower = means - test_bootstrap["ci_95_lower"]
    upper = test_bootstrap["ci_95_upper"] - means
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.errorbar(
        means,
        np.arange(len(test_bootstrap)),
        xerr=np.vstack([lower, upper]),
        fmt="o",
        color="#0F766E",
        ecolor="#94A3B8",
        capsize=4,
    )
    ax.axvline(0.0, linestyle="--", color="#DC2626")
    ax.set_yticks(np.arange(len(test_bootstrap)), labels)
    ax.set_xlabel("Diferencia de Log Loss (ensemble − referencia)")
    ax.set_title("Incertidumbre bootstrap en 2025/26")
    fig.tight_layout()
    path = figure_dir / "25_ensemble_bootstrap.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    expected = fixtures[PROBABILITY_COLUMNS].sum()
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(
        ["Local", "Empate", "Visitante"],
        expected,
        color=["#2563EB", "#94A3B8", "#F97316"],
    )
    ax.set_ylabel("Partidos esperados")
    ax.set_title("Ensemble deportivo — temporada 2026/27")
    for index, value in enumerate(expected):
        ax.text(index, value + 2, f"{value:.1f}", ha="center")
    fig.tight_layout()
    path = figure_dir / "26_ensemble_fixtures.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))
    return files


def _quality_checks(
    temperatures: dict[str, float],
    selections: dict[str, dict],
    candidates: pd.DataFrame,
    predictions: pd.DataFrame,
    fixtures: pd.DataFrame,
    bootstrap: pd.DataFrame,
) -> pd.DataFrame:
    values = predictions[PROBABILITY_COLUMNS].to_numpy(dtype=float)
    fixture_values = fixtures[PROBABILITY_COLUMNS].to_numpy(dtype=float)
    expected_candidate_rows = sum(
        len(_simplex_weights(len(components)))
        for components in ENSEMBLE_COMPONENTS.values()
    )
    checks = [
        (
            "six_components_calibrated",
            set(temperatures) == set(COMPONENT_SOURCES),
        ),
        (
            "temperature_bounds_respected",
            all(
                TEMPERATURE_BOUNDS[0] <= value <= TEMPERATURE_BOUNDS[1]
                for value in temperatures.values()
            ),
        ),
        ("two_ensembles_selected", set(selections) == set(ENSEMBLE_COMPONENTS)),
        (
            "ensemble_weights_sum_to_one",
            all(
                np.isclose(sum(spec["weights"].values()), 1.0)
                for spec in selections.values()
            ),
        ),
        (
            "ensemble_weights_non_negative",
            all(
                value >= 0.0
                for spec in selections.values()
                for value in spec["weights"].values()
            ),
        ),
        ("candidate_grid_complete", len(candidates) == expected_candidate_rows),
        (
            "validation_rows_per_ensemble",
            predictions[predictions["split"].eq("validation")]
            .groupby("model")
            .size()
            .eq(760)
            .all(),
        ),
        (
            "test_rows_per_ensemble",
            predictions[predictions["split"].eq("test")]
            .groupby("model")
            .size()
            .eq(380)
            .all(),
        ),
        ("probabilities_sum_to_one", np.allclose(values.sum(axis=1), 1.0)),
        ("probabilities_are_finite", np.isfinite(values).all()),
        ("probabilities_within_bounds", ((values >= 0) & (values <= 1)).all()),
        (
            "test_season_is_2025_26",
            predictions[predictions["split"].eq("test")]["season"]
            .eq(TEST_SEASON)
            .all(),
        ),
        (
            "validation_seasons_locked",
            set(
                predictions[predictions["split"].eq("validation")]["season"]
            )
            == set(VALIDATION_SEASONS),
        ),
        (
            "fixture_predictions_complete",
            len(fixtures) == 380 and fixtures["fixture_id"].is_unique,
        ),
        (
            "fixture_probabilities_valid",
            np.allclose(fixture_values.sum(axis=1), 1.0),
        ),
        (
            "fixture_model_is_sports_only",
            fixtures["model"].eq("ensemble_sports").all()
            and not fixtures["market_odds_available"].any(),
        ),
        (
            "fixtures_require_updates",
            fixtures["requires_dynamic_update"].all(),
        ),
        (
            "bootstrap_complete",
            len(bootstrap)
            == 2
            * sum(len(references) for references in REFERENCE_MODELS.values()),
        ),
    ]
    return pd.DataFrame(
        [{"check": name, "passed": bool(passed)} for name, passed in checks]
    )


def _dashboard_payload(
    metrics: pd.DataFrame,
    component_calibration: pd.DataFrame,
    selections: dict[str, dict],
    calibration: pd.DataFrame,
    bootstrap: pd.DataFrame,
    test_predictions: pd.DataFrame,
    fixtures: pd.DataFrame,
    quality: pd.DataFrame,
    summary: dict,
) -> dict:
    def records(frame: pd.DataFrame) -> list[dict]:
        clean = frame.astype(object).where(pd.notna(frame), None)
        return clean.to_dict(orient="records")

    weights: list[dict] = []
    for ensemble, specification in selections.items():
        for component in specification["components"]:
            weights.append(
                {
                    "ensemble": ensemble,
                    "component": component,
                    "temperature": summary["temperatures"][component],
                    "weight": specification["weights"][component],
                }
            )
    return {
        "summary": summary,
        "metrics": records(metrics),
        "component_calibration": records(component_calibration),
        "weights": weights,
        "calibration": records(calibration),
        "bootstrap": records(bootstrap),
        "test_predictions": records(test_predictions),
        "fixtures": records(fixtures),
        "quality": records(quality),
    }


def run_phase7() -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sources = _load_prediction_sources()
    temperatures, component_calibration = _select_temperatures(sources)
    selections, candidates = _select_ensemble_weights(sources, temperatures)

    validation = pd.concat(
        [
            _ensemble_prediction_frame(
                sources,
                ensemble,
                "validation",
                temperatures,
                selection,
            )
            for ensemble, selection in selections.items()
        ],
        ignore_index=True,
    )
    test = pd.concat(
        [
            _ensemble_prediction_frame(
                sources,
                ensemble,
                "test",
                temperatures,
                selection,
            )
            for ensemble, selection in selections.items()
        ],
        ignore_index=True,
    )
    predictions = pd.concat([validation, test], ignore_index=True)
    metrics = _metrics_table(sources, predictions)
    calibration = _calibration_table(predictions)
    bootstrap = _paired_bootstrap(sources, predictions)
    fixtures = _fixture_predictions(
        temperatures,
        selections["ensemble_sports"],
    )
    production = _production_package(temperatures, selections)
    quality = _quality_checks(
        temperatures,
        selections,
        candidates,
        predictions,
        fixtures,
        bootstrap,
    )
    if not quality["passed"].all():
        failed = quality.loc[~quality["passed"], "check"].tolist()
        raise AssertionError(f"Phase 7 quality checks failed: {failed}")

    figures = _write_figures(metrics, calibration, bootstrap, fixtures)
    market_test = metrics[
        metrics["split"].eq("test") & metrics["model"].eq("market")
    ].iloc[0]
    market_ensemble_test = metrics[
        metrics["split"].eq("test")
        & metrics["model"].eq("ensemble_market")
    ].iloc[0]
    sports_reference_test = metrics[
        metrics["split"].eq("test")
        & metrics["model"].eq("random_forest_sports")
    ].iloc[0]
    sports_ensemble_test = metrics[
        metrics["split"].eq("test")
        & metrics["model"].eq("ensemble_sports")
    ].iloc[0]
    summary = {
        "quality_passed": True,
        "quality_checks": int(len(quality)),
        "components_calibrated": int(len(temperatures)),
        "candidate_weight_combinations": int(len(candidates)),
        "validation_rows_per_ensemble": 760,
        "test_rows_per_ensemble": 380,
        "selection_metric": "combined_walk_forward_log_loss",
        "temperatures": temperatures,
        "sports_ensemble_weights": selections["ensemble_sports"]["weights"],
        "market_ensemble_weights": selections["ensemble_market"]["weights"],
        "sports_ensemble_validation_log_loss": selections[
            "ensemble_sports"
        ]["validation_log_loss"],
        "market_ensemble_validation_log_loss": selections[
            "ensemble_market"
        ]["validation_log_loss"],
        "sports_ensemble_test_log_loss": float(
            sports_ensemble_test["log_loss"]
        ),
        "sports_ensemble_test_accuracy": float(
            sports_ensemble_test["accuracy"]
        ),
        "sports_ensemble_test_macro_f1": float(
            sports_ensemble_test["macro_f1"]
        ),
        "market_ensemble_test_log_loss": float(
            market_ensemble_test["log_loss"]
        ),
        "market_ensemble_test_accuracy": float(
            market_ensemble_test["accuracy"]
        ),
        "market_ensemble_test_macro_f1": float(
            market_ensemble_test["macro_f1"]
        ),
        "market_test_log_loss": float(market_test["log_loss"]),
        "random_forest_sports_test_log_loss": float(
            sports_reference_test["log_loss"]
        ),
        "market_ensemble_beats_market_on_test": bool(
            market_ensemble_test["log_loss"] < market_test["log_loss"]
        ),
        "sports_ensemble_beats_random_forest_on_test": bool(
            sports_ensemble_test["log_loss"]
            < sports_reference_test["log_loss"]
        ),
        "market_improvement_statistically_clear": bool(
            bootstrap[
                bootstrap["split"].eq("test")
                & bootstrap["ensemble"].eq("ensemble_market")
                & bootstrap["reference"].eq("market")
            ]["statistically_clear_improvement"].iloc[0]
        ),
        "sports_improvement_statistically_clear": bool(
            bootstrap[
                bootstrap["split"].eq("test")
                & bootstrap["ensemble"].eq("ensemble_sports")
                & bootstrap["reference"].eq("random_forest_sports")
            ]["statistically_clear_improvement"].iloc[0]
        ),
        "fixture_predictions_2026_27": int(len(fixtures)),
        "expected_home_wins_2026_27": float(
            fixtures["probability_home"].sum()
        ),
        "expected_draws_2026_27": float(fixtures["probability_draw"].sum()),
        "expected_away_wins_2026_27": float(
            fixtures["probability_away"].sum()
        ),
        "production_models_trained_through": TEST_SEASON,
        "figures": figures,
    }

    selection_report = {
        "validation_protocol": [
            {"train": "2016/17–2022/23", "evaluate": "2023/24"},
            {"train": "2016/17–2023/24", "evaluate": "2024/25"},
        ],
        "test_protocol": {
            "parameters_frozen_before_test": True,
            "evaluate_once": TEST_SEASON,
        },
        "temperature_bounds": list(TEMPERATURE_BOUNDS),
        "weight_step": WEIGHT_STEP,
        "selection_metric": "combined_walk_forward_log_loss",
        "temperatures": temperatures,
        "ensembles": selections,
        "fixture_model": "ensemble_sports",
        "market_ensemble_requires_current_odds": True,
    }

    component_calibration.to_csv(
        REPORTS_DIR / "ensemble_component_calibration.csv",
        index=False,
    )
    candidates.to_csv(
        REPORTS_DIR / "ensemble_weight_candidates.csv",
        index=False,
    )
    validation.to_csv(
        REPORTS_DIR / "ensemble_predictions_validation.csv",
        index=False,
    )
    test.to_csv(
        REPORTS_DIR / "ensemble_predictions_test.csv",
        index=False,
    )
    metrics.to_csv(REPORTS_DIR / "ensemble_metrics.csv", index=False)
    calibration.to_csv(
        REPORTS_DIR / "ensemble_calibration.csv",
        index=False,
    )
    bootstrap.to_csv(
        REPORTS_DIR / "ensemble_bootstrap_comparison.csv",
        index=False,
    )
    quality.to_csv(
        REPORTS_DIR / "phase7_quality_checks.csv",
        index=False,
    )
    fixtures.to_csv(
        PROCESSED_DIR / "fixtures_2026_27_ensemble_predictions.csv",
        index=False,
    )
    joblib.dump(production, REPORTS_DIR / "phase7_production_ensemble.joblib")
    (REPORTS_DIR / "ensemble_selection.json").write_text(
        json.dumps(selection_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (REPORTS_DIR / "phase7_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    payload = _dashboard_payload(
        metrics,
        component_calibration,
        selections,
        calibration,
        bootstrap,
        test,
        fixtures,
        quality,
        summary,
    )
    (REPORTS_DIR / "phase7_dashboard_data.json").write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return summary
