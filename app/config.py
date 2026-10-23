"""Settings. Reads .env (no extra dependency) and decides which LLM engine to use."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse.db"
MAX_ATTEMPTS = 3      # how many times the agent may write/rewrite a query
ROW_LIMIT = 100       # rows auto-appended as LIMIT when the query has none
QUERY_TIMEOUT_S = 5   # a query running longer than this is aborted


def _load_env() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


_load_env()


def provider() -> str:
    """anthropic | openai (any OpenAI-compatible server, e.g. Ollama) | offline"""
    p = os.getenv("LLM_PROVIDER", "auto").lower()
    if p != "auto":
        return p
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_BASE_URL"):
        return "openai"
    return "offline"


def model_name() -> str:
    p = provider()
    if p == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    if p == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return "rule-based"
