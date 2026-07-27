from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.api.main import create_app  # noqa: E402
from laliga_predictor.api.settings import Settings  # noqa: E402


ADMIN_KEY = "phase16-test-key-with-more-than-32-characters"


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "database_url": f"sqlite:///{tmp_path / 'phase16.db'}",
        "project_root": tmp_path,
        "auto_sync": False,
        "automation_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_missing_or_weak_admin_key(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="required in production"):
        _settings(tmp_path, environment="production")
    with pytest.raises(ValueError, match="at least 32"):
        _settings(
            tmp_path,
            environment="production",
            admin_api_key="too-short",
        )


def test_security_headers_and_host_validation(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/health")
        rejected_host = client.get(
            "/health", headers={"host": "untrusted.example"}
        )

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]
    assert rejected_host.status_code == 400


def test_admin_key_protects_mutating_endpoints(tmp_path: Path) -> None:
    settings = _settings(tmp_path, admin_api_key=ADMIN_KEY)
    with TestClient(create_app(settings)) as client:
        missing = client.post("/models/retrain")
        wrong = client.post(
            "/models/retrain", headers={"X-API-Key": "x" * 32}
        )
        accepted = client.post(
            "/models/retrain", headers={"X-API-Key": ADMIN_KEY}
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert accepted.status_code == 201
    assert accepted.json()["status"] == "not_ready"


def test_production_disables_docs_and_limits_request_size(
    tmp_path: Path,
) -> None:
    settings = _settings(
        tmp_path,
        environment="production",
        admin_api_key=ADMIN_KEY,
        docs_enabled=False,
        allowed_hosts=("testserver",),
        cors_origins=("https://laliga.example",),
        max_request_body_bytes=1_024,
    )
    with TestClient(create_app(settings)) as client:
        docs = client.get("/docs")
        openapi = client.get("/openapi.json")
        oversized = client.post(
            "/update-matchday",
            content=b"x" * 2_048,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": ADMIN_KEY,
            },
        )
        health = client.get("/health")

    assert docs.status_code == 404
    assert openapi.status_code == 404
    assert oversized.status_code == 413
    assert health.headers["strict-transport-security"].startswith(
        "max-age=31536000"
    )


def test_offline_release_verifier_passes(tmp_path: Path) -> None:
    output = tmp_path / "release.json"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "verify_release.py"),
            "--offline",
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "passed"
    assert report["checks_passed"] == report["checks_total"]
