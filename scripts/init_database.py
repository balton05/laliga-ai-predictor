from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.api.database import (  # noqa: E402
    Base,
    build_engine,
    build_session_factory,
)
from laliga_predictor.api.analytics import apply_powerbi_views  # noqa: E402
from laliga_predictor.api.service import DataSyncService  # noqa: E402
from laliga_predictor.api.settings import Settings  # noqa: E402


if __name__ == "__main__":
    settings = Settings.from_env()
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    service = DataSyncService(
        settings.project_root, build_session_factory(engine)
    )
    summary = service.sync_current_state()
    views_installed = apply_powerbi_views(engine, settings.project_root)
    print(
        json.dumps(
            {
                "database_initialized": True,
                "update_id": summary["update_id"],
                "fixtures": 380,
                "predictions": summary["remaining_matches"],
                "completed_matches": summary["completed_matches"],
                "powerbi_views_installed": views_installed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
