from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from .config import PROCESSED_DIR, REPORTS_DIR


FIGURES_DIR = REPORTS_DIR / "figures"
MODEL_DATASET = PROCESSED_DIR / "laliga_model_dataset.csv"
MATCHES_MASTER = PROCESSED_DIR / "matches_master.csv"
PROMOTIONS = PROCESSED_DIR / "historical_promotions.csv"

RESULT_ORDER = ["H", "D", "A"]
RESULT_LABELS = {
    "H": "Victoria local",
    "D": "Empate",
    "A": "Victoria visitante",
}
PLOT_COLORS = {
    "H": "#2E7D32",
    "D": "#F9A825",
    "A": "#1565C0",
    "accent": "#7B1FA2",
    "muted": "#607D8B",
    "danger": "#C62828",
}


def _configure_matplotlib() -> None:
    cache_dir = Path(os.environ.get("MPLCONFIGDIR", "/tmp/laliga-matplotlib"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache_dir)
    matplotlib.use("Agg")


_configure_matplotlib()
import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402


def _save_csv(frame: pd.DataFrame, name: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / name
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def _season_summary(matches: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    laliga = matches.loc[matches["division"].eq("SP1")].copy()
    laliga["total_goals"] = laliga["home_goals"] + laliga["away_goals"]
    laliga["home_goal_difference"] = laliga["home_goals"] - laliga["away_goals"]
    laliga["total_shots"] = laliga["home_shots"] + laliga["away_shots"]
    laliga["total_shots_on_target"] = (
        laliga["home_shots_on_target"] + laliga["away_shots_on_target"]
    )

    grouped = laliga.groupby("season", sort=False)
    summary = grouped.agg(
        matches=("match_id", "size"),
        goals=("total_goals", "sum"),
        goals_per_match=("total_goals", "mean"),
        home_goals_per_match=("home_goals", "mean"),
        away_goals_per_match=("away_goals", "mean"),
        home_goal_difference=("home_goal_difference", "mean"),
        shots_per_match=("total_shots", "mean"),
        shots_on_target_per_match=("total_shots_on_target", "mean"),
    ).reset_index()

    result_counts = (
        laliga.groupby(["season", "result"], sort=False)
        .size()
        .unstack(fill_value=0)
        .reindex(columns=RESULT_ORDER, fill_value=0)
    )
    for result in RESULT_ORDER:
        summary[f"{result.lower()}_rate"] = (
            summary["season"].map(result_counts[result]) / summary["matches"]
        )

    market = features[
        [
            "season",
            "market_overround",
            "market_probability_home",
            "market_probability_draw",
            "market_probability_away",
            "target_ftr",
        ]
    ].copy()
    market["market_pick"] = market[
        [
            "market_probability_home",
            "market_probability_draw",
            "market_probability_away",
        ]
    ].idxmax(axis=1).map(
        {
            "market_probability_home": "H",
            "market_probability_draw": "D",
            "market_probability_away": "A",
        }
    )
    market["market_correct"] = market["market_pick"].eq(market["target_ftr"])
    market_summary = market.groupby("season", sort=False).agg(
        market_coverage=("market_overround", lambda x: x.notna().mean()),
        average_overround=("market_overround", "mean"),
        market_accuracy=("market_correct", "mean"),
    )
    summary = summary.merge(market_summary, on="season", how="left")
    return summary


def _scorelines(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    laliga = matches.loc[matches["division"].eq("SP1")].copy()
    laliga["scoreline"] = (
        laliga["home_goals"].astype(str)
        + "-"
        + laliga["away_goals"].astype(str)
    )
    common = (
        laliga["scoreline"]
        .value_counts()
        .rename_axis("scoreline")
        .reset_index(name="matches")
    )
    common["rate"] = common["matches"] / len(laliga)
    common["rank"] = np.arange(1, len(common) + 1)

    capped = laliga.assign(
        home_goals_capped=laliga["home_goals"].clip(upper=5),
        away_goals_capped=laliga["away_goals"].clip(upper=5),
    )
    heatmap = (
        capped.groupby(["home_goals_capped", "away_goals_capped"])
        .size()
        .rename("matches")
        .reset_index()
    )
    heatmap["home_goals_label"] = heatmap["home_goals_capped"].map(
        lambda value: "5+" if value == 5 else str(value)
    )
    heatmap["away_goals_label"] = heatmap["away_goals_capped"].map(
        lambda value: "5+" if value == 5 else str(value)
    )
    return common, heatmap


def _market_calibration(features: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    bins = np.linspace(0.0, 1.0, 11)
    labels = [f"{int(bins[i] * 100)}–{int(bins[i + 1] * 100)}%" for i in range(10)]

    for split_name, split_frame in [
        ("all", features),
        ("train", features.loc[features["temporal_split"].eq("train")]),
        (
            "validation",
            features.loc[features["temporal_split"].eq("validation")],
        ),
        ("test", features.loc[features["temporal_split"].eq("test")]),
    ]:
        stacked = []
        for result, column in zip(
            RESULT_ORDER,
            [
                "market_probability_home",
                "market_probability_draw",
                "market_probability_away",
            ],
        ):
            outcome = pd.DataFrame(
                {
                    "probability": split_frame[column],
                    "observed": split_frame["target_ftr"].eq(result).astype(int),
                }
            )
            stacked.append(outcome)
        calibration = pd.concat(stacked, ignore_index=True).dropna()
        calibration["bin"] = pd.cut(
            calibration["probability"],
            bins=bins,
            labels=labels,
            include_lowest=True,
            right=True,
        )
        grouped = calibration.groupby("bin", observed=False)
        result = grouped.agg(
            predictions=("observed", "size"),
            mean_predicted_probability=("probability", "mean"),
            observed_rate=("observed", "mean"),
        ).reset_index()
        result["calibration_gap"] = (
            result["observed_rate"] - result["mean_predicted_probability"]
        )
        result.insert(0, "split", split_name)
        records.extend(result.to_dict("records"))
    return pd.DataFrame(records)


def _favorite_strategy(features: pd.DataFrame) -> pd.DataFrame:
    frame = features.copy()
    probability_columns = [
        "market_probability_home",
        "market_probability_draw",
        "market_probability_away",
    ]
    odds_columns = ["market_odds_home", "market_odds_draw", "market_odds_away"]
    available = frame[probability_columns + odds_columns].notna().all(axis=1)
    frame = frame.loc[available].copy()
    favorite_index = np.argmax(frame[probability_columns].to_numpy(), axis=1)
    labels = np.array(RESULT_ORDER)
    odds = frame[odds_columns].to_numpy()
    frame["favorite_result"] = labels[favorite_index]
    frame["favorite_odds"] = odds[np.arange(len(frame)), favorite_index]
    frame["favorite_won"] = frame["favorite_result"].eq(frame["target_ftr"])
    frame["flat_profit"] = np.where(
        frame["favorite_won"],
        frame["favorite_odds"] - 1.0,
        -1.0,
    )

    records = []
    for season, season_frame in list(frame.groupby("season", sort=False)) + [
        ("TOTAL", frame)
    ]:
        records.append(
            {
                "season": season,
                "bets": len(season_frame),
                "favorite_hit_rate": season_frame["favorite_won"].mean(),
                "average_favorite_odds": season_frame["favorite_odds"].mean(),
                "flat_profit_units": season_frame["flat_profit"].sum(),
                "roi": season_frame["flat_profit"].mean(),
            }
        )
    return pd.DataFrame(records)


def _promoted_performance(promotions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    completed = promotions.loc[promotions["laliga_played"].notna()].copy()
    completed["points_per_match"] = (
        completed["laliga_points"] / completed["laliga_played"]
    )
    completed["goal_difference_per_match"] = (
        completed["laliga_goal_difference"] / completed["laliga_played"]
    )
    completed["survived_first_season"] = ~completed[
        "relegated_after_first_season"
    ].astype(bool)

    cohort = pd.DataFrame(
        [
            {
                "promoted_team_seasons": len(completed),
                "average_points": completed["laliga_points"].mean(),
                "median_points": completed["laliga_points"].median(),
                "average_goal_difference": completed[
                    "laliga_goal_difference"
                ].mean(),
                "survival_rate": completed["survived_first_season"].mean(),
                "relegation_rate": completed[
                    "relegated_after_first_season"
                ].astype(bool).mean(),
                "with_segunda_statistics": int(
                    completed["has_segunda_statistics"].sum()
                ),
            }
        ]
    )
    return completed, cohort


def _feature_missingness(model: pd.DataFrame) -> pd.DataFrame:
    identifiers = {
        "match_id",
        "season",
        "date",
        "home_team_id",
        "home_team",
        "away_team_id",
        "away_team",
        "target_ftr",
        "target_class",
        "temporal_split",
    }
    records = []
    for split, frame in list(model.groupby("temporal_split", sort=False)) + [
        ("all", model)
    ]:
        for column in model.columns:
            if column in identifiers:
                continue
            records.append(
                {
                    "split": split,
                    "feature": column,
                    "missing_count": int(frame[column].isna().sum()),
                    "missing_rate": frame[column].isna().mean(),
                    "non_missing_count": int(frame[column].notna().sum()),
                }
            )
    return pd.DataFrame(records)


def _eta_squared(values: pd.Series, target: pd.Series) -> float:
    valid = values.notna() & target.notna()
    values = values.loc[valid].astype(float)
    target = target.loc[valid]
    if len(values) < 2 or values.nunique() <= 1:
        return np.nan
    grand_mean = values.mean()
    between = 0.0
    for _, group_values in values.groupby(target):
        between += len(group_values) * (group_values.mean() - grand_mean) ** 2
    total = ((values - grand_mean) ** 2).sum()
    return between / total if total > 0 else np.nan


def _feature_associations(model: pd.DataFrame) -> pd.DataFrame:
    train = model.loc[model["temporal_split"].eq("train")].copy()
    numeric_columns = train.select_dtypes(include=[np.number]).columns
    excluded = {
        "target_class",
        "home_promoted",
        "away_promoted",
        "history_ready_5",
        "history_ready_10",
        "home_division_changed",
        "away_division_changed",
    }
    records = []
    target_score = train["target_ftr"].map({"H": 1.0, "D": 0.5, "A": 0.0})
    for column in numeric_columns:
        if column in excluded:
            continue
        valid = train[column].notna()
        records.append(
            {
                "feature": column,
                "observations": int(valid.sum()),
                "coverage": valid.mean(),
                "eta_squared_1x2": _eta_squared(
                    train[column],
                    train["target_ftr"],
                ),
                "spearman_home_result": train.loc[valid, column].corr(
                    target_score.loc[valid],
                    method="spearman",
                ),
            }
        )
    result = pd.DataFrame(records)
    return result.sort_values(
        ["eta_squared_1x2", "coverage"],
        ascending=[False, False],
    ).reset_index(drop=True)


def _feature_drift(model: pd.DataFrame) -> pd.DataFrame:
    train = model.loc[model["temporal_split"].eq("train")]
    numeric = [
        column
        for column in model.select_dtypes(include=[np.number]).columns
        if column != "target_class"
    ]
    records = []
    for comparison in ("validation", "test"):
        other = model.loc[model["temporal_split"].eq(comparison)]
        for column in numeric:
            train_values = train[column].dropna()
            other_values = other[column].dropna()
            pooled = np.sqrt(
                (train_values.var(ddof=1) + other_values.var(ddof=1)) / 2.0
            )
            smd = (
                (other_values.mean() - train_values.mean()) / pooled
                if pooled and np.isfinite(pooled)
                else np.nan
            )
            records.append(
                {
                    "comparison": comparison,
                    "feature": column,
                    "train_mean": train_values.mean(),
                    "comparison_mean": other_values.mean(),
                    "standardized_mean_difference": smd,
                    "absolute_smd": abs(smd) if np.isfinite(smd) else np.nan,
                    "train_coverage": train_values.size / len(train),
                    "comparison_coverage": other_values.size / len(other),
                }
            )
    return pd.DataFrame(records).sort_values(
        ["comparison", "absolute_smd"],
        ascending=[True, False],
    )


def _correlation_pairs(model: pd.DataFrame) -> pd.DataFrame:
    train = model.loc[model["temporal_split"].eq("train")]
    numeric = train.select_dtypes(include=[np.number]).drop(
        columns=["target_class"],
        errors="ignore",
    )
    correlation = numeric.corr(method="spearman", min_periods=100)
    records = []
    columns = list(correlation.columns)
    for left_index, left in enumerate(columns):
        for right in columns[left_index + 1 :]:
            value = correlation.loc[left, right]
            if pd.notna(value) and abs(value) >= 0.90:
                records.append(
                    {
                        "feature_1": left,
                        "feature_2": right,
                        "spearman_correlation": value,
                        "absolute_correlation": abs(value),
                    }
                )
    if not records:
        return pd.DataFrame(
            columns=[
                "feature_1",
                "feature_2",
                "spearman_correlation",
                "absolute_correlation",
            ]
        )
    return pd.DataFrame(records).sort_values(
        "absolute_correlation",
        ascending=False,
    )


def _write_figures(
    season_summary: pd.DataFrame,
    scoreline_heatmap: pd.DataFrame,
    calibration: pd.DataFrame,
    promoted: pd.DataFrame,
    associations: pd.DataFrame,
    missingness: pd.DataFrame,
) -> list[str]:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    files: list[str] = []

    fig, ax = plt.subplots(figsize=(11, 6))
    bottom = np.zeros(len(season_summary))
    for result in RESULT_ORDER:
        values = season_summary[f"{result.lower()}_rate"].to_numpy()
        ax.bar(
            season_summary["season"],
            values,
            bottom=bottom,
            label=RESULT_LABELS[result],
            color=PLOT_COLORS[result],
        )
        bottom += values
    ax.set_title("Distribución 1X2 por temporada")
    ax.set_ylabel("Proporción de partidos")
    ax.set_ylim(0, 1)
    ax.tick_params(axis="x", rotation=45)
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    fig.tight_layout()
    path = FIGURES_DIR / "01_resultados_por_temporada.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR.parent)))

    fig, ax1 = plt.subplots(figsize=(11, 6))
    ax1.plot(
        season_summary["season"],
        season_summary["goals_per_match"],
        marker="o",
        linewidth=2.2,
        color=PLOT_COLORS["accent"],
        label="Goles por partido",
    )
    ax1.set_ylabel("Goles por partido")
    ax1.tick_params(axis="x", rotation=45)
    ax2 = ax1.twinx()
    ax2.plot(
        season_summary["season"],
        season_summary["home_goal_difference"],
        marker="s",
        linewidth=2.0,
        color=PLOT_COLORS["H"],
        label="Ventaja local (goles)",
    )
    ax2.set_ylabel("Diferencia media local − visitante")
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [line.get_label() for line in lines], loc="best")
    ax1.set_title("Evolución de goles y ventaja de local")
    fig.tight_layout()
    path = FIGURES_DIR / "02_goles_y_ventaja_local.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR.parent)))

    pivot = scoreline_heatmap.pivot(
        index="home_goals_label",
        columns="away_goals_label",
        values="matches",
    ).fillna(0)
    ordered = ["0", "1", "2", "3", "4", "5+"]
    pivot = pivot.reindex(index=ordered, columns=ordered, fill_value=0)
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".0f",
        cmap="Blues",
        cbar_kws={"label": "Partidos"},
        ax=ax,
    )
    ax.set_title("Marcadores de LaLiga 2016/17–2025/26")
    ax.set_xlabel("Goles visitante")
    ax.set_ylabel("Goles local")
    fig.tight_layout()
    path = FIGURES_DIR / "03_matriz_marcadores.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR.parent)))

    overall = calibration.loc[
        calibration["split"].eq("all") & calibration["predictions"].gt(0)
    ]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([0, 1], [0, 1], linestyle="--", color="#9E9E9E", label="Calibración ideal")
    ax.plot(
        overall["mean_predicted_probability"],
        overall["observed_rate"],
        marker="o",
        linewidth=2.2,
        color=PLOT_COLORS["A"],
        label="Mercado 1X2",
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Probabilidad media pronosticada")
    ax.set_ylabel("Frecuencia observada")
    ax.set_title("Calibración histórica de las cuotas")
    ax.legend()
    fig.tight_layout()
    path = FIGURES_DIR / "04_calibracion_mercado.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR.parent)))

    promoted_sorted = promoted.sort_values(
        ["laliga_season", "laliga_points"],
        ascending=[True, False],
    )
    colors = np.where(
        promoted_sorted["relegated_after_first_season"].astype(bool),
        PLOT_COLORS["danger"],
        PLOT_COLORS["H"],
    )
    labels = (
        promoted_sorted["team"]
        + " "
        + promoted_sorted["laliga_season"].astype(str)
    )
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.barh(labels, promoted_sorted["laliga_points"], color=colors)
    ax.axvline(40, color="#424242", linestyle="--", linewidth=1.5, label="Referencia: 40 puntos")
    ax.invert_yaxis()
    ax.set_xlabel("Puntos en la primera temporada tras ascender")
    ax.set_title("Rendimiento histórico de los ascendidos")
    ax.legend()
    fig.tight_layout()
    path = FIGURES_DIR / "05_rendimiento_ascendidos.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR.parent)))

    top = associations.dropna(subset=["eta_squared_1x2"]).head(15).sort_values(
        "eta_squared_1x2"
    )
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(top["feature"], top["eta_squared_1x2"], color=PLOT_COLORS["accent"])
    ax.set_xlabel("Eta² frente al resultado 1X2")
    ax.set_title("Variables con mayor asociación en entrenamiento")
    fig.tight_layout()
    path = FIGURES_DIR / "06_asociacion_variables.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR.parent)))

    missing_all = (
        missingness.loc[missingness["split"].eq("all")]
        .sort_values("missing_rate", ascending=False)
        .head(15)
        .sort_values("missing_rate")
    )
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(
        missing_all["feature"],
        missing_all["missing_rate"],
        color=PLOT_COLORS["muted"],
    )
    ax.set_xlim(0, 1)
    ax.set_xlabel("Proporción ausente")
    ax.set_title("Variables recomendadas con mayor ausencia")
    fig.tight_layout()
    path = FIGURES_DIR / "07_datos_faltantes.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    files.append(str(path.relative_to(REPORTS_DIR.parent)))
    return files


def _quality_checks(
    model: pd.DataFrame,
    season_summary: pd.DataFrame,
    calibration: pd.DataFrame,
    figures: list[str],
) -> pd.DataFrame:
    market_columns = [
        "market_probability_home",
        "market_probability_draw",
        "market_probability_away",
    ]
    complete_market = model[market_columns].notna().all(axis=1)
    market_sum_ok = np.allclose(
        model.loc[complete_market, market_columns].sum(axis=1),
        1.0,
        atol=1e-9,
    )
    checks = [
        ("laliga_rows", len(model) == 3800, len(model), 3800),
        ("seasons", len(season_summary) == 10, len(season_summary), 10),
        (
            "matches_per_season",
            season_summary["matches"].eq(380).all(),
            int(season_summary["matches"].min()),
            380,
        ),
        (
            "unique_match_ids",
            model["match_id"].is_unique,
            model["match_id"].nunique(),
            len(model),
        ),
        (
            "target_complete",
            model["target_ftr"].isin(RESULT_ORDER).all(),
            int(model["target_ftr"].isin(RESULT_ORDER).sum()),
            len(model),
        ),
        (
            "market_probabilities_sum_one",
            market_sum_ok,
            float(
                model.loc[complete_market, market_columns]
                .sum(axis=1)
                .sub(1.0)
                .abs()
                .max()
            ),
            0.0,
        ),
        (
            "temporal_test_locked",
            model.loc[
                model["season"].eq("2025/26"),
                "temporal_split",
            ].eq("test").all(),
            int(
                model.loc[
                    model["season"].eq("2025/26"),
                    "temporal_split",
                ].eq("test").sum()
            ),
            380,
        ),
        (
            "calibration_has_predictions",
            calibration["predictions"].sum() > 0,
            int(calibration["predictions"].sum()),
            "> 0",
        ),
        (
            "figures_created",
            all((REPORTS_DIR.parent / path).exists() for path in figures),
            len(figures),
            7,
        ),
    ]
    return pd.DataFrame(
        checks,
        columns=["check", "passed", "observed", "expected"],
    )


def run_phase3() -> dict:
    matches = pd.read_csv(MATCHES_MASTER)
    model = pd.read_csv(MODEL_DATASET)
    features = pd.read_csv(PROCESSED_DIR / "laliga_match_features.csv")
    promotions = pd.read_csv(PROMOTIONS)

    season_summary = _season_summary(matches, features)
    common_scorelines, scoreline_heatmap = _scorelines(matches)
    calibration = _market_calibration(features)
    favorite_strategy = _favorite_strategy(features)
    promoted, promoted_cohort = _promoted_performance(promotions)
    missingness = _feature_missingness(model)
    associations = _feature_associations(model)
    drift = _feature_drift(model)
    correlation_pairs = _correlation_pairs(model)

    _save_csv(season_summary, "eda_season_summary.csv")
    _save_csv(common_scorelines, "eda_common_scorelines.csv")
    _save_csv(scoreline_heatmap, "eda_scoreline_heatmap.csv")
    _save_csv(calibration, "eda_market_calibration.csv")
    _save_csv(favorite_strategy, "eda_favorite_strategy.csv")
    _save_csv(promoted, "eda_promoted_performance.csv")
    _save_csv(promoted_cohort, "eda_promoted_cohort_summary.csv")
    _save_csv(missingness, "eda_feature_missingness.csv")
    _save_csv(associations, "eda_feature_associations_train.csv")
    _save_csv(drift, "eda_feature_drift.csv")
    _save_csv(correlation_pairs, "eda_high_correlation_pairs.csv")

    figures = _write_figures(
        season_summary,
        scoreline_heatmap,
        calibration,
        promoted,
        associations,
        missingness,
    )
    quality = _quality_checks(model, season_summary, calibration, figures)
    _save_csv(quality, "phase3_quality_checks.csv")

    overall_favorite = favorite_strategy.loc[
        favorite_strategy["season"].eq("TOTAL")
    ].iloc[0]
    overall_results = model["target_ftr"].value_counts(normalize=True)
    summary = {
        "phase": 3,
        "status": "completed" if quality["passed"].all() else "failed",
        "quality_passed": bool(quality["passed"].all()),
        "laliga_matches": int(len(model)),
        "seasons": int(model["season"].nunique()),
        "home_win_rate": float(overall_results.get("H", 0.0)),
        "draw_rate": float(overall_results.get("D", 0.0)),
        "away_win_rate": float(overall_results.get("A", 0.0)),
        "goals_per_match": float(
            season_summary["goals"].sum() / season_summary["matches"].sum()
        ),
        "promoted_team_seasons": int(len(promoted)),
        "promoted_survival_rate": float(
            promoted_cohort.iloc[0]["survival_rate"]
        ),
        "favorite_hit_rate": float(overall_favorite["favorite_hit_rate"]),
        "favorite_flat_roi": float(overall_favorite["roi"]),
        "high_correlation_pairs": int(len(correlation_pairs)),
        "figures": figures,
        "methodological_guardrail": (
            "Las asociaciones de variables se calculan solo con entrenamiento. "
            "La prueba 2025/26 permanece bloqueada para decisiones de modelado."
        ),
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with (REPORTS_DIR / "phase3_summary.json").open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    return summary
