"""Defender (Gemini): steelmans the claim so the Judge hears both sides."""
from ..clients.gemini_client import gemini_json
from ..gemini_schemas import DefenderOut
from ._util import short

SYSTEM = "You are the Defender in a fact-checking debate for a county emergency communications team."

PROMPT = """A social media post claims: "{claim}"
{image_line}
Context: {context}

Argue as strongly and honestly as you can that the post could be real. Give up to 3 short points,
each under 50 characters. Don't make things up. If support is weak, say so in a point like "Little support beyond timing"."""


async def run(claim: str, context: str, image: bytes | None = None, mime: str | None = None) -> DefenderOut:
    image_line = "The attached image was posted with it." if image else ""
    out = await gemini_json(PROMPT.format(claim=claim, image_line=image_line, context=context or "none given"),
                            DefenderOut, image, mime, system=SYSTEM, temperature=0.4)
    return DefenderOut(bullets=[short(b, 50) for b in out.bullets if b.strip()][:3])
