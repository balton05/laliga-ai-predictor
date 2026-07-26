from __future__ import annotations

import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select


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
from laliga_predictor.api.models import (  # noqa: E402
    Fixture,
    MatchResult,
    OddsSnapshot,
    Prediction,
    PredictionEvaluation,
    PredictionSnapshot,
)
from laliga_predictor.api.settings import Settings  # noqa: E402
from laliga_predictor.evaluation import (  # noqa: E402
    capture_current_predictions,
    evaluate_pending_results,
    performance_summary,
)


def _fixture() -> Fixture:
    return Fixture(
        fixture_id="2026-27-md01-barcelona-valencia",
        season="2026/27",
        matchday=1,
        reference_date=date(2026, 8, 16),
        scheduled_date=None,
        kickoff_time=None,
        home_team_id="barcelona",
        home_team="FC Barcelona",
        home_team_official="FC Barcelona",
        away_team_id="valencia",
        away_team="Valencia CF",
        away_team_official="Valencia CF",
        status="scheduled",
    )


def _prediction(update_id: str, home: float) -> Prediction:
    draw = 0.25
    away = 1.0 - home - draw
    return Prediction(
        fixture_id="2026-27-md01-barcelona-valencia",
        model="dynamic_ensemble",
        probability_home=home,
        probability_draw=draw,
        probability_away=away,
        predicted_ftr="H",
        probability_edge=home - draw,
        confidence="high",
        expected_home_goals=1.8,
        expected_away_goals=0.9,
        predicted_score="2-1",
        predicted_score_probability=0.14,
        market_odds_available=True,
        promoted_adjustment_applied=False,
        feature_snapshot="phase14-test",
        update_id=update_id,
    )


def test_snapshots_are_append_only_and_result_is_scored(
    tmp_path: Path,
) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'performance.db'}")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    first_capture = datetime(2026, 7, 26, 18, tzinfo=timezone.utc)
    second_capture = datetime(2026, 8, 10, 18, tzinfo=timezone.utc)

    with factory.begin() as session:
        session.add(_fixture())
        session.add(_prediction("update-1", 0.60))
        session.add(
            OddsSnapshot(
                fixture_id="2026-27-md01-barcelona-valencia",
                captured_at=first_capture,
                odds_b365_home=1.80,
                odds_b365_draw=3.60,
                odds_b365_away=4.50,
                market_probability_home=0.54,
                market_probability_draw=0.27,
                market_probability_away=0.19,
                market_overround=1.03,
            )
        )
        assert (
            capture_current_predictions(
                session,
                captured_at_utc=first_capture,
                capture_source="test",
            )
            == 1
        )
        assert (
            capture_current_predictions(
                session,
                captured_at_utc=first_capture,
                capture_source="duplicate",
            )
            == 0
        )

    with factory.begin() as session:
        prediction = session.get(
            Prediction, "2026-27-md01-barcelona-valencia"
        )
        prediction.update_id = "update-2"
        prediction.probability_home = 0.70
        prediction.probability_away = 0.05
        assert (
            capture_current_predictions(
                session,
                captured_at_utc=second_capture,
                capture_source="test",
            )
            == 1
        )

    with factory.begin() as session:
        session.add(
            MatchResult(
                fixture_id="2026-27-md01-barcelona-valencia",
                played_date=date(2026, 8, 16),
                home_goals=2,
                away_goals=0,
                result="H",
                home_shots=None,
                away_shots=None,
                home_shots_on_target=None,
                away_shots_on_target=None,
                home_corners=None,
                away_corners=None,
                home_yellow_cards=None,
                away_yellow_cards=None,
                home_red_cards=None,
                away_red_cards=None,
            )
        )
        assert evaluate_pending_results(session) == 1
        assert evaluate_pending_results(session) == 0

    with factory() as session:
        snapshots = list(
            session.scalars(
                select(PredictionSnapshot).order_by(
                    PredictionSnapshot.captured_at_utc
                )
            )
        )
        evaluation = session.get(
            PredictionEvaluation,
            "2026-27-md01-barcelona-valencia",
        )
        summary = performance_summary(session)
        assert len(snapshots) == 2
        assert snapshots[0].probability_home == 0.60
        assert evaluation.snapshot_id == snapshots[1].snapshot_id
        assert evaluation.correct is True
        assert math.isclose(evaluation.log_loss, -math.log(0.70))
        assert summary["evaluated_matches"] == 1
        assert summary["accuracy"] == 1.0
        assert summary["market_matches"] == 1


def test_performance_endpoints_start_ready_without_results(
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        project_root=PROJECT_ROOT,
        auto_sync=False,
        automation_enabled=True,
        automation_interval_minutes=360,
        automation_source_url="https://example.test/SP1.csv",
    )
    with TestClient(create_app(settings)) as client:
        summary = client.get("/performance/summary")
        history = client.get("/performance/history")
        by_matchday = client.get("/performance/by-matchday")
        confusion = client.get("/performance/confusion")
        calibration = client.get("/performance/calibration")
        assert summary.status_code == 200
        assert summary.json()["evaluated_matches"] == 0
        assert summary.json()["accuracy"] is None
        assert history.json() == []
        assert by_matchday.json() == []
        assert len(confusion.json()) == 9
        assert len(calibration.json()) == 10
