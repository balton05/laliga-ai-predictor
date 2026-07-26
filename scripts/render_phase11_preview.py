from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIEW_DIR = PROJECT_ROOT / "powerbi" / "preview_data"
OUTPUT = PROJECT_ROOT / "reports" / "figures" / "31_powerbi_preview.png"

BG = "#0F172A"
PANEL = "#172033"
GRID = "#334155"
TEXT = "#F8FAFC"
MUTED = "#94A3B8"
CYAN = "#38BDF8"
AMBER = "#FBBF24"
RED = "#F43F5E"


def add_card(fig, x: float, y: float, width: float, height: float,
             title: str, value: str, color: str = CYAN) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.006,rounding_size=0.012",
        transform=fig.transFigure,
        facecolor=PANEL,
        edgecolor=GRID,
        linewidth=1,
    )
    fig.patches.append(patch)
    fig.text(x + 0.018, y + height - 0.035, title, color=MUTED,
             fontsize=9, weight="semibold")
    fig.text(x + 0.018, y + 0.032, value, color=color,
             fontsize=21, weight="bold")


def style_axis(axis) -> None:
    axis.set_facecolor(PANEL)
    axis.tick_params(colors=MUTED, labelsize=8)
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.grid(axis="x", color=GRID, linewidth=0.6, alpha=0.5)
    axis.set_axisbelow(True)


def main() -> None:
    simulation = pd.read_csv(PREVIEW_DIR / "simulation_summary.csv")
    fixture = pd.read_csv(PREVIEW_DIR / "next_matchday.csv")
    leader = simulation.sort_values("champion_probability", ascending=False).iloc[0]
    risk = simulation.sort_values("relegation_probability", ascending=False).iloc[0]

    figure = plt.figure(figsize=(16, 9), dpi=120, facecolor=BG)
    figure.text(0.035, 0.945, "LaLiga AI Predictor · 2026/27",
                color=TEXT, fontsize=24, weight="bold")
    figure.text(0.035, 0.912,
                "Resumen de pretemporada · ensemble deportivo · 50,000 simulaciones",
                color=MUTED, fontsize=10)

    add_card(figure, 0.035, 0.79, 0.20, 0.095, "Partidos pendientes",
             f"{len(pd.read_csv(PROJECT_ROOT / 'data/processed/current_predictions_2026_27.csv'))}")
    add_card(figure, 0.255, 0.79, 0.20, 0.095, "Favorito al título",
             str(leader["team"]), AMBER)
    add_card(figure, 0.475, 0.79, 0.20, 0.095, "Probabilidad campeón",
             f"{leader['champion_probability']:.1%}", AMBER)
    add_card(figure, 0.695, 0.79, 0.27, 0.095, "Mayor riesgo de descenso",
             f"{risk['team']} · {risk['relegation_probability']:.1%}", RED)

    champions = simulation.nlargest(7, "champion_probability").sort_values(
        "champion_probability"
    )
    ax1 = figure.add_axes((0.035, 0.39, 0.45, 0.34))
    style_axis(ax1)
    ax1.barh(champions["team"], champions["champion_probability"],
             color=CYAN, height=0.58)
    ax1.set_xlim(0, max(0.60, champions["champion_probability"].max() * 1.12))
    ax1.set_title("Probabilidad de campeón", loc="left",
                  color=TEXT, fontsize=12, weight="bold", pad=14)
    ax1.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    for i, value in enumerate(champions["champion_probability"]):
        ax1.text(value + 0.008, i, f"{value:.1%}", va="center",
                 color=TEXT, fontsize=8)

    relegation = simulation.nlargest(7, "relegation_probability").sort_values(
        "relegation_probability"
    )
    ax2 = figure.add_axes((0.515, 0.39, 0.45, 0.34))
    style_axis(ax2)
    ax2.barh(relegation["team"], relegation["relegation_probability"],
             color=RED, height=0.58)
    ax2.set_xlim(0, max(0.60, relegation["relegation_probability"].max() * 1.12))
    ax2.set_title("Probabilidad de descenso", loc="left",
                  color=TEXT, fontsize=12, weight="bold", pad=14)
    ax2.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    for i, value in enumerate(relegation["relegation_probability"]):
        ax2.text(value + 0.008, i, f"{value:.1%}", va="center",
                 color=TEXT, fontsize=8)

    ax3 = figure.add_axes((0.035, 0.07, 0.93, 0.25))
    ax3.set_facecolor(PANEL)
    ax3.axis("off")
    ax3.set_title("Próxima jornada · probabilidades 1X2",
                  loc="left", color=TEXT, fontsize=12, weight="bold", pad=10)
    table_data = fixture[
        ["home_team", "away_team", "probability_home",
         "probability_draw", "probability_away"]
    ].copy()
    for name in ["probability_home", "probability_draw", "probability_away"]:
        table_data[name] = table_data[name].map(lambda value: f"{value:.1%}")
    table = ax3.table(
        cellText=table_data.values,
        colLabels=["Local", "Visitante", "1", "X", "2"],
        cellLoc="left",
        colLoc="left",
        loc="center",
        colWidths=[0.27, 0.27, 0.12, 0.12, 0.12],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.5)
    table.scale(1, 1.28)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.set_linewidth(0.4)
        cell.set_facecolor("#1E293B" if row == 0 else PANEL)
        cell.get_text().set_color(TEXT if row == 0 else "#E2E8F0")
        if row == 0:
            cell.get_text().set_weight("bold")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, facecolor=BG, bbox_inches="tight")
    plt.close(figure)
    print(OUTPUT)


if __name__ == "__main__":
    main()
