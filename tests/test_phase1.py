from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.pipeline import run_phase1  # noqa: E402


def test_phase1_outputs() -> None:
    summary = run_phase1()
    assert summary["audit_passed"] is True
    assert summary["laliga_matches"] == 3800
    assert summary["segunda_matches"] == 2310
    assert summary["historical_matches"] == 6110
    assert summary["team_history_rows"] == 12220
    assert summary["fixtures_2026_27"] == 380
    assert summary["fixture_teams"] == 20
    assert summary["promotion_records"] == 30
    assert summary["promotions_with_segunda_stats"] == 15


def test_promoted_teams_2026_27() -> None:
    run_phase1()
    path = PROJECT_ROOT / "data" / "processed" / "promoted_teams_2026_27.csv"
    promoted = pd.read_csv(path).set_index("team_id")

    assert set(promoted.index) == {"racing_santander", "deportivo", "malaga"}
    assert promoted.loc["racing_santander", "segunda_position"] == 1
    assert promoted.loc["deportivo", "segunda_position"] == 2
    assert promoted.loc["malaga", "segunda_position"] == 4
    assert promoted.loc["racing_santander", "promotion_type"] == "direct"
    assert promoted.loc["deportivo", "promotion_type"] == "direct"
    assert promoted.loc["malaga", "promotion_type"] == "playoff"


def test_processed_data_has_no_duplicate_ids() -> None:
    run_phase1()
    processed = PROJECT_ROOT / "data" / "processed"
    matches = pd.read_csv(processed / "matches_master.csv")
    fixtures = pd.read_csv(processed / "fixtures_2026_27.csv")

    assert matches["match_id"].is_unique
    assert fixtures["fixture_id"].is_unique
    assert matches[["date", "home_team_id", "away_team_id", "result"]].notna().all().all()
