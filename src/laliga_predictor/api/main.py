from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from secrets import compare_digest
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .analytics import apply_powerbi_views
from .database import Base, build_engine, build_session_factory
from .models import (
    Fixture,
    MatchResult,
    ModelTrainingRun,
    ModelVersion,
    PipelineRun,
    PipelineStep,
    Prediction,
    SimulationSummary,
    Standing,
    UpdateRun,
)
from .schemas import (
    AutomationStatusOut,
    CalibrationBinOut,
    ConfusionCellOut,
    FixtureOut,
    HealthOut,
    MatchdayUpdateInput,
    MatchdayPerformanceOut,
    ModelStatusOut,
    ModelTrainingRunOut,
    ModelVersionOut,
    PerformanceHistoryOut,
    PerformanceSummaryOut,
    PipelineRunOut,
    PipelineStepOut,
    PredictionOut,
    PromoteModelInput,
    PromotionOut,
    SimulationOut,
    StandingOut,
    UpdateRunOut,
)
from .service import DataSyncService, UpdateConflictError
from .settings import Settings
from laliga_predictor.automation import AutomationConfig, AutomationRunner
from laliga_predictor.evaluation import (
    calibration_bins,
    confusion_matrix,
    performance_by_matchday,
    performance_history_query,
    performance_summary,
)
from laliga_predictor.model_management import (
    ModelTrainingService,
    bootstrap_model_registry,
    list_models,
    list_training_runs,
    promote_model,
    promotion_readiness,
)


LOGGER = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    service = DataSyncService(settings.project_root, session_factory)
    automation = AutomationRunner(
        settings.project_root,
        session_factory,
        AutomationConfig(
            source_url=settings.automation_source_url,
            timeout_seconds=settings.automation_timeout_seconds,
            simulations=settings.automation_simulations,
            seed=settings.automation_seed,
        ),
    )
    model_training = ModelTrainingService(
        settings.project_root,
        session_factory,
        minimum_matches=settings.retraining_minimum_matches,
        minimum_matchdays=settings.retraining_minimum_matchdays,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        Base.metadata.create_all(engine)
        with session_factory.begin() as session:
            bootstrap_model_registry(session, settings.project_root)
        if settings.auto_sync:
            service.sync_current_state()
        apply_powerbi_views(engine, settings.project_root)
        yield
        engine.dispose()

    application = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=(
            "API operativa de predicciones 1X2, tabla y simulación Monte "
            "Carlo para LaLiga 2026/27."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.service = service
    application.state.automation = automation
    application.state.model_training = model_training
    application.state.settings = settings
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )

    @application.middleware("http")
    async def enforce_request_and_response_security(
        request: Request,
        call_next,
    ):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = (
                    int(content_length) > settings.max_request_body_bytes
                )
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": "Request body is too large."},
                )

        response = await call_next(request)
        if settings.security_headers_enabled:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=()"
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'; "
                "base-uri 'none'"
            )
            response.headers["Cache-Control"] = "no-store"
            if settings.is_production:
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
        response.headers["X-Request-ID"] = (
            request.headers.get("X-Request-ID") or uuid4().hex
        )
        return response

    def get_session(request: Request):
        session = request.app.state.session_factory()
        try:
            yield session
        finally:
            session.close()

    def require_admin_api_key(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str | None = Header(default=None),
    ) -> None:
        expected = settings.admin_api_key
        if expected is None:
            return

        bearer = None
        if authorization and authorization.lower().startswith("bearer "):
            bearer = authorization[7:].strip()
        supplied = x_api_key or bearer
        if supplied is None or not compare_digest(supplied, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid administrative API key is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @application.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": settings.api_title,
            "version": settings.api_version,
            "docs": "/docs" if settings.docs_enabled else None,
            "health": "/health",
        }

    @application.get("/health", response_model=HealthOut, tags=["system"])
    def health(session: Session = Depends(get_session)) -> HealthOut:
        try:
            session.execute(text("SELECT 1"))
            latest = session.scalar(
                select(UpdateRun).order_by(
                    UpdateRun.created_at_utc.desc()
                ).limit(1)
            )
            return HealthOut(
                status="ok",
                database="connected",
                season="2026/27",
                latest_update_id=latest.update_id if latest else None,
                fixtures=session.scalar(
                    select(func.count()).select_from(Fixture)
                )
                or 0,
                predictions=session.scalar(
                    select(func.count()).select_from(Prediction)
                )
                or 0,
                completed_matches=session.scalar(
                    select(func.count()).select_from(MatchResult)
                )
                or 0,
                simulations=latest.simulations if latest else 0,
            )
        except Exception as exc:
            LOGGER.exception("Database health check failed.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable.",
            ) from exc

    @application.get(
        "/fixtures", response_model=list[FixtureOut], tags=["season"]
    )
    def fixtures(
        session: Session = Depends(get_session),
        matchday: int | None = Query(default=None, ge=1, le=38),
        fixture_status: str | None = Query(default=None, alias="status"),
        team: str | None = None,
        limit: int = Query(default=380, ge=1, le=380),
        offset: int = Query(default=0, ge=0),
    ) -> list[Fixture]:
        query = select(Fixture)
        if matchday is not None:
            query = query.where(Fixture.matchday == matchday)
        if fixture_status:
            query = query.where(Fixture.status == fixture_status)
        if team:
            pattern = f"%{team.strip()}%"
            query = query.where(
                or_(
                    Fixture.home_team.ilike(pattern),
                    Fixture.away_team.ilike(pattern),
                    Fixture.home_team_id.ilike(pattern),
                    Fixture.away_team_id.ilike(pattern),
                )
            )
        query = query.order_by(
            Fixture.matchday, Fixture.reference_date, Fixture.fixture_id
        )
        return list(session.scalars(query.offset(offset).limit(limit)))

    @application.get(
        "/predictions",
        response_model=list[PredictionOut],
        tags=["predictions"],
    )
    def predictions(
        session: Session = Depends(get_session),
        matchday: int | None = Query(default=None, ge=1, le=38),
        team: str | None = None,
        model: str | None = None,
        limit: int = Query(default=380, ge=1, le=380),
        offset: int = Query(default=0, ge=0),
    ) -> list[PredictionOut]:
        query = (
            select(Prediction, Fixture)
            .join(Fixture, Fixture.fixture_id == Prediction.fixture_id)
        )
        if matchday is not None:
            query = query.where(Fixture.matchday == matchday)
        if model:
            query = query.where(Prediction.model == model)
        if team:
            pattern = f"%{team.strip()}%"
            query = query.where(
                or_(
                    Fixture.home_team.ilike(pattern),
                    Fixture.away_team.ilike(pattern),
                    Fixture.home_team_id.ilike(pattern),
                    Fixture.away_team_id.ilike(pattern),
                )
            )
        query = query.order_by(Fixture.matchday, Fixture.fixture_id)
        rows = session.execute(query.offset(offset).limit(limit)).all()
        return [
            PredictionOut(
                fixture_id=prediction.fixture_id,
                matchday=fixture.matchday,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                model=prediction.model,
                probability_home=prediction.probability_home,
                probability_draw=prediction.probability_draw,
                probability_away=prediction.probability_away,
                predicted_ftr=prediction.predicted_ftr,
                confidence=prediction.confidence,
                expected_home_goals=prediction.expected_home_goals,
                expected_away_goals=prediction.expected_away_goals,
                predicted_score=prediction.predicted_score,
                market_odds_available=prediction.market_odds_available,
            )
            for prediction, fixture in rows
        ]

    @application.get(
        "/standings", response_model=list[StandingOut], tags=["season"]
    )
    def standings(
        session: Session = Depends(get_session),
    ) -> list[Standing]:
        position_null_last = Standing.position.is_(None)
        query = select(Standing).order_by(
            position_null_last,
            Standing.position,
            Standing.points.desc(),
            Standing.team,
        )
        return list(session.scalars(query))

    @application.get(
        "/simulation",
        response_model=list[SimulationOut],
        tags=["simulation"],
    )
    def simulation(
        session: Session = Depends(get_session),
    ) -> list[SimulationSummary]:
        return list(
            session.scalars(
                select(SimulationSummary).order_by(
                    SimulationSummary.expected_position,
                    SimulationSummary.team,
                )
            )
        )

    @application.get(
        "/updates/latest",
        response_model=UpdateRunOut,
        tags=["updates"],
    )
    def latest_update(
        session: Session = Depends(get_session),
    ) -> UpdateRun:
        latest = session.scalar(
            select(UpdateRun).order_by(
                UpdateRun.created_at_utc.desc()
            ).limit(1)
        )
        if latest is None:
            raise HTTPException(status_code=404, detail="No update found.")
        return latest

    @application.get(
        "/automation/status",
        response_model=AutomationStatusOut,
        tags=["automation"],
    )
    def automation_status(
        session: Session = Depends(get_session),
    ) -> AutomationStatusOut:
        latest = session.scalar(
            select(PipelineRun)
            .order_by(PipelineRun.started_at_utc.desc())
            .limit(1)
        )
        return AutomationStatusOut(
            enabled=settings.automation_enabled,
            interval_minutes=settings.automation_interval_minutes,
            source="football-data-sp1",
            source_url=settings.automation_source_url,
            latest_run=latest,
        )

    @application.get(
        "/automation/runs",
        response_model=list[PipelineRunOut],
        tags=["automation"],
    )
    def automation_runs(
        session: Session = Depends(get_session),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[PipelineRun]:
        return list(
            session.scalars(
                select(PipelineRun)
                .order_by(PipelineRun.started_at_utc.desc())
                .limit(limit)
            )
        )

    @application.get(
        "/automation/runs/{run_id}/steps",
        response_model=list[PipelineStepOut],
        tags=["automation"],
    )
    def automation_steps(
        run_id: str,
        session: Session = Depends(get_session),
    ) -> list[PipelineStep]:
        exists = session.get(PipelineRun, run_id)
        if exists is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        return list(
            session.scalars(
                select(PipelineStep)
                .where(PipelineStep.run_id == run_id)
                .order_by(PipelineStep.step_order)
            )
        )

    @application.get(
        "/performance/summary",
        response_model=PerformanceSummaryOut,
        tags=["performance"],
    )
    def performance_summary_endpoint(
        session: Session = Depends(get_session),
    ) -> dict:
        return performance_summary(session)

    @application.get(
        "/performance/history",
        response_model=list[PerformanceHistoryOut],
        tags=["performance"],
    )
    def performance_history(
        session: Session = Depends(get_session),
        matchday: int | None = Query(default=None, ge=1, le=38),
        team: str | None = None,
        limit: int = Query(default=100, ge=1, le=380),
        offset: int = Query(default=0, ge=0),
    ) -> list:
        return performance_history_query(
            session,
            matchday=matchday,
            team=team,
            limit=limit,
            offset=offset,
        )

    @application.get(
        "/performance/by-matchday",
        response_model=list[MatchdayPerformanceOut],
        tags=["performance"],
    )
    def matchday_performance(
        session: Session = Depends(get_session),
    ) -> list[dict]:
        return performance_by_matchday(session)

    @application.get(
        "/performance/confusion",
        response_model=list[ConfusionCellOut],
        tags=["performance"],
    )
    def performance_confusion(
        session: Session = Depends(get_session),
    ) -> list[dict]:
        return confusion_matrix(session)

    @application.get(
        "/performance/calibration",
        response_model=list[CalibrationBinOut],
        tags=["performance"],
    )
    def performance_calibration(
        session: Session = Depends(get_session),
    ) -> list[dict]:
        return calibration_bins(session)

    @application.get(
        "/models/status",
        response_model=ModelStatusOut,
        tags=["models"],
    )
    def model_status(
        session: Session = Depends(get_session),
    ) -> dict:
        return promotion_readiness(
            session,
            settings.retraining_minimum_matches,
            settings.retraining_minimum_matchdays,
        )

    @application.get(
        "/models",
        response_model=list[ModelVersionOut],
        tags=["models"],
    )
    def model_versions(
        session: Session = Depends(get_session),
    ) -> list[ModelVersion]:
        return list_models(session)

    @application.get(
        "/models/training-runs",
        response_model=list[ModelTrainingRunOut],
        tags=["models"],
    )
    def model_training_runs(
        session: Session = Depends(get_session),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[ModelTrainingRun]:
        return list_training_runs(session, limit)

    @application.post(
        "/models/retrain",
        response_model=ModelTrainingRunOut,
        status_code=status.HTTP_201_CREATED,
        tags=["models"],
        dependencies=[Depends(require_admin_api_key)],
    )
    def retrain_model(request: Request) -> ModelTrainingRun:
        try:
            return request.app.state.model_training.run_once(
                trigger="manual"
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post(
        "/models/{version}/promote",
        response_model=PromotionOut,
        tags=["models"],
        dependencies=[Depends(require_admin_api_key)],
    )
    def promote_model_endpoint(
        version: str,
        payload: PromoteModelInput,
        session: Session = Depends(get_session),
    ) -> PromotionOut:
        if not payload.confirm:
            raise HTTPException(
                status_code=422,
                detail="Explicit confirmation is required.",
            )
        try:
            promoted, previous = promote_model(
                session, settings.project_root, version
            )
            session.commit()
            return PromotionOut(
                active_model=promoted.version,
                previous_model=previous,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post(
        "/automation/run",
        response_model=PipelineRunOut,
        status_code=status.HTTP_201_CREATED,
        tags=["automation"],
        dependencies=[Depends(require_admin_api_key)],
    )
    def run_automation(request: Request) -> PipelineRun:
        if not settings.automation_enabled:
            raise HTTPException(
                status_code=409, detail="Automation is disabled."
            )
        try:
            return request.app.state.automation.run_once(trigger="manual")
        except UpdateConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, AssertionError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post(
        "/update-matchday",
        response_model=UpdateRunOut,
        status_code=status.HTTP_201_CREATED,
        tags=["updates"],
        dependencies=[Depends(require_admin_api_key)],
    )
    def update_matchday(
        payload: MatchdayUpdateInput,
        request: Request,
    ) -> UpdateRunOut:
        try:
            summary = request.app.state.service.apply_update(payload)
            return UpdateRunOut.model_validate(summary)
        except UpdateConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, AssertionError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return application


app = create_app()
