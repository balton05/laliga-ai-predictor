from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session, sessionmaker

from laliga_predictor.api.models import PipelineRun, PipelineStep
from laliga_predictor.api.schemas import MatchdayUpdateInput
from laliga_predictor.api.service import DataSyncService
from laliga_predictor.sources.football_data import (
    FootballDataSnapshot,
    SourceUnavailableError,
    fetch_football_data,
)


LOGGER = logging.getLogger(__name__)
MODEL_VERSION = "ensemble-v1-trained-through-2025-26"
T = TypeVar("T")


@dataclass(frozen=True)
class AutomationConfig:
    source_url: str
    timeout_seconds: int = 30
    simulations: int = 50_000
    seed: int = 42
    source_name: str = "football-data-sp1"


class AutomationRunner:
    """Download, reconcile and execute one idempotent season update."""

    def __init__(
        self,
        project_root: Path,
        session_factory: sessionmaker[Session],
        config: AutomationConfig,
        fetcher: Callable[..., FootballDataSnapshot] = fetch_football_data,
    ) -> None:
        self.project_root = Path(project_root)
        self.session_factory = session_factory
        self.config = config
        self.fetcher = fetcher
        self.data_service = DataSyncService(
            self.project_root, self.session_factory
        )
        self._run_id = ""
        self._step_order = 0

    @property
    def processed(self) -> Path:
        return self.project_root / "data" / "processed"

    @property
    def incoming(self) -> Path:
        return self.project_root / "data" / "incoming"

    def run_once(self, trigger: str = "scheduled") -> PipelineRun:
        started = datetime.now(timezone.utc)
        self._run_id = uuid4().hex
        self._step_order = 0
        run = PipelineRun(
            run_id=self._run_id,
            started_at_utc=started,
            finished_at_utc=None,
            status="running",
            trigger=trigger,
            source=self.config.source_name,
            source_url=self.config.source_url,
            source_checksum=None,
            rows_downloaded=0,
            results_discovered=0,
            results_added=0,
            odds_discovered=0,
            odds_added=0,
            update_id=None,
            simulations=self.config.simulations,
            model_version=MODEL_VERSION,
            duration_seconds=None,
            error_type=None,
            error_message=None,
        )
        self._save_run(run)

        try:
            fixtures = self._execute_step(
                "load_calendar",
                lambda: pd.read_csv(
                    self.processed / "fixtures_2026_27.csv",
                    parse_dates=["reference_date", "scheduled_date"],
                    encoding="utf-8-sig",
                ),
                rows=lambda frame: len(frame),
                detail="Calendario canónico 2026/27 cargado.",
            )
            snapshot = self._execute_step(
                "download_source",
                lambda: self.fetcher(
                    self.config.source_url,
                    fixtures=fixtures,
                    timeout_seconds=self.config.timeout_seconds,
                ),
                rows=lambda item: item.rows_downloaded,
                detail="CSV de Football-Data descargado y validado.",
            )
            run.source_checksum = snapshot.checksum
            run.rows_downloaded = snapshot.rows_downloaded
            run.results_discovered = len(snapshot.results)
            run.odds_discovered = len(snapshot.odds)

            new_results, new_odds = self._execute_step(
                "detect_changes",
                lambda: self._changes(snapshot),
                rows=lambda frames: len(frames[0]) + len(frames[1]),
                detail=(
                    "Comparación idempotente contra resultados y cuotas "
                    "ya confirmados."
                ),
            )
            run.results_added = len(new_results)
            run.odds_added = len(new_odds)
            if new_results.empty and new_odds.empty:
                return self._finish(
                    run,
                    "no_changes",
                    started,
                    detail="No se encontraron resultados ni cuotas nuevas.",
                )

            payload = MatchdayUpdateInput(
                results=new_results.to_dict(orient="records"),
                odds=new_odds.to_dict(orient="records"),
                simulations=self.config.simulations,
                seed=self.config.seed,
                allow_partial=True,
            )
            summary = self._execute_step(
                "update_predictions_and_database",
                lambda: self.data_service.apply_update(payload),
                rows=lambda item: int(item["remaining_matches"]),
                detail=(
                    "Variables prepartido, probabilidades 1X2, simulación "
                    "Monte Carlo y PostgreSQL actualizados."
                ),
            )
            run.update_id = str(summary["update_id"])
            return self._finish(
                run,
                "success",
                started,
                detail=(
                    f"{run.results_added} resultados y {run.odds_added} "
                    "cuotas nuevas procesadas."
                ),
            )
        except SourceUnavailableError as exc:
            run.error_type = type(exc).__name__
            run.error_message = str(exc)
            return self._finish(
                run,
                "source_unavailable",
                started,
                detail=str(exc),
            )
        except Exception as exc:
            run.error_type = type(exc).__name__
            run.error_message = str(exc)[:2000]
            self._finish(run, "failed", started, detail=run.error_message)
            LOGGER.exception("Automated LaLiga update failed.")
            raise

    def _changes(
        self, snapshot: FootballDataSnapshot
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        existing_results = self._read_incoming("results_2026_27.csv")
        existing_odds = self._read_incoming("odds_2026_27.csv")
        new_results = self._new_results(
            snapshot.results, existing_results
        )
        new_odds = self._new_odds(snapshot.odds, existing_odds)
        return new_results, new_odds

    def _read_incoming(self, filename: str) -> pd.DataFrame:
        path = self.incoming / filename
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        return pd.read_csv(path, encoding="utf-8-sig")

    @staticmethod
    def _new_results(
        source: pd.DataFrame, existing: pd.DataFrame
    ) -> pd.DataFrame:
        if source.empty:
            return source.copy()
        if existing.empty:
            return source.copy()
        known = existing.set_index("fixture_id")
        additions: list[dict] = []
        for row in source.to_dict(orient="records"):
            fixture_id = row["fixture_id"]
            if fixture_id not in known.index:
                additions.append(row)
                continue
            old = known.loc[fixture_id]
            if (
                int(old["home_goals"]) != int(row["home_goals"])
                or int(old["away_goals"]) != int(row["away_goals"])
            ):
                additions.append(row)
        return pd.DataFrame(additions, columns=source.columns)

    @staticmethod
    def _new_odds(
        source: pd.DataFrame, existing: pd.DataFrame
    ) -> pd.DataFrame:
        if source.empty:
            return source.copy()
        if existing.empty:
            return source.copy()
        odds_columns = [
            "odds_b365_home",
            "odds_b365_draw",
            "odds_b365_away",
        ]
        current = (
            existing.sort_values("captured_at")
            .drop_duplicates("fixture_id", keep="last")
            .set_index("fixture_id")
        )
        additions: list[dict] = []
        for row in source.to_dict(orient="records"):
            fixture_id = row["fixture_id"]
            if fixture_id not in current.index:
                additions.append(row)
                continue
            previous = current.loc[fixture_id]
            if not np.allclose(
                [float(previous[column]) for column in odds_columns],
                [float(row[column]) for column in odds_columns],
                rtol=0,
                atol=1e-9,
            ):
                additions.append(row)
        return pd.DataFrame(additions, columns=source.columns)

    def _execute_step(
        self,
        name: str,
        operation: Callable[[], T],
        rows: Callable[[T], int | None],
        detail: str,
    ) -> T:
        self._step_order += 1
        started = datetime.now(timezone.utc)
        monotonic_started = time.monotonic()
        try:
            value = operation()
        except Exception as exc:
            self._save_step(
                name=name,
                status="failed",
                started=started,
                duration=time.monotonic() - monotonic_started,
                rows_processed=None,
                detail=str(exc)[:2000],
            )
            raise
        self._save_step(
            name=name,
            status="success",
            started=started,
            duration=time.monotonic() - monotonic_started,
            rows_processed=rows(value),
            detail=detail,
        )
        return value

    def _save_run(self, run: PipelineRun) -> None:
        with self.session_factory.begin() as session:
            session.merge(run)

    def _save_step(
        self,
        name: str,
        status: str,
        started: datetime,
        duration: float,
        rows_processed: int | None,
        detail: str | None,
    ) -> None:
        finished = datetime.now(timezone.utc)
        with self.session_factory.begin() as session:
            session.add(
                PipelineStep(
                    run_id=self._run_id,
                    step_order=self._step_order,
                    name=name,
                    status=status,
                    started_at_utc=started,
                    finished_at_utc=finished,
                    duration_seconds=duration,
                    rows_processed=rows_processed,
                    detail=detail,
                )
            )

    def _finish(
        self,
        run: PipelineRun,
        status: str,
        started: datetime,
        detail: str,
    ) -> PipelineRun:
        finished = datetime.now(timezone.utc)
        run.status = status
        run.finished_at_utc = finished
        run.duration_seconds = max(
            0.0, (finished - started).total_seconds()
        )
        self._save_run(run)
        LOGGER.info(
            "Pipeline %s finished with status=%s: %s",
            run.run_id,
            status,
            detail,
        )
        return run
