from __future__ import annotations

import argparse
import json
import logging
import sys
import time
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
from laliga_predictor.api.settings import Settings  # noqa: E402
from laliga_predictor.automation import (  # noqa: E402
    AutomationConfig,
    AutomationRunner,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated LaLiga 2026/27 update pipeline."
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep checking Football-Data at the configured interval.",
    )
    parser.add_argument(
        "--trigger",
        default="scheduled",
        choices=["scheduled", "manual", "startup"],
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args()
    settings = Settings.from_env()
    if not settings.automation_enabled:
        print(
            json.dumps(
                {
                    "status": "disabled",
                    "message": "LALIGA_AUTOMATION_ENABLED is false.",
                }
            )
        )
        return 0
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    runner = AutomationRunner(
        settings.project_root,
        build_session_factory(engine),
        AutomationConfig(
            source_url=settings.automation_source_url,
            timeout_seconds=settings.automation_timeout_seconds,
            simulations=settings.automation_simulations,
            seed=settings.automation_seed,
        ),
    )

    while True:
        try:
            run = runner.run_once(trigger=args.trigger)
            print(
                json.dumps(
                    {
                        "run_id": run.run_id,
                        "status": run.status,
                        "started_at_utc": run.started_at_utc.isoformat(),
                        "finished_at_utc": (
                            run.finished_at_utc.isoformat()
                            if run.finished_at_utc
                            else None
                        ),
                        "results_added": run.results_added,
                        "odds_added": run.odds_added,
                        "update_id": run.update_id,
                        "error_message": run.error_message,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception:
            logging.exception("The scheduled iteration failed.")
        if not args.loop:
            break
        time.sleep(settings.automation_interval_minutes * 60)
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
