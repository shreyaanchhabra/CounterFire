import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
FIXTURES = DATA / "fixtures"
FRONTEND = ROOT / "frontend"
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip()
GEMINI_JUDGE_MODEL = os.getenv("GEMINI_JUDGE_MODEL", "").strip()
# Comma-separated, tried in order when a model is overloaded (503) or out of quota (429).
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODEL", "").split(",") if m.strip()]
XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
GROK_MODEL = os.getenv("GROK_MODEL", "").strip()
GROK_FAST_MODEL = os.getenv("GROK_FAST_MODEL", "").strip() or GROK_MODEL
VOISKEY_API_KEY = os.getenv("VOISKEY_API_KEY", "").strip()
VOISKEY_BASE_URL = os.getenv("VOISKEY_BASE_URL", "").strip()

DEMO_MODE = os.getenv("DEMO_MODE", "hybrid").strip().lower()
if DEMO_MODE not in ("replay", "live", "hybrid"):
    DEMO_MODE = "hybrid"

# Seconds before a live call gives up and falls back to cache.
# The Prosecutor makes 2 rounds of Gemini calls, so it gets more time than the plan's 8s.
TIMEOUTS = {
    "scout": 15, "prosecutor": 35, "defender": 20, "judge": 20, "drafter": 20,
    "society": 30, "editor": 25, "broadcast": 15, "draft_ask": 10, "analyze": 60,
}


def scenario() -> dict:
    return json.loads((DATA / "scenario_sd1024.json").read_text(encoding="utf-8"))
