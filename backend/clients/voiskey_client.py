"""Voiskey adapter.

Voiskey (voiskey.ai) is a system-wide speak-to-type desktop app with no public API or SDK
(checked Oct 24 2026). It's integrated through the UI instead:
  - Dictation (hold Right Alt): Voiskey types a cleaned note into the Editor's dictation box,
    which POSTs it to /api/voice with source="voiskey".
  - Translation (Right Alt + Right Shift): dictate straight into the editable Spanish post.
If Voiskey ships an API later, implement transcribe_and_clean and the mic path will use it.
"""
from .. import config


class VoiskeyClient:
    def available(self) -> bool:
        return bool(config.VOISKEY_API_KEY or config.VOISKEY_BASE_URL)

    async def transcribe_and_clean(self, audio: bytes, mime: str) -> tuple[str, str]:
        """Return (raw_transcript, clean_text)."""
        raise NotImplementedError("Voiskey has no API; the mic path falls back to Gemini")
