"""Voiskey adapter. Owned by the Voiskey side.

Fill in transcribe_and_clean once we know what Voiskey offers. Until then it raises
NotImplementedError and the Editor falls back to Gemini for transcription and cleanup.
If Voiskey turns out to be a desktop dictation app (no API), POST /api/voice also
accepts a `text` field, so dictated text can be sent instead of audio.
"""
from .. import config


class VoiskeyClient:
    def available(self) -> bool:
        return bool(config.VOISKEY_API_KEY or config.VOISKEY_BASE_URL)

    async def transcribe_and_clean(self, audio: bytes, mime: str) -> tuple[str, str]:
        """Return (raw_transcript, clean_text)."""
        raise NotImplementedError("Voiskey adapter not built yet")
