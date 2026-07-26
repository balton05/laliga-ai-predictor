from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor.dynamic import (  # noqa: E402
    DEFAULT_ODDS_PATH,
    DEFAULT_RESULTS_PATH,
    run_phase9,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update LaLiga 2026/27 results, features, predictions and "
            "Monte Carlo simulation."
        )
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=DEFAULT_RESULTS_PATH,
        help="Canonical results CSV.",
    )
    parser.add_argument(
        "--odds",
        type=Path,
        default=DEFAULT_ODDS_PATH,
        help="Latest 1X2 odds CSV.",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=50_000,
        help="Number of Monte Carlo seasons.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Reproducible random seed.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow a live update before all 10 matches of a matchday finish.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    summary = run_phase9(
        results_path=args.results,
        odds_path=args.odds,
        simulations=args.simulations,
        seed=args.seed,
        allow_partial=args.allow_partial,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
