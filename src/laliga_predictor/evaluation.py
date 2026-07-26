from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from laliga_predictor.api.models import (
    Fixture,
    MatchResult,
    OddsSnapshot,
    Prediction,
    PredictionEvaluation,
    PredictionSnapshot,
)


MODEL_VERSION = "ensemble-v1-trained-through-2025-26"
OUTCOMES = ("H", "D", "A")
LIMA = ZoneInfo("America/Lima")
EPSILON = 1e-15


def _snapshot_id(
    fixture_id: str, update_id: str, model_version: str
) -> str:
    raw = f"{fixture_id}|{update_id}|{model_version}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _cutoff_utc(fixture: Fixture) -> datetime:
    if fixture.scheduled_date is not None:
        scheduled = fixture.scheduled_date
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=LIMA)
        return scheduled.astimezone(timezone.utc)
    local_end = datetime.combine(
        fixture.reference_date, time(23, 59, 59), tzinfo=LIMA
    )
    return local_end.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _outcome_probabilities(
    home: float, draw: float, away: float
) -> dict[str, float]:
    return {"H": float(home), "D": float(draw), "A": float(away)}


def _log_loss(probability: float) -> float:
    return -math.log(max(min(float(probability), 1.0 - EPSILON), EPSILON))


def _brier(probabilities: dict[str, float], actual: str) -> float:
    return sum(
        (probabilities[outcome] - float(outcome == actual)) ** 2
        for outcome in OUTCOMES
    )


def _argmax(probabilities: dict[str, float]) -> str:
    return max(OUTCOMES, key=lambda outcome: probabilities[outcome])


def capture_current_predictions(
    session: Session,
    *,
    captured_at_utc: datetime | None = None,
    capture_source: str,
    model_version: str = MODEL_VERSION,
    exclude_fixture_ids: set[str] | None = None,
) -> int:
    """Append prediction versions without altering any existing snapshot."""

    captured_at_utc = _as_utc(
        captured_at_utc or datetime.now(timezone.utc)
    )
    session.flush()
    played_ids = set(session.scalars(select(MatchResult.fixture_id)))
    played_ids.update(exclude_fixture_ids or set())
    rows = session.execute(
        select(Prediction, Fixture)
        .join(Fixture, Fixture.fixture_id == Prediction.fixture_id)
        .order_by(Fixture.matchday, Fixture.fixture_id)
    ).all()
    odds_rows = session.scalars(
        select(OddsSnapshot).order_by(
            OddsSnapshot.fixture_id,
            OddsSnapshot.captured_at.desc(),
        )
    )
    latest_odds: dict[str, OddsSnapshot] = {}
    for odds in odds_rows:
        latest_odds.setdefault(odds.fixture_id, odds)

    created = 0
    for prediction, fixture in rows:
        if fixture.fixture_id in played_ids:
            continue
        snapshot_id = _snapshot_id(
            fixture.fixture_id, prediction.update_id, model_version
        )
        if session.get(PredictionSnapshot, snapshot_id) is not None:
            continue
        odds = latest_odds.get(fixture.fixture_id)
        session.add(
            PredictionSnapshot(
                snapshot_id=snapshot_id,
                fixture_id=fixture.fixture_id,
                update_id=prediction.update_id,
                season=fixture.season,
                matchday=fixture.matchday,
                reference_date=fixture.reference_date,
                scheduled_date=fixture.scheduled_date,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                captured_at_utc=captured_at_utc,
                model=prediction.model,
                model_version=model_version,
                probability_home=prediction.probability_home,
                probability_draw=prediction.probability_draw,
                probability_away=prediction.probability_away,
                predicted_ftr=prediction.predicted_ftr,
                confidence=prediction.confidence,
                expected_home_goals=prediction.expected_home_goals,
                expected_away_goals=prediction.expected_away_goals,
                predicted_score=prediction.predicted_score,
                market_probability_home=(
                    odds.market_probability_home if odds else None
                ),
                market_probability_draw=(
                    odds.market_probability_draw if odds else None
                ),
                market_probability_away=(
                    odds.market_probability_away if odds else None
                ),
                odds_b365_home=odds.odds_b365_home if odds else None,
                odds_b365_draw=odds.odds_b365_draw if odds else None,
                odds_b365_away=odds.odds_b365_away if odds else None,
                is_pre_match=captured_at_utc <= _cutoff_utc(fixture),
                capture_source=capture_source,
            )
        )
        created += 1
    session.flush()
    return created


def evaluate_pending_results(
    session: Session,
    *,
    evaluated_at_utc: datetime | None = None,
) -> int:
    """Score completed matches once, using their latest valid snapshot."""

    evaluated_at_utc = _as_utc(
        evaluated_at_utc or datetime.now(timezone.utc)
    )
    session.flush()
    evaluated_ids = set(
        session.scalars(select(PredictionEvaluation.fixture_id))
    )
    results = session.execute(
        select(MatchResult, Fixture)
        .join(Fixture, Fixture.fixture_id == MatchResult.fixture_id)
        .order_by(Fixture.matchday, Fixture.fixture_id)
    ).all()
    created = 0
    for result, fixture in results:
        if fixture.fixture_id in evaluated_ids:
            continue
        snapshot = session.scalar(
            select(PredictionSnapshot)
            .where(
                PredictionSnapshot.fixture_id == fixture.fixture_id,
                PredictionSnapshot.is_pre_match.is_(True),
            )
            .order_by(PredictionSnapshot.captured_at_utc.desc())
            .limit(1)
        )
        if snapshot is None:
            continue
        probabilities = _outcome_probabilities(
            snapshot.probability_home,
            snapshot.probability_draw,
            snapshot.probability_away,
        )
        market_probabilities = None
        if snapshot.market_probability_home is not None:
            market_probabilities = _outcome_probabilities(
                snapshot.market_probability_home,
                snapshot.market_probability_draw or 0.0,
                snapshot.market_probability_away or 0.0,
            )
        session.add(
            PredictionEvaluation(
                fixture_id=fixture.fixture_id,
                snapshot_id=snapshot.snapshot_id,
                season=fixture.season,
                matchday=fixture.matchday,
                played_date=result.played_date,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                home_goals=result.home_goals,
                away_goals=result.away_goals,
                actual_ftr=result.result,
                predicted_ftr=snapshot.predicted_ftr,
                probability_home=snapshot.probability_home,
                probability_draw=snapshot.probability_draw,
                probability_away=snapshot.probability_away,
                correct=snapshot.predicted_ftr == result.result,
                log_loss=_log_loss(probabilities[result.result]),
                brier_score=_brier(probabilities, result.result),
                market_predicted_ftr=(
                    _argmax(market_probabilities)
                    if market_probabilities
                    else None
                ),
                market_log_loss=(
                    _log_loss(market_probabilities[result.result])
                    if market_probabilities
                    else None
                ),
                market_brier_score=(
                    _brier(market_probabilities, result.result)
                    if market_probabilities
                    else None
                ),
                model_version=snapshot.model_version,
                prediction_captured_at_utc=snapshot.captured_at_utc,
                evaluated_at_utc=evaluated_at_utc,
            )
        )
        created += 1
    session.flush()
    return created


def performance_summary(session: Session) -> dict[str, Any]:
    snapshots = session.scalar(
        select(func.count()).select_from(PredictionSnapshot)
    ) or 0
    covered_fixtures = session.scalar(
        select(func.count(func.distinct(PredictionSnapshot.fixture_id)))
    ) or 0
    completed = session.scalar(
        select(func.count()).select_from(MatchResult)
    ) or 0
    evaluations = list(
        session.scalars(
            select(PredictionEvaluation).order_by(
                PredictionEvaluation.played_date,
                PredictionEvaluation.fixture_id,
            )
        )
    )
    evaluated = len(evaluations)
    correct = sum(int(row.correct) for row in evaluations)
    market_rows = [
        row for row in evaluations if row.market_log_loss is not None
    ]
    versions = sorted({row.model_version for row in evaluations})
    if not versions:
        versions = list(
            session.scalars(
                select(PredictionSnapshot.model_version)
                .distinct()
                .order_by(PredictionSnapshot.model_version)
            )
        )
    return {
        "season": "2026/27",
        "prediction_snapshots": snapshots,
        "fixtures_with_snapshot": covered_fixtures,
        "completed_matches": completed,
        "evaluated_matches": evaluated,
        "pending_evaluation": max(completed - evaluated, 0),
        "correct_predictions": correct,
        "accuracy": correct / evaluated if evaluated else None,
        "log_loss": (
            sum(row.log_loss for row in evaluations) / evaluated
            if evaluated
            else None
        ),
        "brier_score": (
            sum(row.brier_score for row in evaluations) / evaluated
            if evaluated
            else None
        ),
        "market_matches": len(market_rows),
        "market_accuracy": (
            sum(
                int(row.market_predicted_ftr == row.actual_ftr)
                for row in market_rows
            )
            / len(market_rows)
            if market_rows
            else None
        ),
        "market_log_loss": (
            sum(float(row.market_log_loss) for row in market_rows)
            / len(market_rows)
            if market_rows
            else None
        ),
        "market_brier_score": (
            sum(float(row.market_brier_score) for row in market_rows)
            / len(market_rows)
            if market_rows
            else None
        ),
        "model_versions": versions,
        "last_evaluated_at_utc": (
            max(row.evaluated_at_utc for row in evaluations)
            if evaluations
            else None
        ),
    }


def performance_by_matchday(
    session: Session,
) -> list[dict[str, Any]]:
    grouped: dict[int, list[PredictionEvaluation]] = defaultdict(list)
    for row in session.scalars(
        select(PredictionEvaluation).order_by(
            PredictionEvaluation.matchday
        )
    ):
        grouped[row.matchday].append(row)
    output = []
    for matchday, rows in grouped.items():
        market = [row for row in rows if row.market_log_loss is not None]
        output.append(
            {
                "matchday": matchday,
                "matches": len(rows),
                "correct": sum(int(row.correct) for row in rows),
                "accuracy": sum(int(row.correct) for row in rows) / len(rows),
                "log_loss": sum(row.log_loss for row in rows) / len(rows),
                "brier_score": (
                    sum(row.brier_score for row in rows) / len(rows)
                ),
                "market_log_loss": (
                    sum(float(row.market_log_loss) for row in market)
                    / len(market)
                    if market
                    else None
                ),
            }
        )
    return output


def confusion_matrix(session: Session) -> list[dict[str, Any]]:
    counts = {
        (actual, predicted): 0
        for actual in OUTCOMES
        for predicted in OUTCOMES
    }
    for actual, predicted in session.execute(
        select(
            PredictionEvaluation.actual_ftr,
            PredictionEvaluation.predicted_ftr,
        )
    ):
        counts[(actual, predicted)] += 1
    return [
        {
            "actual_ftr": actual,
            "predicted_ftr": predicted,
            "matches": counts[(actual, predicted)],
        }
        for actual in OUTCOMES
        for predicted in OUTCOMES
    ]


def calibration_bins(session: Session) -> list[dict[str, Any]]:
    bins: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for row in session.scalars(select(PredictionEvaluation)):
        confidence = max(
            row.probability_home,
            row.probability_draw,
            row.probability_away,
        )
        index = min(int(confidence * 10), 9)
        bins[index].append((confidence, row.correct))
    output = []
    for index in range(10):
        rows = bins.get(index, [])
        output.append(
            {
                "bin_lower": index / 10,
                "bin_upper": (index + 1) / 10,
                "label": f"{index * 10}-{(index + 1) * 10}%",
                "matches": len(rows),
                "mean_confidence": (
                    sum(row[0] for row in rows) / len(rows)
                    if rows
                    else None
                ),
                "observed_accuracy": (
                    sum(int(row[1]) for row in rows) / len(rows)
                    if rows
                    else None
                ),
            }
        )
    return output


def performance_history_query(
    session: Session,
    *,
    matchday: int | None,
    team: str | None,
    limit: int,
    offset: int,
):
    query = select(PredictionEvaluation)
    if matchday is not None:
        query = query.where(PredictionEvaluation.matchday == matchday)
    if team:
        pattern = f"%{team.strip()}%"
        query = query.where(
            or_(
                PredictionEvaluation.home_team.ilike(pattern),
                PredictionEvaluation.away_team.ilike(pattern),
            )
        )
    return list(
        session.scalars(
            query.order_by(
                PredictionEvaluation.played_date.desc(),
                PredictionEvaluation.fixture_id,
            )
            .offset(offset)
            .limit(limit)
        )
    )
