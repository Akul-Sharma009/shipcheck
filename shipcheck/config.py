"""Settings: secrets, model IDs and cost limits.

Values come from st.secrets (Streamlit Cloud) and fall back to environment variables / .env (local).
Never hardcode keys here.
"""
import os
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        import streamlit as st
        return str(st.secrets[name])
    except Exception:
        return os.getenv(name, default)


def _int(name: str, default: int) -> int:
    v = get_secret(name)
    try:
        return int(v) if v not in (None, "") else default
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = get_secret(name)
    if v in (None, ""):
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ---------- services ----------
TOKEN_FACTORY_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
NEBIUS_API_KEY = get_secret("NEBIUS_API_KEY")
TAVILY_API_KEY = get_secret("TAVILY_API_KEY")
GITHUB_TOKEN = get_secret("GITHUB_TOKEN")

# ---------- models (IDs are case-sensitive; verified in pre-flight) ----------
MODEL_NANO = get_secret("MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
MODEL_SUPER = get_secret("MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b")
MODEL_ULTRA = get_secret("MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b")

# Output budget per call. Reasoning tokens count against it, so llm.call_json may double it once,
# but never past MAX_TOKENS_CEILING.
MAX_TOKENS_NANO = _int("MAX_TOKENS_NANO", 1500)
MAX_TOKENS_SUPER = _int("MAX_TOKENS_SUPER", 6000)
MAX_TOKENS_ULTRA = _int("MAX_TOKENS_ULTRA", 6000)
MAX_TOKENS_CEILING = _int("MAX_TOKENS_CEILING", 12000)
LLM_TIMEOUT_S = _int("LLM_TIMEOUT_S", 120)
# Send enable_thinking=false to Nano (per-file summaries don't need reasoning).
NANO_DISABLE_THINKING = _bool("NANO_DISABLE_THINKING", True)
# Rules extraction is transcription, not reasoning: thinking off was 6x faster at similar quality.
RULES_THINKING = _bool("RULES_THINKING", False)

# ---------- repo ingestion limits ----------
MAX_FILES = _int("MAX_FILES", 40)
MAX_FILE_BYTES = _int("MAX_FILE_BYTES", 50_000)
MAX_TOTAL_BYTES = _int("MAX_TOTAL_BYTES", 200_000)

# ---------- cost guardrails ----------
MAX_RUNS_PER_SESSION = _int("MAX_RUNS_PER_SESSION", 5)
MAX_UNCACHED_RUNS_PER_DAY = _int("MAX_UNCACHED_RUNS_PER_DAY", 100)
# Kill switch: false = never call paid APIs, serve cached examples only.
LIVE = _bool("SHIPCHECK_LIVE", True)


def missing_keys() -> List[str]:
    return [k for k, v in (("NEBIUS_API_KEY", NEBIUS_API_KEY), ("TAVILY_API_KEY", TAVILY_API_KEY),
                           ("GITHUB_TOKEN", GITHUB_TOKEN)) if not v]
