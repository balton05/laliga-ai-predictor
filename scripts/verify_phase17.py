from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "Dockerfile.render",
    "requirements.runtime.txt",
    "render.yaml",
    ".github/workflows/ci.yml",
    ".github/workflows/season-automation.yml",
    "docs/phase17_free_deployment.md",
    "scripts/serve_render.py",
    "src/laliga_predictor/deployment.py",
    "tests/test_phase17.py",
)
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    "GitHub fine-grained token": re.compile(
        r"github_pat_[A-Za-z0-9_]{20,}"
    ),
    "OpenAI key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "private key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
}


def _check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    marker = "PASS" if passed else "FAIL"
    print(f"[{marker}] {name}: {detail}")


def _request(url: str) -> tuple[int, str, dict[str, str]]:
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/json",
            "User-Agent": "laliga-phase17-verifier/1.0",
        },
    )
    with urlopen(request, timeout=90) as response:
        return (
            response.status,
            response.read().decode("utf-8"),
            {key.lower(): value for key, value in response.headers.items()},
        )


def verify_source(root: Path, checks: list[dict[str, Any]]) -> None:
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    _check(
        checks,
        "deployment_files",
        not missing,
        "complete" if not missing else f"missing: {', '.join(missing)}",
    )

    render_text = (root / "render.yaml").read_text(encoding="utf-8")
    render_safe = all(
        fragment in render_text
        for fragment in (
            "plan: free",
            "runtime: docker",
            "healthCheckPath: /api/health",
            "LALIGA_DATABASE_URL",
            "sync: false",
            "LALIGA_ADMIN_API_KEY",
            "generateValue: true",
        )
    )
    _check(
        checks,
        "free_render_blueprint",
        render_safe,
        "free web service with external secret database",
    )

    automation_text = (
        root / ".github" / "workflows" / "season-automation.yml"
    ).read_text(encoding="utf-8")
    automation_safe = all(
        fragment in automation_text
        for fragment in (
            "workflow_dispatch:",
            "schedule:",
            "timezone: \"America/Lima\"",
            "secrets.LALIGA_DATABASE_URL",
            "secrets.LALIGA_ADMIN_API_KEY",
            "permissions:",
            "contents: read",
        )
    )
    _check(
        checks,
        "scheduled_automation",
        automation_safe,
        "manual and Lima-time schedule with least privilege",
    )

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    ignored = all(
        pattern in gitignore
        for pattern in (
            ".env",
            ".test-venv/",
            "frontend/.angular/",
            "frontend/dist/",
        )
    )
    _check(
        checks,
        "publication_exclusions",
        ignored,
        "local secrets, environments and builds are ignored",
    )

    deployment_files = [
        root / "render.yaml",
        root / "Dockerfile.render",
        root / ".github" / "workflows" / "season-automation.yml",
    ]
    findings: list[str] = []
    for path in deployment_files:
        text = path.read_text(encoding="utf-8")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.name}: {label}")
    _check(
        checks,
        "no_embedded_secrets",
        not findings,
        "none" if not findings else ", ".join(findings),
    )

    angular = (root / "frontend" / "angular.json").read_text(
        encoding="utf-8"
    )
    csp_compatible = '"inlineCritical": false' in angular
    _check(
        checks,
        "csp_compatible_styles",
        csp_compatible,
        "Angular critical CSS inline handler is disabled",
    )


def verify_live(
    base_url: str,
    checks: list[dict[str, Any]],
) -> None:
    base = base_url.rstrip("/")
    status, html, headers = _request(f"{base}/")
    web_ok = (
        status == 200
        and "<base href=\"/\">" in html
        and "Content-Security-Policy".lower() in headers
    )
    _check(
        checks,
        "public_frontend",
        web_ok,
        f"{base}/ returned HTTP {status}",
    )

    health_status, body, _ = _request(f"{base}/api/health")
    health = json.loads(body)
    api_ok = (
        health_status == 200
        and health.get("status") == "ok"
        and health.get("database") == "connected"
    )
    _check(
        checks,
        "public_api_database",
        api_ok,
        (
            f"HTTP {health_status}, status={health.get('status')}, "
            f"database={health.get('database')}"
        ),
    )

    favicon_status, _, _ = _request(f"{base}/favicon.ico")
    _check(
        checks,
        "public_favicon",
        favicon_status == 200,
        f"HTTP {favicon_status}",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Phase 17 source and optional public deployment."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_ROOT,
    )
    parser.add_argument("--base-url")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/phase17_deployment_check.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    checks: list[dict[str, Any]] = []
    verify_source(root, checks)
    if args.base_url:
        try:
            verify_live(args.base_url, checks)
        except Exception as exc:
            _check(checks, "public_deployment", False, str(exc))

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "passed" if all(check["passed"] for check in checks) else "failed"
        ),
        "checks_passed": sum(check["passed"] for check in checks),
        "checks_total": len(checks),
        "base_url": args.base_url,
        "checks": checks,
    }
    output = args.output
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Report: {output}")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
