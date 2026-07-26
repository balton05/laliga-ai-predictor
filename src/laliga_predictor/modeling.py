from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import PROCESSED_DIR, REPORTS_DIR
from .features import CORE_MODEL_FEATURES


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


CLASS_LABELS = ["H", "D", "A"]
CLASS_IDS = [0, 1, 2]
VALIDATION_SEASONS = ["2023/24", "2024/25"]
TEST_SEASON = "2025/26"
LOGISTIC_CANDIDATES = [0.05, 0.20, 1.00, 5.00]

MARKET_PROBABILITY_COLUMNS = [
    "market_probability_home",
    "market_probability_draw",
    "market_probability_away",
]
SPORT_FEATURES = [
    column
    for column in CORE_MODEL_FEATURES
    if not column.startswith("market_")
]
MARKET_FEATURES = SPORT_FEATURES + MARKET_PROBABILITY_COLUMNS


@dataclass
class PredictionResult:
    model: str
    split: str
    frame: pd.DataFrame
    fallback_rows: int = 0


def _clip_probabilities(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1.0)
    return clipped / clipped.sum(axis=1, keepdims=True)


def _frequency_probabilities(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> np.ndarray:
    counts = (
        train["target_class"]
        .value_counts()
        .reindex(CLASS_IDS, fill_value=0)
        .to_numpy(dtype=float)
    )
    probabilities = counts / counts.sum()
    return np.tile(probabilities, (len(evaluation), 1))


def _market_probabilities(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> tuple[np.ndarray, int]:
    probabilities = evaluation[MARKET_PROBABILITY_COLUMNS].to_numpy(dtype=float)
    missing = ~np.isfinite(probabilities).all(axis=1)
    fallback_rows = int(missing.sum())
    if fallback_rows:
        probabilities[missing] = _frequency_probabilities(
            train,
            evaluation.loc[missing],
        )
    return _clip_probabilities(probabilities), fallback_rows


def _logistic_pipeline(features: list[str], c_value: float) -> Pipeline:
    return Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median",
                    add_indicator=True,
                    keep_empty_features=True,
                ),
            ),
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    C=c_value,
                    solver="lbfgs",
                    max_iter=4000,
                    random_state=42,
                ),
            ),
        ]
    )


def _fit_predict_logistic(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    features: list[str],
    c_value: float,
) -> tuple[np.ndarray, Pipeline]:
    pipeline = _logistic_pipeline(features, c_value)
    pipeline.fit(train[features], train["target_class"])
    probabilities = pipeline.predict_proba(evaluation[features])
    return _clip_probabilities(probabilities), pipeline


def _fit_predict_elo(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> tuple[np.ndarray, Pipeline]:
    return _fit_predict_logistic(
        train,
        evaluation,
        ["elo_difference_pre"],
        1.0,
    )


def _brier_multiclass(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    observed = np.eye(3)[y_true]
    return float(np.mean(np.sum((probabilities - observed) ** 2, axis=1)))


def _expected_calibration_error(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    bins: int = 10,
) -> float:
    observed = np.eye(3)[y_true].reshape(-1)
    predicted = probabilities.reshape(-1)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(predicted)
    error = 0.0
    for left, right in zip(edges[:-1], edges[1:]):
        include_right = right == 1.0
        mask = (predicted >= left) & (
            (predicted <= right) if include_right else (predicted < right)
        )
        if mask.any():
            error += (
                mask.sum()
                / total
                * abs(predicted[mask].mean() - observed[mask].mean())
            )
    return float(error)


def evaluate_probabilities(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, float]:
    y_array = np.asarray(y_true, dtype=int)
    probabilities = _clip_probabilities(probabilities)
    prediction = probabilities.argmax(axis=1)
    return {
        "log_loss": float(log_loss(y_array, probabilities, labels=CLASS_IDS)),
        "brier_score": _brier_multiclass(y_array, probabilities),
        "accuracy": float(accuracy_score(y_array, prediction)),
        "macro_f1": float(f1_score(y_array, prediction, average="macro")),
        "ece_10_bins": _expected_calibration_error(y_array, probabilities),
    }


def _prediction_frame(
    evaluation: pd.DataFrame,
    probabilities: np.ndarray,
    model: str,
    split: str,
) -> pd.DataFrame:
    probabilities = _clip_probabilities(probabilities)
    prediction = probabilities.argmax(axis=1)
    output = evaluation[
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
    output.insert(0, "model", model)
    output["probability_home"] = probabilities[:, 0]
    output["probability_draw"] = probabilities[:, 1]
    output["probability_away"] = probabilities[:, 2]
    output["predicted_class"] = prediction
    output["predicted_ftr"] = pd.Series(prediction).map(
        dict(enumerate(CLASS_LABELS))
    ).to_numpy()
    output["correct"] = output["predicted_class"].eq(output["target_class"]).astype(int)
    output["row_log_loss"] = -np.log(
        probabilities[np.arange(len(output)), output["target_class"].to_numpy()]
    )
    return output


def _walk_forward_predictions(
    data: pd.DataFrame,
    model: str,
    *,
    features: list[str] | None = None,
    c_value: float = 1.0,
) -> PredictionResult:
    pieces: list[pd.DataFrame] = []
    fallback_rows = 0

    for season in VALIDATION_SEASONS:
        evaluation = data[data["season"].eq(season)].copy()
        train = data[data["date"].lt(evaluation["date"].min())].copy()

        if model == "historical_frequency":
            probabilities = _frequency_probabilities(train, evaluation)
        elif model == "market":
            probabilities, fallbacks = _market_probabilities(train, evaluation)
            fallback_rows += fallbacks
        elif model == "elo_multinomial":
            probabilities, _ = _fit_predict_elo(train, evaluation)
        elif model.startswith("logistic_"):
            if features is None:
                raise ValueError("Logistic models require a feature list.")
            probabilities, _ = _fit_predict_logistic(
                train,
                evaluation,
                features,
                c_value,
            )
        else:
            raise ValueError(f"Unknown model: {model}")

        pieces.append(
            _prediction_frame(
                evaluation,
                probabilities,
                model,
                "validation",
            )
        )

    return PredictionResult(
        model=model,
        split="validation",
        frame=pd.concat(pieces, ignore_index=True),
        fallback_rows=fallback_rows,
    )


def _candidate_search(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, pd.DataFrame]]:
    records: list[dict] = []
    selected: dict[str, float] = {}
    selected_predictions: dict[str, pd.DataFrame] = {}

    configurations = {
        "logistic_sports": SPORT_FEATURES,
        "logistic_market": MARKET_FEATURES,
    }
    for model, features in configurations.items():
        candidates: dict[float, pd.DataFrame] = {}
        for c_value in LOGISTIC_CANDIDATES:
            result = _walk_forward_predictions(
                data,
                model,
                features=features,
                c_value=c_value,
            )
            candidates[c_value] = result.frame
            for season, season_rows in result.frame.groupby("season", sort=True):
                metrics = evaluate_probabilities(
                    season_rows["target_class"],
                    season_rows[
                        [
                            "probability_home",
                            "probability_draw",
                            "probability_away",
                        ]
                    ].to_numpy(),
                )
                records.append(
                    {
                        "model": model,
                        "c_value": c_value,
                        "fold": season,
                        "train_end_season": (
                            "2022/23" if season == "2023/24" else "2023/24"
                        ),
                        "rows": len(season_rows),
                        **metrics,
                    }
                )

            combined_metrics = evaluate_probabilities(
                result.frame["target_class"],
                result.frame[
                    [
                        "probability_home",
                        "probability_draw",
                        "probability_away",
                    ]
                ].to_numpy(),
            )
            records.append(
                {
                    "model": model,
                    "c_value": c_value,
                    "fold": "COMBINED",
                    "train_end_season": "walk_forward",
                    "rows": len(result.frame),
                    **combined_metrics,
                }
            )

        combined = pd.DataFrame(records)
        model_combined = combined[
            combined["model"].eq(model) & combined["fold"].eq("COMBINED")
        ].sort_values(["log_loss", "brier_score", "macro_f1"], ascending=[True, True, False])
        best_c = float(model_combined.iloc[0]["c_value"])
        selected[model] = best_c
        selected_predictions[model] = candidates[best_c]

    return pd.DataFrame(records), selected, selected_predictions


def _test_predictions(
    data: pd.DataFrame,
    selected_c: dict[str, float],
) -> tuple[list[PredictionResult], dict[str, object]]:
    train = data[~data["season"].eq(TEST_SEASON)].copy()
    evaluation = data[data["season"].eq(TEST_SEASON)].copy()
    results: list[PredictionResult] = []
    fitted: dict[str, object] = {}

    frequency = _frequency_probabilities(train, evaluation)
    results.append(
        PredictionResult(
            "historical_frequency",
            "test",
            _prediction_frame(
                evaluation,
                frequency,
                "historical_frequency",
                "test",
            ),
        )
    )
    fitted["historical_frequency"] = {
        "classes": CLASS_LABELS,
        "probabilities": frequency[0].tolist(),
    }

    market, fallback_rows = _market_probabilities(train, evaluation)
    results.append(
        PredictionResult(
            "market",
            "test",
            _prediction_frame(evaluation, market, "market", "test"),
            fallback_rows=fallback_rows,
        )
    )
    fitted["market"] = {
        "columns": MARKET_PROBABILITY_COLUMNS,
        "fallback_probabilities": _frequency_probabilities(
            train,
            evaluation.iloc[:1],
        )[0].tolist(),
    }

    elo_probabilities, elo_pipeline = _fit_predict_elo(train, evaluation)
    results.append(
        PredictionResult(
            "elo_multinomial",
            "test",
            _prediction_frame(
                evaluation,
                elo_probabilities,
                "elo_multinomial",
                "test",
            ),
        )
    )
    fitted["elo_multinomial"] = elo_pipeline

    for model, features in (
        ("logistic_sports", SPORT_FEATURES),
        ("logistic_market", MARKET_FEATURES),
    ):
        probabilities, pipeline = _fit_predict_logistic(
            train,
            evaluation,
            features,
            selected_c[model],
        )
        results.append(
            PredictionResult(
                model,
                "test",
                _prediction_frame(evaluation, probabilities, model, "test"),
            )
        )
        fitted[model] = {
            "pipeline": pipeline,
            "features": features,
            "c_value": selected_c[model],
        }
    return results, fitted


def _fit_production_models(
    data: pd.DataFrame,
    selected_c: dict[str, float],
) -> dict[str, object]:
    frequency = _frequency_probabilities(data, data.iloc[:1])[0]
    elo_pipeline = _logistic_pipeline(["elo_difference_pre"], 1.0)
    elo_pipeline.fit(data[["elo_difference_pre"]], data["target_class"])

    models: dict[str, object] = {
        "historical_frequency": {
            "classes": CLASS_LABELS,
            "probabilities": frequency.tolist(),
        },
        "market": {
            "columns": MARKET_PROBABILITY_COLUMNS,
            "fallback_probabilities": frequency.tolist(),
        },
        "elo_multinomial": elo_pipeline,
    }
    for model, features in (
        ("logistic_sports", SPORT_FEATURES),
        ("logistic_market", MARKET_FEATURES),
    ):
        pipeline = _logistic_pipeline(features, selected_c[model])
        pipeline.fit(data[features], data["target_class"])
        models[model] = {
            "pipeline": pipeline,
            "features": features,
            "c_value": selected_c[model],
        }
    return {
        "classes": CLASS_LABELS,
        "sport_features": SPORT_FEATURES,
        "market_features": MARKET_FEATURES,
        "selected_c": selected_c,
        "selection_metric": "validation_log_loss",
        "trained_through": TEST_SEASON,
        "models": models,
    }


def _calibration_table(predictions: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    records: list[dict] = []
    edges = np.linspace(0.0, 1.0, bins + 1)

    for (split, model), model_rows in predictions.groupby(
        ["split", "model"],
        sort=True,
    ):
        for class_id, class_label, column in zip(
            CLASS_IDS,
            CLASS_LABELS,
            ["probability_home", "probability_draw", "probability_away"],
        ):
            predicted = model_rows[column].to_numpy(dtype=float)
            observed = model_rows["target_class"].eq(class_id).to_numpy(dtype=float)
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


def _confusion_table(predictions: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for (split, model), rows in predictions.groupby(["split", "model"], sort=True):
        matrix = confusion_matrix(
            rows["target_class"],
            rows["predicted_class"],
            labels=CLASS_IDS,
        )
        for actual_id, actual in enumerate(CLASS_LABELS):
            for predicted_id, predicted in enumerate(CLASS_LABELS):
                records.append(
                    {
                        "split": split,
                        "model": model,
                        "actual": actual,
                        "predicted": predicted,
                        "matches": int(matrix[actual_id, predicted_id]),
                    }
                )
    return pd.DataFrame(records)


def _coefficient_table(fitted: dict[str, object]) -> pd.DataFrame:
    records: list[dict] = []
    for model in ("logistic_sports", "logistic_market"):
        model_info = fitted[model]
        pipeline = model_info["pipeline"]
        features = model_info["features"]
        names = pipeline.named_steps["imputer"].get_feature_names_out(features)
        coefficients = pipeline.named_steps["classifier"].coef_
        for index, feature in enumerate(names):
            values = coefficients[:, index]
            records.append(
                {
                    "model": model,
                    "feature": feature,
                    "coefficient_home": values[0],
                    "coefficient_draw": values[1],
                    "coefficient_away": values[2],
                    "mean_absolute_coefficient": np.abs(values).mean(),
                }
            )
    output = pd.DataFrame(records)
    output["rank"] = (
        output.groupby("model")["mean_absolute_coefficient"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    return output.sort_values(["model", "rank"]).reset_index(drop=True)


def _metrics_table(predictions: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for (split, model), rows in predictions.groupby(["split", "model"], sort=True):
        metrics = evaluate_probabilities(
            rows["target_class"],
            rows[
                ["probability_home", "probability_draw", "probability_away"]
            ].to_numpy(),
        )
        records.append(
            {
                "split": split,
                "model": model,
                "rows": len(rows),
                **metrics,
            }
        )
    return pd.DataFrame(records).sort_values(
        ["split", "log_loss", "brier_score"],
    ).reset_index(drop=True)


def _write_figures(
    metrics: pd.DataFrame,
    calibration: pd.DataFrame,
    confusion: pd.DataFrame,
    coefficients: pd.DataFrame,
    champion: str,
) -> list[str]:
    figure_dir = REPORTS_DIR / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    colors = {
        "historical_frequency": "#94A3B8",
        "market": "#7C3AED",
        "elo_multinomial": "#F59E0B",
        "logistic_sports": "#0EA5E9",
        "logistic_market": "#10B981",
    }

    validation = metrics[metrics["split"].eq("validation")].sort_values("log_loss")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].barh(
        validation["model"],
        validation["log_loss"],
        color=[colors[model] for model in validation["model"]],
    )
    axes[0].invert_yaxis()
    axes[0].set_title("Validación walk-forward: Log Loss")
    axes[0].set_xlabel("Menor es mejor")
    axes[1].barh(
        validation["model"],
        validation["macro_f1"],
        color=[colors[model] for model in validation["model"]],
    )
    axes[1].invert_yaxis()
    axes[1].set_title("Validación walk-forward: Macro F1")
    axes[1].set_xlabel("Mayor es mejor")
    fig.tight_layout()
    path = figure_dir / "08_comparacion_validacion.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    test = metrics[metrics["split"].eq("test")].sort_values("log_loss")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].barh(
        test["model"],
        test["log_loss"],
        color=[colors[model] for model in test["model"]],
    )
    axes[0].invert_yaxis()
    axes[0].set_title("Prueba 2025/26: Log Loss")
    axes[1].barh(
        test["model"],
        test["accuracy"],
        color=[colors[model] for model in test["model"]],
    )
    axes[1].invert_yaxis()
    axes[1].set_title("Prueba 2025/26: Accuracy")
    fig.tight_layout()
    path = figure_dir / "09_comparacion_prueba.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    fig, ax = plt.subplots(figsize=(7, 6))
    test_calibration = calibration[calibration["split"].eq("test")]
    for model, rows in test_calibration.groupby("model", sort=True):
        grouped = rows.groupby("bin", as_index=False).agg(
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
    ax.plot([0, 1], [0, 1], "--", color="#475569", label="calibración perfecta")
    ax.set(xlabel="Probabilidad media", ylabel="Frecuencia observada")
    ax.set_title("Calibración multiclase — prueba 2025/26")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = figure_dir / "10_calibracion_prueba.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    matrix_rows = confusion[
        confusion["split"].eq("test") & confusion["model"].eq(champion)
    ]
    matrix = (
        matrix_rows.pivot(index="actual", columns="predicted", values="matches")
        .reindex(index=CLASS_LABELS, columns=CLASS_LABELS)
        .to_numpy()
    )
    fig, ax = plt.subplots(figsize=(6, 5))
    image = ax.imshow(matrix, cmap="Blues")
    for row in range(3):
        for column in range(3):
            ax.text(column, row, int(matrix[row, column]), ha="center", va="center")
    ax.set_xticks(range(3), CLASS_LABELS)
    ax.set_yticks(range(3), CLASS_LABELS)
    ax.set_xlabel("Predicción")
    ax.set_ylabel("Resultado real")
    ax.set_title(f"Matriz de confusión — {champion}")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    path = figure_dir / "11_matriz_confusion_campeon.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    top = coefficients[
        coefficients["model"].eq("logistic_market")
    ].nsmallest(15, "rank").sort_values("mean_absolute_coefficient")
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(
        top["feature"],
        top["mean_absolute_coefficient"],
        color="#10B981",
    )
    ax.set_title("Regresión logística con mercado: coeficientes dominantes")
    ax.set_xlabel("Promedio del coeficiente absoluto estandarizado")
    fig.tight_layout()
    path = figure_dir / "12_coeficientes_logistic_market.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))
    return files


def _quality_checks(
    validation: pd.DataFrame,
    test: pd.DataFrame,
    metrics: pd.DataFrame,
    selected_c: dict[str, float],
) -> pd.DataFrame:
    probability_columns = [
        "probability_home",
        "probability_draw",
        "probability_away",
    ]
    all_predictions = pd.concat([validation, test], ignore_index=True)
    sums = all_predictions[probability_columns].sum(axis=1)
    values = all_predictions[probability_columns].to_numpy(dtype=float)
    checks = [
        ("validation_rows_per_model", validation.groupby("model").size().eq(760).all()),
        ("test_rows_per_model", test.groupby("model").size().eq(380).all()),
        ("five_models_evaluated", metrics["model"].nunique() == 5),
        ("probabilities_sum_to_one", np.allclose(sums, 1.0, atol=1e-9)),
        ("probabilities_are_finite", np.isfinite(values).all()),
        ("probabilities_within_bounds", ((values >= 0) & (values <= 1)).all()),
        ("all_metrics_are_finite", np.isfinite(metrics.select_dtypes("number")).all().all()),
        ("logistic_c_selected", set(selected_c) == {"logistic_sports", "logistic_market"}),
        ("test_season_is_2025_26", test["season"].eq(TEST_SEASON).all()),
        (
            "validation_is_walk_forward_seasons",
            set(validation["season"]) == set(VALIDATION_SEASONS),
        ),
    ]
    return pd.DataFrame(
        [
            {"check": name, "passed": bool(passed)}
            for name, passed in checks
        ]
    )


def run_phase4() -> dict:
    dataset_path = PROCESSED_DIR / "laliga_model_dataset.csv"
    if not dataset_path.exists():
        raise FileNotFoundError(
            "Run Phase 2 before Phase 4: laliga_model_dataset.csv is missing."
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(dataset_path, parse_dates=["date"]).sort_values(
        ["date", "match_id"]
    )

    candidate_metrics, selected_c, selected_logistic = _candidate_search(data)

    validation_results = [
        _walk_forward_predictions(data, "historical_frequency"),
        _walk_forward_predictions(data, "market"),
        _walk_forward_predictions(data, "elo_multinomial"),
        PredictionResult(
            "logistic_sports",
            "validation",
            selected_logistic["logistic_sports"],
        ),
        PredictionResult(
            "logistic_market",
            "validation",
            selected_logistic["logistic_market"],
        ),
    ]
    validation = pd.concat(
        [result.frame for result in validation_results],
        ignore_index=True,
    )

    test_results, fitted = _test_predictions(data, selected_c)
    test = pd.concat([result.frame for result in test_results], ignore_index=True)
    predictions = pd.concat([validation, test], ignore_index=True)
    metrics = _metrics_table(predictions)

    validation_metrics = metrics[metrics["split"].eq("validation")].sort_values(
        ["log_loss", "brier_score", "macro_f1"],
        ascending=[True, True, False],
    )
    champion = str(validation_metrics.iloc[0]["model"])
    test_champion = metrics[
        metrics["split"].eq("test") & metrics["model"].eq(champion)
    ].iloc[0]

    calibration = _calibration_table(predictions)
    confusion = _confusion_table(predictions)
    coefficients = _coefficient_table(fitted)
    quality = _quality_checks(validation, test, metrics, selected_c)
    figures = _write_figures(
        metrics,
        calibration,
        confusion,
        coefficients,
        champion,
    )

    candidate_metrics.to_csv(
        REPORTS_DIR / "model_candidate_validation.csv",
        index=False,
    )
    metrics.to_csv(REPORTS_DIR / "model_metrics.csv", index=False)
    validation.to_csv(
        REPORTS_DIR / "model_predictions_validation.csv",
        index=False,
    )
    test.to_csv(REPORTS_DIR / "model_predictions_test.csv", index=False)
    calibration.to_csv(REPORTS_DIR / "model_calibration.csv", index=False)
    confusion.to_csv(REPORTS_DIR / "model_confusion.csv", index=False)
    coefficients.to_csv(
        REPORTS_DIR / "logistic_coefficients.csv",
        index=False,
    )
    quality.to_csv(REPORTS_DIR / "phase4_quality_checks.csv", index=False)

    artifact = {
        "classes": CLASS_LABELS,
        "sport_features": SPORT_FEATURES,
        "market_features": MARKET_FEATURES,
        "selected_c": selected_c,
        "selection_metric": "validation_log_loss",
        "champion": champion,
        "trained_through": "2024/25",
        "models": fitted,
    }
    joblib.dump(artifact, REPORTS_DIR / "phase4_fitted_models.joblib")
    joblib.dump(
        _fit_production_models(data, selected_c),
        REPORTS_DIR / "phase4_production_models.joblib",
    )

    selection = {
        "validation_protocol": [
            {
                "train": "2016/17–2022/23",
                "evaluate": "2023/24",
            },
            {
                "train": "2016/17–2023/24",
                "evaluate": "2024/25",
            },
        ],
        "test_protocol": {
            "train": "2016/17–2024/25",
            "evaluate_once": TEST_SEASON,
        },
        "selected_c": selected_c,
        "champion_by_validation_log_loss": champion,
    }
    (REPORTS_DIR / "model_selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "quality_passed": bool(quality["passed"].all()),
        "quality_checks": int(len(quality)),
        "models_evaluated": int(metrics["model"].nunique()),
        "validation_rows_per_model": 760,
        "test_rows_per_model": 380,
        "sport_features": len(SPORT_FEATURES),
        "market_features": len(MARKET_FEATURES),
        "selected_c": selected_c,
        "champion": champion,
        "champion_validation_log_loss": float(
            validation_metrics.iloc[0]["log_loss"]
        ),
        "champion_test_log_loss": float(test_champion["log_loss"]),
        "champion_test_accuracy": float(test_champion["accuracy"]),
        "champion_test_macro_f1": float(test_champion["macro_f1"]),
        "market_fallback_validation_rows": int(
            next(
                result.fallback_rows
                for result in validation_results
                if result.model == "market"
            )
        ),
        "market_fallback_test_rows": int(
            next(result.fallback_rows for result in test_results if result.model == "market")
        ),
        "production_models_trained_through": TEST_SEASON,
        "figures": figures,
    }
    (REPORTS_DIR / "phase4_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
