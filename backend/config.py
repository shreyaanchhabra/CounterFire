"""Explicit configuration. Importing agents never requires credentials."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    model: str = ""
    fast_model: str = ""
    mode: str = "hybrid"
    timeout: float = 8
    cache_dir: Path = ROOT / "cache"

    def __post_init__(self):
        if self.mode not in {"live", "replay", "hybrid"}:
            raise ValueError("DEMO_MODE must be live, replay, or hybrid")
        if self.timeout <= 0 or self.timeout > 120:
            raise ValueError("GROK_TIMEOUT_SECONDS must be between 0 and 120")

    @classmethod
    def from_env(cls, env_file: Path | None = None):
        load_dotenv(env_file or ROOT / ".env", override=False)
        cache_dir = Path(os.getenv("FIREBREAK_CACHE_DIR", "cache"))
        if not cache_dir.is_absolute():
            cache_dir = ROOT / cache_dir
        return cls(api_key=os.getenv("XAI_API_KEY", "").strip(),
                   model=os.getenv("GROK_MODEL", "").strip(),
                   fast_model=os.getenv("GROK_FAST_MODEL", "").strip(),
                   mode=os.getenv("DEMO_MODE", "hybrid").strip(),
                   timeout=float(os.getenv("GROK_TIMEOUT_SECONDS", "8")),
                   cache_dir=cache_dir)
