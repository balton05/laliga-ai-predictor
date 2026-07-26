from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laliga_predictor import run_phase1, run_phase2  # noqa: E402
from laliga_predictor.modeling import run_phase4  # noqa: E402


if __name__ == "__main__":
    run_phase1()
    run_phase2()
    print(json.dumps(run_phase4(), ensure_ascii=False, indent=2))

