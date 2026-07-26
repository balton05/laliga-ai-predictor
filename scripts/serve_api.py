from __future__ import annotations

import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


if __name__ == "__main__":
    uvicorn.run(
        "laliga_predictor.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        app_dir=str(SRC),
    )
