from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import confusion_matrix
from sklearn.pipeline import Pipeline

from .config import PROCESSED_DIR, REPORTS_DIR
from .modeling import (
    CLASS_IDS,
    CLASS_LABELS,
    MARKET_FEATURES,
    SPORT_FEATURES,
    TEST_SEASON,
    VALIDATION_SEASONS,
    evaluate_probabilities,
)


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


RANDOM_FOREST_CONFIGS = [
    {
        "config_id": "rf_depth6_leaf10",
        "n_estimators": 400,
        "max_depth": 6,
        "min_samples_leaf": 10,
        "max_features": "sqrt",
        "class_weight": None,
    },
    {
        "config_id": "rf_depth8_leaf8",
        "n_estimators": 400,
        "max_depth": 8,
        "min_samples_leaf": 8,
        "max_features": "sqrt",
        "class_weight": None,
    },
    {
        "config_id": "rf_depth10_leaf5",
        "n_estimators": 400,
        "max_depth": 10,
        "min_samples_leaf": 5,
        "max_features": 0.50,
        "class_weight": None,
    },
    {
        "config_id": "rf_depth8_balanced",
        "n_estimators": 400,
        "max_depth": 8,
        "min_samples_leaf": 8,
        "max_features": "sqrt",
        "class_weight": "balanced",
    },
]

HIST_BOOST_CONFIGS = [
    {
        "config_id": "hgb_lr003_leaf7",
        "learning_rate": 0.03,
        "max_iter": 250,
        "max_leaf_nodes": 7,
        "min_samples_leaf": 20,
        "l2_regularization": 1.0,
    },
    {
        "config_id": "hgb_lr005_leaf7",
        "learning_rate": 0.05,
        "max_iter": 200,
        "max_leaf_nodes": 7,
        "min_samples_leaf": 25,
        "l2_regularization": 2.0,
    },
    {
        "config_id": "hgb_lr005_leaf15",
        "learning_rate": 0.05,
        "max_iter": 200,
        "max_leaf_nodes": 15,
        "min_samples_leaf": 30,
        "l2_regularization": 5.0,
    },
    {
        "config_id": "hgb_lr010_leaf7",
        "learning_rate": 0.10,
        "max_iter": 140,
        "max_leaf_nodes": 7,
        "min_samples_leaf": 30,
        "l2_regularization": 5.0,
    },
]

PRIOR_BLEND_CANDIDATES = [0.0, 0.05, 0.10, 0.20]

MODEL_SPECS = {
    "random_forest_sports": ("random_forest", SPORT_FEATURES),
    "random_forest_market": ("random_forest", MARKET_FEATURES),
    "hist_boost_sports": ("hist_boost", SPORT_FEATURES),
    "hist_boost_market": ("hist_boost", MARKET_FEATURES),
}


def _clip_probabilities(probabilities: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1.0)
    return values / values.sum(axis=1, keepdims=True)


def _class_prior(frame: pd.DataFrame) -> np.ndarray:
    counts = (
        frame["target_class"]
        .value_counts()
        .reindex(CLASS_IDS, fill_value=0)
        .to_numpy(dtype=float)
    )
    return counts / counts.sum()


def _smooth_probabilities(
    probabilities: np.ndarray,
    prior: np.ndarray,
    weight: float,
) -> np.ndarray:
    smoothed = (1.0 - weight) * probabilities + weight * prior.reshape(1, -1)
    return _clip_probabilities(smoothed)


def _pipeline(family: str, config: dict) -> Pipeline:
    parameters = {key: value for key, value in config.items() if key != "config_id"}
    if family == "random_forest":
        classifier = RandomForestClassifier(
            **parameters,
            random_state=42,
            n_jobs=-1,
        )
    elif family == "hist_boost":
        classifier = HistGradientBoostingClassifier(
            **parameters,
            loss="log_loss",
            random_state=42,
            early_stopping=False,
        )
    else:
        raise ValueError(f"Unknown advanced model family: {family}")

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
            ("classifier", classifier),
        ]
    )


def _prediction_frame(
    evaluation: pd.DataFrame,
    probabilities: np.ndarray,
    model: str,
    split: str,
) -> pd.DataFrame:
    probabilities = _clip_probabilities(probabilities)
    predicted = probabilities.argmax(axis=1)
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
    output["predicted_class"] = predicted
    output["predicted_ftr"] = pd.Series(predicted).map(
        dict(enumerate(CLASS_LABELS))
    ).to_numpy()
    output["correct"] = output["predicted_class"].eq(output["target_class"]).astype(int)
    output["row_log_loss"] = -np.log(
        probabilities[np.arange(len(output)), output["target_class"].to_numpy()]
    )
    return output


def _configs_for_family(family: str) -> list[dict]:
    if family == "random_forest":
        return RANDOM_FOREST_CONFIGS
    if family == "hist_boost":
        return HIST_BOOST_CONFIGS
    raise ValueError(f"Unknown family: {family}")


def _walk_forward_raw(
    data: pd.DataFrame,
    model: str,
    config: dict,
) -> list[dict]:
    family, features = MODEL_SPECS[model]
    folds: list[dict] = []
    for season in VALIDATION_SEASONS:
        evaluation = data[data["season"].eq(season)].copy()
        train = data[data["date"].lt(evaluation["date"].min())].copy()
        pipeline = _pipeline(family, config)
        pipeline.fit(train[features], train["target_class"])
        probabilities = _clip_probabilities(
            pipeline.predict_proba(evaluation[features])
        )
        folds.append(
            {
                "season": season,
                "evaluation": evaluation,
                "probabilities": probabilities,
                "prior": _class_prior(train),
            }
        )
    return folds


def _candidate_search(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict], dict[str, pd.DataFrame]]:
    records: list[dict] = []
    selected: dict[str, dict] = {}
    selected_predictions: dict[str, pd.DataFrame] = {}

    for model, (family, _) in MODEL_SPECS.items():
        candidate_frames: dict[tuple[str, float], pd.DataFrame] = {}
        for config in _configs_for_family(family):
            raw_folds = _walk_forward_raw(data, model, config)
            for prior_blend in PRIOR_BLEND_CANDIDATES:
                pieces: list[pd.DataFrame] = []
                for fold in raw_folds:
                    probabilities = _smooth_probabilities(
                        fold["probabilities"],
                        fold["prior"],
                        prior_blend,
                    )
                    prediction = _prediction_frame(
                        fold["evaluation"],
                        probabilities,
                        model,
                        "validation",
                    )
                    pieces.append(prediction)
                    metrics = evaluate_probabilities(
                        prediction["target_class"],
                        prediction[
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
                            "family": family,
                            "config_id": config["config_id"],
                            "prior_blend": prior_blend,
                            "fold": fold["season"],
                            "rows": len(prediction),
                            **metrics,
                        }
                    )

                combined = pd.concat(pieces, ignore_index=True)
                combined_metrics = evaluate_probabilities(
                    combined["target_class"],
                    combined[
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
                        "family": family,
                        "config_id": config["config_id"],
                        "prior_blend": prior_blend,
                        "fold": "COMBINED",
                        "rows": len(combined),
                        **combined_metrics,
                    }
                )
                candidate_frames[(config["config_id"], prior_blend)] = combined

        model_records = pd.DataFrame(records)
        model_combined = model_records[
            model_records["model"].eq(model)
            & model_records["fold"].eq("COMBINED")
        ].sort_values(
            ["log_loss", "brier_score", "macro_f1"],
            ascending=[True, True, False],
        )
        best = model_combined.iloc[0]
        best_config = next(
            config
            for config in _configs_for_family(family)
            if config["config_id"] == best["config_id"]
        )
        selected[model] = {
            "family": family,
            "features": list(MODEL_SPECS[model][1]),
            "config": best_config,
            "prior_blend": float(best["prior_blend"]),
            "validation_log_loss": float(best["log_loss"]),
        }
        selected_predictions[model] = candidate_frames[
            (str(best["config_id"]), float(best["prior_blend"]))
        ]

    return pd.DataFrame(records), selected, selected_predictions


def _fit_test_models(
    data: pd.DataFrame,
    selected: dict[str, dict],
) -> tuple[pd.DataFrame, dict[str, dict]]:
    train = data[~data["season"].eq(TEST_SEASON)].copy()
    evaluation = data[data["season"].eq(TEST_SEASON)].copy()
    predictions: list[pd.DataFrame] = []
    fitted: dict[str, dict] = {}

    for model, specification in selected.items():
        pipeline = _pipeline(
            specification["family"],
            specification["config"],
        )
        features = specification["features"]
        pipeline.fit(train[features], train["target_class"])
        prior = _class_prior(train)
        probabilities = _smooth_probabilities(
            pipeline.predict_proba(evaluation[features]),
            prior,
            specification["prior_blend"],
        )
        predictions.append(
            _prediction_frame(
                evaluation,
                probabilities,
                model,
                "test",
            )
        )
        fitted[model] = {
            **specification,
            "pipeline": pipeline,
            "prior": prior,
            "trained_through": "2024/25",
        }

    return pd.concat(predictions, ignore_index=True), fitted


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


def _calibration_table(predictions: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    records: list[dict] = []
    edges = np.linspace(0.0, 1.0, bins + 1)
    probability_columns = [
        "probability_home",
        "probability_draw",
        "probability_away",
    ]
    for (split, model), rows in predictions.groupby(["split", "model"], sort=True):
        for class_id, class_label, column in zip(
            CLASS_IDS,
            CLASS_LABELS,
            probability_columns,
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


def _paired_bootstrap_table(
    advanced_predictions: pd.DataFrame,
    baseline_predictions: pd.DataFrame,
    repetitions: int = 5000,
) -> pd.DataFrame:
    baseline_for_model = {
        "random_forest_sports": "logistic_sports",
        "hist_boost_sports": "logistic_sports",
        "random_forest_market": "market",
        "hist_boost_market": "market",
    }
    rng = np.random.default_rng(42)
    records: list[dict] = []
    for split in ("validation", "test"):
        advanced_split = advanced_predictions[
            advanced_predictions["split"].eq(split)
        ]
        baseline_split = baseline_predictions[
            baseline_predictions["split"].eq(split)
        ]
        for model, baseline in baseline_for_model.items():
            advanced_rows = advanced_split[
                advanced_split["model"].eq(model)
            ][["match_id", "row_log_loss"]].rename(
                columns={"row_log_loss": "advanced_row_log_loss"}
            )
            baseline_rows = baseline_split[
                baseline_split["model"].eq(baseline)
            ][["match_id", "row_log_loss"]].rename(
                columns={"row_log_loss": "baseline_row_log_loss"}
            )
            paired = advanced_rows.merge(
                baseline_rows,
                on="match_id",
                validate="one_to_one",
            )
            differences = (
                paired["advanced_row_log_loss"]
                - paired["baseline_row_log_loss"]
            ).to_numpy(dtype=float)
            sample_indices = rng.integers(
                0,
                len(differences),
                size=(repetitions, len(differences)),
            )
            bootstrap_means = differences[sample_indices].mean(axis=1)
            lower, upper = np.quantile(bootstrap_means, [0.025, 0.975])
            records.append(
                {
                    "split": split,
                    "model": model,
                    "baseline": baseline,
                    "rows": len(differences),
                    "mean_log_loss_difference": float(differences.mean()),
                    "ci_95_lower": float(lower),
                    "ci_95_upper": float(upper),
                    "bootstrap_probability_better": float(
                        np.mean(bootstrap_means < 0.0)
                    ),
                    "statistically_clear_improvement": bool(upper < 0.0),
                }
            )
    return pd.DataFrame(records)


def _feature_importances(
    data: pd.DataFrame,
    selected: dict[str, dict],
) -> pd.DataFrame:
    evaluation = data[data["season"].eq("2024/25")].copy()
    train = data[data["date"].lt(evaluation["date"].min())].copy()
    records: list[dict] = []

    for model, specification in selected.items():
        pipeline = _pipeline(
            specification["family"],
            specification["config"],
        )
        features = specification["features"]
        pipeline.fit(train[features], train["target_class"])
        importance = permutation_importance(
            pipeline,
            evaluation[features],
            evaluation["target_class"],
            scoring="neg_log_loss",
            n_repeats=3,
            random_state=42,
            # La importancia es un diagnóstico offline. Un único trabajador
            # evita fallos de loky en contenedores con procesos restringidos
            # sin alterar los modelos ni las predicciones.
            n_jobs=1,
        )
        for feature, mean, std in zip(
            features,
            importance.importances_mean,
            importance.importances_std,
        ):
            records.append(
                {
                    "model": model,
                    "feature": feature,
                    "importance_log_loss": float(mean),
                    "importance_std": float(std),
                }
            )

    output = pd.DataFrame(records)
    output["rank"] = (
        output.groupby("model")["importance_log_loss"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    return output.sort_values(["model", "rank"]).reset_index(drop=True)


def _fit_production_models(
    data: pd.DataFrame,
    selected: dict[str, dict],
) -> dict:
    models: dict[str, dict] = {}
    prior = _class_prior(data)
    for model, specification in selected.items():
        pipeline = _pipeline(
            specification["family"],
            specification["config"],
        )
        features = specification["features"]
        pipeline.fit(data[features], data["target_class"])
        models[model] = {
            **specification,
            "pipeline": pipeline,
            "prior": prior,
            "trained_through": TEST_SEASON,
        }
    return {
        "classes": CLASS_LABELS,
        "selection_metric": "walk_forward_validation_log_loss",
        "trained_through": TEST_SEASON,
        "models": models,
    }


def _fixture_sports_features(fixtures: pd.DataFrame) -> pd.DataFrame:
    output = pd.DataFrame(
        np.nan,
        index=fixtures.index,
        columns=SPORT_FEATURES,
        dtype=float,
    )

    direct = {
        "home_promoted": "home_promoted",
        "away_promoted": "away_promoted",
        "home_segunda_position": "home_segunda_position",
        "away_segunda_position": "away_segunda_position",
        "home_form_ppg_5": "home_form_ppg_5",
        "away_form_ppg_5": "away_form_ppg_5",
        "home_form_win_rate_5": "home_form_win_rate_5",
        "away_form_win_rate_5": "away_form_win_rate_5",
        "home_form_goals_for_avg_5": "home_form_goals_for_avg_5",
        "away_form_goals_for_avg_5": "away_form_goals_for_avg_5",
        "home_form_goals_against_avg_5": "home_form_goals_against_avg_5",
        "away_form_goals_against_avg_5": "away_form_goals_against_avg_5",
        "home_form_shots_on_target_for_avg_5": "home_form_shots_on_target_for_avg_5",
        "away_form_shots_on_target_for_avg_5": "away_form_shots_on_target_for_avg_5",
        "home_form_ppg_10": "home_form_ppg_10",
        "away_form_ppg_10": "away_form_ppg_10",
        "home_form_goals_for_avg_10": "home_form_goals_for_avg_10",
        "away_form_goals_for_avg_10": "away_form_goals_for_avg_10",
        "home_form_goals_against_avg_10": "home_form_goals_against_avg_10",
        "away_form_goals_against_avg_10": "away_form_goals_against_avg_10",
        "home_elo_pre": "home_elo_initial_2026_27",
        "away_elo_pre": "away_elo_initial_2026_27",
        "elo_difference_pre": "elo_difference_preseason",
        "form_ppg_5_difference": "form_ppg_5_difference_preseason",
    }
    for target, source in direct.items():
        output[target] = pd.to_numeric(fixtures[source], errors="coerce")

    for side in ("home", "away"):
        output[f"{side}_division_changed"] = output[f"{side}_promoted"]
        output[f"{side}_season_matches_pre"] = 0.0
        output[f"{side}_form_goal_difference_avg_5"] = (
            output[f"{side}_form_goals_for_avg_5"]
            - output[f"{side}_form_goals_against_avg_5"]
        )
        output[f"{side}_form_goal_difference_avg_10"] = (
            output[f"{side}_form_goals_for_avg_10"]
            - output[f"{side}_form_goals_against_avg_10"]
        )

    output["history_ready_5"] = (
        pd.to_numeric(fixtures["home_form_matches_5"], errors="coerce").ge(5)
        & pd.to_numeric(fixtures["away_form_matches_5"], errors="coerce").ge(5)
    ).astype(float)
    output["history_ready_10"] = (
        pd.to_numeric(fixtures["home_form_matches_10"], errors="coerce").ge(10)
        & pd.to_numeric(fixtures["away_form_matches_10"], errors="coerce").ge(10)
    ).astype(float)

    output["home_venue_ppg_5"] = pd.to_numeric(
        fixtures["home_home_ppg_last_5_home_matches"],
        errors="coerce",
    )
    output["away_venue_ppg_5"] = pd.to_numeric(
        fixtures["away_away_ppg_last_5_away_matches"],
        errors="coerce",
    )
    output["venue_ppg_5_difference"] = (
        output["home_venue_ppg_5"] - output["away_venue_ppg_5"]
    )
    output["form_ppg_10_difference"] = (
        output["home_form_ppg_10"] - output["away_form_ppg_10"]
    )
    output["form_goal_difference_5_difference"] = (
        output["home_form_goal_difference_avg_5"]
        - output["away_form_goal_difference_avg_5"]
    )
    output["form_shots_on_target_5_difference"] = (
        output["home_form_shots_on_target_for_avg_5"]
        - output["away_form_shots_on_target_for_avg_5"]
    )
    output["elo_expected_home"] = 1.0 / (
        1.0
        + 10.0
        ** (
            (
                output["away_elo_pre"]
                - (output["home_elo_pre"] + 60.0)
            )
            / 400.0
        )
    )
    return output


def _fixture_predictions(
    fixtures: pd.DataFrame,
    production: dict,
    sports_champion: str,
) -> pd.DataFrame:
    specification = production["models"][sports_champion]
    features = _fixture_sports_features(fixtures)
    probabilities = _smooth_probabilities(
        specification["pipeline"].predict_proba(
            features[specification["features"]]
        ),
        specification["prior"],
        specification["prior_blend"],
    )
    prediction = probabilities.argmax(axis=1)
    ordered = np.sort(probabilities, axis=1)
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
    output["model"] = sports_champion
    output["probability_home"] = probabilities[:, 0]
    output["probability_draw"] = probabilities[:, 1]
    output["probability_away"] = probabilities[:, 2]
    output["predicted_ftr"] = pd.Series(prediction).map(
        dict(enumerate(CLASS_LABELS))
    ).to_numpy()
    output["probability_edge"] = ordered[:, -1] - ordered[:, -2]
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
    return output


def _write_figures(
    metrics: pd.DataFrame,
    comparison: pd.DataFrame,
    calibration: pd.DataFrame,
    importance: pd.DataFrame,
    fixtures: pd.DataFrame,
) -> list[str]:
    figure_dir = REPORTS_DIR / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    colors = {
        "random_forest_sports": "#0284C7",
        "random_forest_market": "#0EA5E9",
        "hist_boost_sports": "#059669",
        "hist_boost_market": "#10B981",
        "market": "#7C3AED",
        "logistic_sports": "#F59E0B",
        "logistic_market": "#F97316",
        "poisson": "#64748B",
    }

    validation = metrics[metrics["split"].eq("validation")].sort_values("log_loss")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].barh(
        validation["model"],
        validation["log_loss"],
        color=[colors.get(model, "#94A3B8") for model in validation["model"]],
    )
    axes[0].invert_yaxis()
    axes[0].set_title("Modelos avanzados: validación Log Loss")
    axes[0].set_xlabel("Menor es mejor")
    axes[1].barh(
        validation["model"],
        validation["macro_f1"],
        color=[colors.get(model, "#94A3B8") for model in validation["model"]],
    )
    axes[1].invert_yaxis()
    axes[1].set_title("Modelos avanzados: validación Macro F1")
    axes[1].set_xlabel("Mayor es mejor")
    fig.tight_layout()
    path = figure_dir / "18_advanced_validation.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    test = comparison[comparison["split"].eq("test")].sort_values("log_loss")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].barh(
        test["model"],
        test["log_loss"],
        color=[colors.get(model, "#94A3B8") for model in test["model"]],
    )
    axes[0].invert_yaxis()
    axes[0].set_title("Prueba 2025/26: Log Loss")
    axes[0].set_xlabel("Menor es mejor")
    axes[1].barh(
        test["model"],
        test["macro_f1"],
        color=[colors.get(model, "#94A3B8") for model in test["model"]],
    )
    axes[1].invert_yaxis()
    axes[1].set_title("Prueba 2025/26: Macro F1")
    axes[1].set_xlabel("Mayor es mejor")
    fig.tight_layout()
    path = figure_dir / "19_advanced_test.png"
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
            color=colors.get(model, "#64748B"),
        )
    ax.plot([0, 1], [0, 1], linestyle="--", color="#0F172A", label="ideal")
    ax.set_xlabel("Probabilidad media")
    ax.set_ylabel("Frecuencia observada")
    ax.set_title("Calibración avanzada en prueba 2025/26")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = figure_dir / "20_advanced_calibration.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    top = (
        importance.groupby("feature", as_index=False)["importance_log_loss"]
        .mean()
        .sort_values("importance_log_loss", ascending=False)
        .head(15)
        .sort_values("importance_log_loss")
    )
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(top["feature"], top["importance_log_loss"], color="#0F766E")
    ax.set_title("Importancia por permutación en validación 2024/25")
    ax.set_xlabel("Aumento medio de Log Loss al permutar")
    fig.tight_layout()
    path = figure_dir / "21_advanced_feature_importance.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))

    counts = (
        fixtures["predicted_ftr"]
        .value_counts()
        .reindex(CLASS_LABELS, fill_value=0)
    )
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(["Local", "Empate", "Visitante"], counts, color=["#2563EB", "#94A3B8", "#F97316"])
    ax.set_title("Predicción preliminar de los 380 partidos 2026/27")
    ax.set_ylabel("Partidos")
    for index, value in enumerate(counts):
        ax.text(index, value + 3, str(int(value)), ha="center")
    fig.tight_layout()
    path = figure_dir / "22_advanced_fixtures.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR)))
    return files


def _quality_checks(
    candidates: pd.DataFrame,
    selected: dict[str, dict],
    validation: pd.DataFrame,
    test: pd.DataFrame,
    metrics: pd.DataFrame,
    importance: pd.DataFrame,
    fixtures: pd.DataFrame,
    sports_champion: str,
) -> pd.DataFrame:
    probability_columns = [
        "probability_home",
        "probability_draw",
        "probability_away",
    ]
    predictions = pd.concat([validation, test], ignore_index=True)
    values = predictions[probability_columns].to_numpy(dtype=float)
    fixture_values = fixtures[probability_columns].to_numpy(dtype=float)
    checks = [
        ("four_advanced_models", metrics["model"].nunique() == 4),
        ("candidate_configurations", len(candidates[candidates["fold"].eq("COMBINED")]) == 64),
        ("validation_rows_per_model", validation.groupby("model").size().eq(760).all()),
        ("test_rows_per_model", test.groupby("model").size().eq(380).all()),
        ("probabilities_sum_to_one", np.allclose(values.sum(axis=1), 1.0)),
        ("probabilities_are_finite", np.isfinite(values).all()),
        ("probabilities_within_bounds", ((values >= 0.0) & (values <= 1.0)).all()),
        ("test_is_2025_26", test["season"].eq(TEST_SEASON).all()),
        ("validation_seasons_locked", set(validation["season"]) == set(VALIDATION_SEASONS)),
        ("selection_complete", set(selected) == set(MODEL_SPECS)),
        ("feature_importance_complete", importance.groupby("model").size().ge(72).all()),
        ("fixture_predictions_complete", len(fixtures) == 380 and fixtures["fixture_id"].is_unique),
        ("fixture_probabilities_valid", np.allclose(fixture_values.sum(axis=1), 1.0)),
        (
            "fixture_model_is_sports_only",
            sports_champion.endswith("_sports")
            and not fixtures["market_odds_available"].any(),
        ),
    ]
    return pd.DataFrame(
        [{"check": name, "passed": bool(passed)} for name, passed in checks]
    )


def run_phase6() -> dict:
    dataset_path = PROCESSED_DIR / "laliga_model_dataset.csv"
    fixture_path = PROCESSED_DIR / "fixtures_2026_27_preseason_features.csv"
    if not dataset_path.exists() or not fixture_path.exists():
        raise FileNotFoundError("Run Phase 2 before Phase 6.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(dataset_path, parse_dates=["date"]).sort_values(
        ["date", "match_id"]
    )
    fixtures = pd.read_csv(fixture_path)

    candidates, selected, selected_validation = _candidate_search(data)
    validation = pd.concat(selected_validation.values(), ignore_index=True)
    test, fitted = _fit_test_models(data, selected)
    predictions = pd.concat([validation, test], ignore_index=True)
    metrics = _metrics_table(predictions)
    calibration = _calibration_table(predictions)
    confusion = _confusion_table(predictions)
    importance = _feature_importances(data, selected)
    baseline_predictions = pd.concat(
        [
            pd.read_csv(REPORTS_DIR / "model_predictions_validation.csv"),
            pd.read_csv(REPORTS_DIR / "model_predictions_test.csv"),
        ],
        ignore_index=True,
    )
    bootstrap = _paired_bootstrap_table(predictions, baseline_predictions)

    validation_metrics = metrics[metrics["split"].eq("validation")].sort_values(
        ["log_loss", "brier_score", "macro_f1"],
        ascending=[True, True, False],
    )
    advanced_champion = str(validation_metrics.iloc[0]["model"])
    sports_champion = str(
        validation_metrics[validation_metrics["model"].str.endswith("_sports")]
        .iloc[0]["model"]
    )

    production = _fit_production_models(data, selected)
    fixture_predictions = _fixture_predictions(
        fixtures,
        production,
        sports_champion,
    )

    phase5_comparison_path = REPORTS_DIR / "phase5_model_comparison.csv"
    reference = pd.read_csv(phase5_comparison_path)
    keep_reference = reference[
        reference["model"].isin(
            ["market", "logistic_market", "logistic_sports", "poisson"]
        )
    ].copy()
    comparison = pd.concat([keep_reference, metrics], ignore_index=True).sort_values(
        ["split", "log_loss", "brier_score"]
    )

    quality = _quality_checks(
        candidates,
        selected,
        validation,
        test,
        metrics,
        importance,
        fixture_predictions,
        sports_champion,
    )
    figures = _write_figures(
        metrics,
        comparison,
        calibration,
        importance,
        fixture_predictions,
    )

    candidates.to_csv(
        REPORTS_DIR / "advanced_model_candidate_validation.csv",
        index=False,
    )
    metrics.to_csv(REPORTS_DIR / "advanced_model_metrics.csv", index=False)
    comparison.to_csv(
        REPORTS_DIR / "phase6_model_comparison.csv",
        index=False,
    )
    validation.to_csv(
        REPORTS_DIR / "advanced_model_predictions_validation.csv",
        index=False,
    )
    test.to_csv(
        REPORTS_DIR / "advanced_model_predictions_test.csv",
        index=False,
    )
    calibration.to_csv(
        REPORTS_DIR / "advanced_model_calibration.csv",
        index=False,
    )
    confusion.to_csv(
        REPORTS_DIR / "advanced_model_confusion.csv",
        index=False,
    )
    importance.to_csv(
        REPORTS_DIR / "advanced_model_feature_importance.csv",
        index=False,
    )
    bootstrap.to_csv(
        REPORTS_DIR / "advanced_model_bootstrap_comparison.csv",
        index=False,
    )
    fixture_predictions.to_csv(
        PROCESSED_DIR / "fixtures_2026_27_advanced_predictions.csv",
        index=False,
    )
    quality.to_csv(
        REPORTS_DIR / "phase6_quality_checks.csv",
        index=False,
    )

    joblib.dump(
        {
            "classes": CLASS_LABELS,
            "selection_metric": "walk_forward_validation_log_loss",
            "champion": advanced_champion,
            "sports_champion": sports_champion,
            "selected": selected,
            "models": fitted,
            "trained_through": "2024/25",
        },
        REPORTS_DIR / "phase6_fitted_models.joblib",
    )
    joblib.dump(
        {
            **production,
            "champion": advanced_champion,
            "sports_champion": sports_champion,
        },
        REPORTS_DIR / "phase6_production_models.joblib",
    )

    selection = {
        "validation_protocol": [
            {"train": "2016/17–2022/23", "evaluate": "2023/24"},
            {"train": "2016/17–2023/24", "evaluate": "2024/25"},
        ],
        "test_protocol": {
            "train": "2016/17–2024/25",
            "evaluate_once": TEST_SEASON,
        },
        "selection_metric": "combined_walk_forward_log_loss",
        "selected": {
            model: {
                "family": specification["family"],
                "config": specification["config"],
                "prior_blend": specification["prior_blend"],
                "validation_log_loss": specification["validation_log_loss"],
            }
            for model, specification in selected.items()
        },
        "advanced_champion": advanced_champion,
        "sports_champion_for_2026_27": sports_champion,
    }
    (REPORTS_DIR / "advanced_model_selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    test_metrics = metrics[metrics["split"].eq("test")].set_index("model")
    champion_test = test_metrics.loc[advanced_champion]
    sports_test = test_metrics.loc[sports_champion]
    market_test = float(
        comparison[
            comparison["split"].eq("test")
            & comparison["model"].eq("market")
        ]["log_loss"].iloc[0]
    )
    sports_baseline_test = float(
        comparison[
            comparison["split"].eq("test")
            & comparison["model"].eq("logistic_sports")
        ]["log_loss"].iloc[0]
    )
    champion_bootstrap = bootstrap[
        bootstrap["split"].eq("test")
        & bootstrap["model"].eq(advanced_champion)
    ].iloc[0]
    sports_bootstrap = bootstrap[
        bootstrap["split"].eq("test")
        & bootstrap["model"].eq(sports_champion)
    ].iloc[0]
    summary = {
        "quality_passed": bool(quality["passed"].all()),
        "quality_checks": int(len(quality)),
        "advanced_models_evaluated": int(metrics["model"].nunique()),
        "candidate_configurations": int(
            len(candidates[candidates["fold"].eq("COMBINED")])
        ),
        "validation_rows_per_model": 760,
        "test_rows_per_model": 380,
        "advanced_champion": advanced_champion,
        "sports_champion": sports_champion,
        "advanced_champion_validation_log_loss": float(
            validation_metrics.iloc[0]["log_loss"]
        ),
        "advanced_champion_test_log_loss": float(champion_test["log_loss"]),
        "advanced_champion_test_accuracy": float(champion_test["accuracy"]),
        "advanced_champion_test_macro_f1": float(champion_test["macro_f1"]),
        "sports_champion_test_log_loss": float(sports_test["log_loss"]),
        "market_test_log_loss": market_test,
        "sports_baseline_test_log_loss": sports_baseline_test,
        "advanced_champion_beats_market_on_test": bool(
            champion_test["log_loss"] < market_test
        ),
        "sports_champion_beats_sports_baseline_on_test": bool(
            sports_test["log_loss"] < sports_baseline_test
        ),
        "advanced_champion_test_difference_ci_95": [
            float(champion_bootstrap["ci_95_lower"]),
            float(champion_bootstrap["ci_95_upper"]),
        ],
        "advanced_champion_improvement_statistically_clear": bool(
            champion_bootstrap["statistically_clear_improvement"]
        ),
        "sports_champion_test_difference_ci_95": [
            float(sports_bootstrap["ci_95_lower"]),
            float(sports_bootstrap["ci_95_upper"]),
        ],
        "sports_champion_improvement_statistically_clear": bool(
            sports_bootstrap["statistically_clear_improvement"]
        ),
        "fixture_predictions_2026_27": int(len(fixture_predictions)),
        "production_models_trained_through": TEST_SEASON,
        "figures": figures,
    }
    (REPORTS_DIR / "phase6_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
