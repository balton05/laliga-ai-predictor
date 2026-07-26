from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .analytics import apply_powerbi_views
from .database import Base, build_engine, build_session_factory
from .models import (
    Fixture,
    MatchResult,
    Prediction,
    SimulationSummary,
    Standing,
    UpdateRun,
)
from .schemas import (
    FixtureOut,
    HealthOut,
    MatchdayUpdateInput,
    PredictionOut,
    SimulationOut,
    StandingOut,
    UpdateRunOut,
)
from .service import DataSyncService, UpdateConflictError
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    service = DataSyncService(settings.project_root, session_factory)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        Base.metadata.create_all(engine)
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
    )
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.service = service
    application.state.settings = settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    def get_session(request: Request):
        session = request.app.state.session_factory()
        try:
            yield session
        finally:
            session.close()

    @application.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": settings.api_title,
            "version": settings.api_version,
            "docs": "/docs",
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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database unavailable: {exc}",
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

    @application.post(
        "/update-matchday",
        response_model=UpdateRunOut,
        status_code=status.HTTP_201_CREATED,
        tags=["updates"],
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
