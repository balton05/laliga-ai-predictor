from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from laliga_predictor.config import PROJECT_ROOT


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://laliga:laliga@localhost:5432/laliga_predictor"
)


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    database_url: str = DEFAULT_DATABASE_URL
    project_root: Path = PROJECT_ROOT
    api_title: str = "LaLiga AI Predictor API"
    api_version: str = "1.0.0"
    auto_sync: bool = True
    cors_origins: tuple[str, ...] = (
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        cors_origins = tuple(
            origin.strip()
            for origin in os.getenv(
                "LALIGA_CORS_ORIGINS",
                "http://localhost:4200,http://127.0.0.1:4200",
            ).split(",")
            if origin.strip()
        )
        return cls(
            database_url=os.getenv(
                "LALIGA_DATABASE_URL", DEFAULT_DATABASE_URL
            ),
            project_root=Path(
                os.getenv("LALIGA_PROJECT_ROOT", str(PROJECT_ROOT))
            ).resolve(),
            auto_sync=os.getenv("LALIGA_AUTO_SYNC", "true").lower()
            not in {"0", "false", "no"},
            cors_origins=cors_origins,
        )
