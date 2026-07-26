from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.api.database import (  # noqa: E402
    Base,
    build_engine,
    build_session_factory,
)
from laliga_predictor.api.main import create_app  # noqa: E402
from laliga_predictor.api.models import PipelineStep  # noqa: E402
from laliga_predictor.api.settings import Settings  # noqa: E402
from laliga_predictor.automation import (  # noqa: E402
    AutomationConfig,
    AutomationRunner,
)
from laliga_predictor.sources.football_data import (  # noqa: E402
    FootballDataSnapshot,
    SourceDataError,
    SourceUnavailableError,
    parse_football_data,
)


def _fixtures() -> pd.DataFrame:
    return pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "fixtures_2026_27.csv",
        parse_dates=["reference_date", "scheduled_date"],
        encoding="utf-8-sig",
    )


def _csv_for_fixture(fixture: pd.Series) -> bytes:
    date = pd.Timestamp(fixture["reference_date"]).strftime("%d/%m/%Y")
    return (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST,"
        "HC,AC,HY,AY,HR,AR,B365H,B365D,B365A\n"
        f"SP1,{date},{fixture['home_team']},{fixture['away_team']},"
        "2,1,14,8,6,3,5,4,2,3,0,0,1.90,3.50,4.20\n"
    ).encode("utf-8")


def test_football_data_maps_result_stats_and_odds() -> None:
    fixtures = _fixtures()
    fixture = fixtures.iloc[0]
    snapshot = parse_football_data(
        _csv_for_fixture(fixture),
        fixtures,
        "https://example.test/SP1.csv",
        fetched_at_utc=datetime(2026, 8, 15, 23, tzinfo=timezone.utc),
    )
    result = snapshot.results.iloc[0]
    odds = snapshot.odds.iloc[0]
    assert snapshot.rows_downloaded == 1
    assert result["fixture_id"] == fixture["fixture_id"]
    assert result["home_goals"] == 2
    assert result["home_shots_on_target"] == 6
    assert odds["odds_b365_draw"] == 3.5
    assert odds["captured_at"] == "2026-08-15T23:00:00+00:00"


def test_football_data_rejects_unmatched_relevant_match() -> None:
    content = (
        "Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
        "15/08/2026,Unknown FC,Barcelona,1,0\n"
    ).encode()
    with pytest.raises(SourceDataError, match="do not match"):
        parse_football_data(
            content,
            _fixtures(),
            "https://example.test/SP1.csv",
        )


def test_runner_records_source_unavailable(tmp_path: Path) -> None:
    database = tmp_path / "automation.db"
    engine = build_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)

    def unavailable(*args, **kwargs):
        raise SourceUnavailableError("2026/27 file not published yet.")

    runner = AutomationRunner(
        PROJECT_ROOT,
        factory,
        AutomationConfig(source_url="https://example.test/SP1.csv"),
        fetcher=unavailable,
    )
    run = runner.run_once(trigger="scheduled")
    assert run.status == "source_unavailable"
    assert run.error_type == "SourceUnavailableError"
    with factory() as session:
        steps = session.query(PipelineStep).order_by(
            PipelineStep.step_order
        ).all()
        assert [step.name for step in steps] == [
            "load_calendar",
            "download_source",
        ]
        assert steps[-1].status == "failed"


def test_runner_is_idempotent_against_current_inputs(tmp_path: Path) -> None:
    database = tmp_path / "idempotent.db"
    engine = build_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    now = datetime.now(timezone.utc)
    fixture = _fixtures().iloc[0]
    snapshot = parse_football_data(
        _csv_for_fixture(fixture),
        _fixtures(),
        "https://example.test/SP1.csv",
        fetched_at_utc=now,
    )
    project = tmp_path / "project"
    processed = project / "data" / "processed"
    incoming = project / "data" / "incoming"
    processed.mkdir(parents=True)
    incoming.mkdir(parents=True)
    _fixtures().to_csv(
        processed / "fixtures_2026_27.csv",
        index=False,
        encoding="utf-8-sig",
    )
    snapshot.results.to_csv(
        incoming / "results_2026_27.csv",
        index=False,
        encoding="utf-8-sig",
    )
    snapshot.odds.to_csv(
        incoming / "odds_2026_27.csv",
        index=False,
        encoding="utf-8-sig",
    )

    def same_snapshot(*args, **kwargs) -> FootballDataSnapshot:
        return snapshot

    runner = AutomationRunner(
        project,
        factory,
        AutomationConfig(source_url=snapshot.source_url),
        fetcher=same_snapshot,
    )
    run = runner.run_once()
    assert run.status == "no_changes"
    assert run.results_added == 0
    assert run.odds_added == 0


def test_automation_endpoints_start_empty(tmp_path: Path) -> None:
    database = tmp_path / "api.db"
    settings = Settings(
        database_url=f"sqlite:///{database}",
        project_root=PROJECT_ROOT,
        auto_sync=False,
        automation_enabled=True,
        automation_interval_minutes=360,
        automation_source_url="https://example.test/SP1.csv",
    )
    with TestClient(create_app(settings)) as client:
        status = client.get("/automation/status")
        runs = client.get("/automation/runs")
        missing_steps = client.get("/automation/runs/unknown/steps")
        assert status.status_code == 200
        assert status.json()["latest_run"] is None
        assert status.json()["interval_minutes"] == 360
        assert runs.json() == []
        assert missing_steps.status_code == 404
