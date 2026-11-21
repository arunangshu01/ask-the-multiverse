"""Runtime settings for the Ask the Multiverse API."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load KEY=value lines from backend/.env (git-ignored) without overriding real env vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(BACKEND_DIR / ".env")

API_COMMON_PREFIX = "/multiverse/api/v1"

CORS_ORIGINS = [o for o in os.environ.get(
    "MULTIVERSE_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173",
).split(",") if o]

# Directory holding latest.json and the DuckDB serving files written by `python -m ingest`.
DATA_DIR = Path(os.environ.get("MULTIVERSE_DATA_DIR", BACKEND_DIR / "data" / "serve"))

MAX_PAGE = 200

# Multiverse Console (same providers as the portfolio's ask assistant). Without keys the
# console still answers the supported question shapes with its rule-based planner.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
LLM_TIMEOUT_S = float(os.environ.get("MULTIVERSE_LLM_TIMEOUT", "20"))

# Rate limits for /ask: per visitor (anonymous __session cookie, best effort) and site-wide.
ASK_PER_VISITOR_PER_MIN = float(os.environ.get("MULTIVERSE_ASK_PER_MIN", "6"))
ASK_PER_VISITOR_BURST = float(os.environ.get("MULTIVERSE_ASK_BURST", "6"))
ASK_GLOBAL_PER_MIN = float(os.environ.get("MULTIVERSE_ASK_GLOBAL_PER_MIN", "30"))
ASK_CACHE_SIZE = int(os.environ.get("MULTIVERSE_ASK_CACHE", "500"))
