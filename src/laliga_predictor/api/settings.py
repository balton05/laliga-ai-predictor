from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from laliga_predictor.config import PROJECT_ROOT


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://laliga:laliga@localhost:5432/laliga_predictor"
)
DEFAULT_FOOTBALL_DATA_URL = (
    "https://www.football-data.co.uk/mmz4281/2627/SP1.csv"
)
FALSE_VALUES = {"0", "false", "no", "off"}


def _environment_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in FALSE_VALUES


def _environment_tuple(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in os.getenv(name, default).split(",")
        if value.strip()
    )


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    database_url: str = DEFAULT_DATABASE_URL
    project_root: Path = PROJECT_ROOT
    api_title: str = "LaLiga AI Predictor API"
    api_version: str = "1.6.0"
    environment: str = "development"
    auto_sync: bool = True
    automation_enabled: bool = True
    automation_interval_minutes: int = 360
    automation_source_url: str = DEFAULT_FOOTBALL_DATA_URL
    automation_timeout_seconds: int = 30
    automation_simulations: int = 50_000
    automation_seed: int = 42
    retraining_minimum_matches: int = 80
    retraining_minimum_matchdays: int = 8
    admin_api_key: str | None = None
    docs_enabled: bool = True
    security_headers_enabled: bool = True
    max_request_body_bytes: int = 1_000_000
    cors_origins: tuple[str, ...] = (
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    )
    allowed_hosts: tuple[str, ...] = (
        "localhost",
        "127.0.0.1",
        "testserver",
        "api",
    )

    def __post_init__(self) -> None:
        environment = self.environment.strip().lower()
        if environment not in {"development", "test", "production"}:
            raise ValueError(
                "LALIGA_ENVIRONMENT must be development, test or production."
            )
        object.__setattr__(self, "environment", environment)

        if self.admin_api_key and len(self.admin_api_key) < 32:
            raise ValueError(
                "LALIGA_ADMIN_API_KEY must contain at least 32 characters."
            )
        if self.max_request_body_bytes < 1_024:
            raise ValueError(
                "LALIGA_MAX_REQUEST_BODY_BYTES must be at least 1024."
            )
        if environment == "production":
            if not self.admin_api_key:
                raise ValueError(
                    "LALIGA_ADMIN_API_KEY is required in production."
                )
            if "*" in self.allowed_hosts:
                raise ValueError(
                    "Wildcard hosts are not allowed in production."
                )
            if "*" in self.cors_origins:
                raise ValueError(
                    "Wildcard CORS origins are not allowed in production."
                )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv(
            "LALIGA_ENVIRONMENT", "development"
        ).strip().lower()
        docs_default = environment != "production"
        admin_api_key = os.getenv("LALIGA_ADMIN_API_KEY", "").strip() or None
        return cls(
            database_url=os.getenv(
                "LALIGA_DATABASE_URL", DEFAULT_DATABASE_URL
            ),
            project_root=Path(
                os.getenv("LALIGA_PROJECT_ROOT", str(PROJECT_ROOT))
            ).resolve(),
            environment=environment,
            auto_sync=_environment_bool("LALIGA_AUTO_SYNC", True),
            automation_enabled=_environment_bool(
                "LALIGA_AUTOMATION_ENABLED", True
            ),
            automation_interval_minutes=max(
                15,
                int(os.getenv("LALIGA_AUTOMATION_INTERVAL_MINUTES", "360")),
            ),
            automation_source_url=os.getenv(
                "LALIGA_FOOTBALL_DATA_URL", DEFAULT_FOOTBALL_DATA_URL
            ),
            automation_timeout_seconds=max(
                5,
                int(os.getenv("LALIGA_AUTOMATION_TIMEOUT_SECONDS", "30")),
            ),
            automation_simulations=max(
                100,
                min(
                    100_000,
                    int(os.getenv("LALIGA_AUTOMATION_SIMULATIONS", "50000")),
                ),
            ),
            automation_seed=int(
                os.getenv("LALIGA_AUTOMATION_SEED", "42")
            ),
            retraining_minimum_matches=max(
                30,
                int(os.getenv("LALIGA_RETRAIN_MINIMUM_MATCHES", "80")),
            ),
            retraining_minimum_matchdays=max(
                3,
                int(os.getenv("LALIGA_RETRAIN_MINIMUM_MATCHDAYS", "8")),
            ),
            admin_api_key=admin_api_key,
            docs_enabled=_environment_bool(
                "LALIGA_DOCS_ENABLED", docs_default
            ),
            security_headers_enabled=_environment_bool(
                "LALIGA_SECURITY_HEADERS_ENABLED", True
            ),
            max_request_body_bytes=max(
                1_024,
                int(
                    os.getenv(
                        "LALIGA_MAX_REQUEST_BODY_BYTES", "1000000"
                    )
                ),
            ),
            cors_origins=_environment_tuple(
                "LALIGA_CORS_ORIGINS",
                "http://localhost:4200,http://127.0.0.1:4200",
            ),
            allowed_hosts=_environment_tuple(
                "LALIGA_ALLOWED_HOSTS",
                "localhost,127.0.0.1,testserver,api",
            ),
        )
