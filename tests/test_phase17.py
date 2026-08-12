from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def test_render_application_serves_spa_and_prefixed_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    browser = (
        tmp_path / "frontend" / "dist" / "laliga-app" / "browser"
    )
    browser.mkdir(parents=True)
    (browser / "index.html").write_text(
        (
            '<!doctype html><html><head><base href="/">'
            '<link rel="stylesheet" href="styles.css"></head>'
            '<body><div data-laliga-root></div></body></html>'
        ),
        encoding="utf-8",
    )
    (browser / "styles.css").write_text(
        "body{background:#081020}",
        encoding="utf-8",
    )
    (browser / "favicon.ico").write_bytes(b"ico")

    monkeypatch.setenv(
        "LALIGA_DATABASE_URL",
        f"sqlite:///{tmp_path / 'phase17.db'}",
    )
    monkeypatch.setenv("LALIGA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("LALIGA_ENVIRONMENT", "test")
    monkeypatch.setenv("LALIGA_AUTO_SYNC", "false")
    monkeypatch.setenv("LALIGA_BOOTSTRAP_EMPTY_DATABASE", "false")
    monkeypatch.setenv("LALIGA_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("LALIGA_CORS_ORIGINS", "http://testserver")

    sys.modules.pop("laliga_predictor.deployment", None)
    deployment = importlib.import_module("laliga_predictor.deployment")

    with TestClient(deployment.app) as client:
        homepage = client.get("/")
        route = client.get("/rendimiento")
        stylesheet = client.get("/styles.css")
        health = client.get("/api/health")

    assert homepage.status_code == 200
    assert route.status_code == 200
    assert "data-laliga-root" in route.text
    assert stylesheet.status_code == 200
    assert stylesheet.headers["cache-control"] == "public, max-age=3600"
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["database"] == "connected"
    assert "content-security-policy" in homepage.headers


def test_render_hostname_is_added_to_trusted_hosts(monkeypatch) -> None:
    from laliga_predictor.api.settings import Settings

    monkeypatch.setenv("LALIGA_ENVIRONMENT", "production")
    monkeypatch.setenv("LALIGA_ADMIN_API_KEY", "x" * 32)
    monkeypatch.setenv("LALIGA_ALLOWED_HOSTS", "localhost")
    monkeypatch.setenv(
        "RENDER_EXTERNAL_HOSTNAME",
        "laliga-ai-predictor-josue.onrender.com",
    )
    monkeypatch.setenv(
        "LALIGA_CORS_ORIGINS",
        "https://laliga-ai-predictor-josue.onrender.com",
    )

    settings = Settings.from_env()

    assert "localhost" in settings.allowed_hosts
    assert (
        "laliga-ai-predictor-josue.onrender.com" in settings.allowed_hosts
    )
