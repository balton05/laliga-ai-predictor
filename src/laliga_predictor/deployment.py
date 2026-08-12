from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, Response

from laliga_predictor.api.main import create_app
from laliga_predictor.api.settings import Settings


settings = Settings.from_env()
api_app = create_app(settings)
frontend_root = (
    settings.project_root / "frontend" / "dist" / "laliga-app" / "browser"
).resolve()
index_file = frontend_root / "index.html"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not index_file.is_file():
        raise RuntimeError(
            "Angular production build was not found at "
            f"{index_file.as_posix()}."
        )
    async with api_app.router.lifespan_context(api_app):
        yield


app = FastAPI(
    title="LaLiga AI Predictor",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(settings.allowed_hosts),
)
app.mount("/api", api_app)


@app.middleware("http")
async def static_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        return response
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


@app.get("/{requested_path:path}", include_in_schema=False)
def serve_frontend(requested_path: str) -> FileResponse:
    candidate = (frontend_root / requested_path).resolve()
    is_inside_frontend = (
        candidate == frontend_root or frontend_root in candidate.parents
    )
    if is_inside_frontend and candidate.is_file():
        response = FileResponse(candidate)
        if candidate.name == "index.html":
            response.headers["Cache-Control"] = "no-cache"
        elif candidate.suffix in {".js", ".css", ".woff2", ".png", ".webp"}:
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    response = FileResponse(index_file)
    response.headers["Cache-Control"] = "no-cache"
    return response
