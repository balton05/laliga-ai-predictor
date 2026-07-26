from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POWERBI_ROOT = PROJECT_ROOT / "powerbi" / "LaLigaAIPredictor"
REPORT_DIR = POWERBI_ROOT / "LaLigaAIPredictor.Report"
MODEL_PATH = (
    POWERBI_ROOT / "LaLigaAIPredictor.SemanticModel" / "model.bim"
)


def test_phase11_build_is_reproducible() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_phase11.py")],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(completed.stdout)
    assert summary["quality_passed"] is True
    assert summary["report_pages"] == 6
    assert summary["semantic_tables"] == 10
    assert summary["measures"] == 29


def test_pbip_entrypoint_and_report_definition() -> None:
    pbip = json.loads(
        (POWERBI_ROOT / "LaLigaAIPredictor.pbip").read_text(encoding="utf-8")
    )
    assert pbip["version"] == "1.0"
    assert pbip["artifacts"][0]["report"]["path"] == (
        "LaLigaAIPredictor.Report"
    )
    pages = json.loads(
        (REPORT_DIR / "definition" / "pages" / "pages.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(pages["pageOrder"]) == 6
    for page_name in pages["pageOrder"]:
        page_dir = REPORT_DIR / "definition" / "pages" / page_name
        assert (page_dir / "page.json").exists()
        assert len(list((page_dir / "visuals").glob("*/visual.json"))) >= 2


def test_semantic_model_contract() -> None:
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))["model"]
    assert len(model["tables"]) == 10
    assert len(model["relationships"]) == 6
    assert sum(len(table.get("measures", [])) for table in model["tables"]) == 29
    parameter_names = {
        expression["name"]
        for expression in model["expressions"]
        if expression["kind"] == "m"
    }
    assert {
        "pPostgresServer",
        "pPostgresDatabase",
        "pApiBaseUrl",
    }.issubset(parameter_names)


def test_analytical_views_are_complete() -> None:
    sql = (
        PROJECT_ROOT / "database" / "002_powerbi_views.sql"
    ).read_text(encoding="utf-8")
    required = {
        "bi_dim_team",
        "bi_dim_matchday",
        "bi_dim_position",
        "bi_fact_matches",
        "bi_fact_team_matches",
        "bi_current_standings",
        "bi_simulation_summary",
        "bi_position_probabilities",
        "bi_update_status",
    }
    assert sql.count("CREATE OR REPLACE VIEW ") == len(required)
    assert all(f"VIEW {name} AS" in sql for name in required)


def test_powerbi_preview_data_reconciles() -> None:
    preview = PROJECT_ROOT / "powerbi" / "preview_data"
    matches = pd.read_csv(preview / "next_matchday.csv")
    simulation = pd.read_csv(preview / "simulation_summary.csv")
    positions = pd.read_csv(preview / "position_distribution.csv")
    assert len(matches) == 10
    assert len(simulation) == 20
    assert len(positions) == 400
    assert np.allclose(
        matches[["probability_home", "probability_draw",
                 "probability_away"]].sum(axis=1),
        1.0,
    )
    assert np.isclose(simulation["champion_probability"].sum(), 1.0)
    assert np.isclose(simulation["top4_probability"].sum(), 4.0)
    assert np.isclose(simulation["europe_top7_probability"].sum(), 7.0)
    assert np.isclose(simulation["relegation_probability"].sum(), 3.0)


def test_credentials_are_not_embedded() -> None:
    text = MODEL_PATH.read_text(encoding="utf-8").lower()
    assert "password" not in text
    assert "postgresql.database" in text
