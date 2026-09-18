import os
import sys
from pathlib import Path

import uvicorn

# Ensure the backend package is importable when this script is invoked
# from anywhere (e.g. `python scripts/run_api.py` from the repo root).
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Default local-only overrides so the app runs without cloud credentials.
# Explicit environment variables take precedence over these defaults.
os.environ.setdefault("MEMORY_BACKEND", "local")
os.environ.setdefault("VECTOR_STORE", "in-memory")
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_MODEL", "hash:local")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)