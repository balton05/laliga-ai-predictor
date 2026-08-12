from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


if __name__ == "__main__":
    uvicorn.run(
        "laliga_predictor.deployment:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
        app_dir=str(SRC),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
