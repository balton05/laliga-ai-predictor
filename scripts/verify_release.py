from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "reports" / "phase16_release_check.json"
REQUIRED_FILES = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    ".env.example",
    ".env.production.example",
    ".github/workflows/ci.yml",
    "docker-compose.production.yml",
    "docs/architecture.md",
    "docs/security.md",
    "docs/testing_and_release.md",
)
CORE_FILES = (
    "src/laliga_predictor/api/main.py",
    "src/laliga_predictor/api/settings.py",
    "src/laliga_predictor/model_management.py",
    "src/laliga_predictor/evaluation.py",
    "frontend/src/app/data.service.ts",
    "frontend/nginx.conf",
    "Dockerfile",
)


def _check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_json(url: str) -> tuple[dict[str, Any], dict[str, str]]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
        headers = {key.lower(): value for key, value in response.headers.items()}
    return payload, headers


def verify_offline(checks: list[dict[str, Any]]) -> dict[str, str]:
    running_in_container = Path("/.dockerenv").exists()
    missing = [
        relative
        for relative in REQUIRED_FILES
        if (
            not (PROJECT_ROOT / relative).is_file()
            and not (
                running_in_container
                and relative == ".github/workflows/ci.yml"
            )
        )
    ]
    _check(
        checks,
        "release_documentation",
        not missing,
        "complete" if not missing else f"missing: {', '.join(missing)}",
    )

    accidental_env = (PROJECT_ROOT / ".env").exists()
    _check(
        checks,
        "no_local_env_in_release",
        not accidental_env,
        ".env is absent" if not accidental_env else ".env must not be packaged",
    )

    production_compose = (
        PROJECT_ROOT / "docker-compose.production.yml"
    ).read_text(encoding="utf-8")
    production_guards = (
        "${POSTGRES_PASSWORD:?" in production_compose
        and "${LALIGA_ADMIN_API_KEY:?" in production_compose
        and "internal: true" in production_compose
    )
    _check(
        checks,
        "production_secret_guards",
        production_guards,
        "required variables and private database network configured",
    )

    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    non_root = "USER laliga" in dockerfile and "HEALTHCHECK" in dockerfile
    _check(
        checks,
        "non_root_api_image",
        non_root,
        "non-root user and container healthcheck configured",
    )

    nginx = (
        PROJECT_ROOT / "frontend" / "nginx.conf"
    ).read_text(encoding="utf-8")
    hardened_web = all(
        token in nginx
        for token in (
            "X-Content-Type-Options",
            "Content-Security-Policy",
            "location /api/",
            "server_tokens off",
        )
    )
    _check(
        checks,
        "hardened_web_proxy",
        hardened_web,
        "same-origin API proxy and defensive headers configured",
    )

    fixtures = pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "fixtures_2026_27.csv"
    )
    predictions = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "current_predictions_2026_27.csv"
    )
    results = pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "current_results_2026_27.csv"
    )
    fixtures_valid = (
        len(fixtures) == 380
        and fixtures["fixture_id"].nunique() == 380
        and fixtures["matchday"].between(1, 38).all()
    )
    _check(
        checks,
        "fixture_contract",
        fixtures_valid,
        f"{len(fixtures)} rows; {fixtures['fixture_id'].nunique()} unique ids",
    )

    probability_columns = [
        "probability_home",
        "probability_draw",
        "probability_away",
    ]
    probability_sum = predictions[probability_columns].sum(axis=1)
    simplex_error = (
        0.0
        if predictions.empty
        else float(probability_sum.sub(1.0).abs().max())
    )
    probabilities_in_range = (
        predictions.empty
        or (
            predictions[probability_columns].ge(0).all().all()
            and predictions[probability_columns].le(1).all().all()
        )
    )
    fixture_ids = set(fixtures["fixture_id"])
    prediction_ids = set(predictions["fixture_id"])
    result_ids = set(results["fixture_id"]) if not results.empty else set()
    predictions_valid = (
        len(predictions) + len(results) == 380
        and predictions["fixture_id"].nunique() == len(predictions)
        and results["fixture_id"].nunique() == len(results)
        and prediction_ids.isdisjoint(result_ids)
        and prediction_ids | result_ids == fixture_ids
        and probabilities_in_range
        and simplex_error < 1e-8
    )
    _check(
        checks,
        "prediction_contract",
        predictions_valid,
        f"{len(predictions)} pending + {len(results)} completed; "
        f"max simplex error {simplex_error:.3e}",
    )

    return {
        relative: _sha256(PROJECT_ROOT / relative)
        for relative in CORE_FILES
    }


def verify_online(
    checks: list[dict[str, Any]],
    api_url: str,
) -> None:
    base = api_url.rstrip("/")
    try:
        health, headers = _request_json(f"{base}/health")
        healthy = (
            health.get("status") == "ok"
            and health.get("database") == "connected"
            and health.get("fixtures") == 380
            and health.get("predictions") == 380
        )
        _check(
            checks,
            "live_api_contract",
            healthy,
            (
                f"status={health.get('status')}; "
                f"fixtures={health.get('fixtures')}; "
                f"predictions={health.get('predictions')}"
            ),
        )
        secure_headers = all(
            name in headers
            for name in (
                "x-content-type-options",
                "x-frame-options",
                "referrer-policy",
                "x-request-id",
            )
        )
        _check(
            checks,
            "live_security_headers",
            secure_headers,
            "required response headers present",
        )

        models, _ = _request_json(f"{base}/models/status")
        _check(
            checks,
            "live_model_registry",
            bool(models.get("active_model")),
            f"active_model={models.get('active_model')}",
        )
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        _check(checks, "live_api_contract", False, str(exc))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the Phase 16 release contract."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip live API checks.",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL used for live checks.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON report destination.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks: list[dict[str, Any]] = []
    fingerprints = verify_offline(checks)
    if not args.offline:
        verify_online(checks, args.api_url)

    passed = all(item["passed"] for item in checks)
    report = {
        "phase": 16,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "checks_passed": sum(item["passed"] for item in checks),
        "checks_total": len(checks),
        "checks": checks,
        "core_file_sha256": fingerprints,
    }
    output = args.output
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    for item in checks:
        marker = "PASS" if item["passed"] else "FAIL"
        print(f"[{marker}] {item['name']}: {item['detail']}")
    print(f"Report: {output}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
