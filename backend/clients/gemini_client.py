"""Gemini client (async). All Gemini agents go through these helpers."""
import logging
import re

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from .. import config

log = logging.getLogger("firebreak.gemini")

_client: genai.Client | None = None
_auto_model: str | None = None


class GeminiNotConfigured(RuntimeError):
    pass


def client() -> genai.Client:
    global _client
    if not config.GEMINI_API_KEY:
        raise GeminiNotConfigured("GEMINI_API_KEY is not set in .env")
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _version(name: str) -> tuple:
    return tuple(float(x) for x in re.findall(r"\d+(?:\.\d+)?", name)[:1]) or (0.0,)


def list_text_models() -> list[str]:
    """Model names this key can call with generateContent."""
    names = []
    for m in client().models.list():
        actions = getattr(m, "supported_actions", None) or []
        if actions and "generateContent" not in actions:
            continue
        names.append(m.name.removeprefix("models/"))
    return names


def pick_flash(names: list[str]) -> str | None:
    """Newest stable-looking Flash model (not lite, image, tts, live or audio variants)."""
    skip = ("lite", "image", "tts", "live", "audio", "thinking", "exp", "embedding", "8b")
    flash = [n for n in names if n.startswith("gemini-") and "flash" in n and not any(s in n for s in skip)]
    flash.sort(key=lambda n: (_version(n), "preview" not in n, -len(n)), reverse=True)
    return flash[0] if flash else None


def model() -> str:
    global _auto_model
    if config.GEMINI_MODEL:
        return config.GEMINI_MODEL
    if _auto_model is None:
        _auto_model = pick_flash(list_text_models()) or "gemini-2.5-flash"
        log.info("GEMINI_MODEL not set, using %s", _auto_model)
    return _auto_model


def judge_model() -> str:
    return config.GEMINI_JUDGE_MODEL or model()


def _parts(prompt: str, media: bytes | None, mime: str | None):
    parts = []
    if media:
        parts.append(types.Part.from_bytes(data=media, mime_type=mime or "image/png"))
    parts.append(prompt)
    return parts


async def gemini_json(prompt: str, schema: type[BaseModel], media: bytes | None = None, mime: str | None = None,
                      system: str | None = None, temperature: float = 0.2, model_name: str | None = None):
    """Structured output validated by Pydantic. Retries once on a bad parse."""
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
        system_instruction=system,
    )
    last = None
    for _ in range(2):
        resp = await client().aio.models.generate_content(
            model=model_name or model(), contents=_parts(prompt, media, mime), config=cfg)
        try:
            if isinstance(resp.parsed, schema):
                return resp.parsed
            return schema.model_validate_json(resp.text or "")
        except ValidationError as e:
            last = e
            log.warning("Gemini returned bad JSON for %s, retrying", schema.__name__)
    raise last


async def gemini_text(prompt: str, media: bytes | None = None, mime: str | None = None,
                      system: str | None = None, temperature: float = 0.4) -> str:
    resp = await client().aio.models.generate_content(
        model=model(), contents=_parts(prompt, media, mime),
        config=types.GenerateContentConfig(temperature=temperature, system_instruction=system))
    return (resp.text or "").strip()


async def gemini_grounded_text(prompt: str, media: bytes | None = None, mime: str | None = None) -> str:
    """Google Search grounding. Returns plain text; structure it with gemini_json in a second call,
    since some models don't allow grounding and a response schema in one call."""
    resp = await client().aio.models.generate_content(
        model=model(), contents=_parts(prompt, media, mime),
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.1))
    return (resp.text or "").strip()
