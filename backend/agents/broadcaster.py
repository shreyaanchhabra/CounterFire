"""Broadcaster (Grok). STUB: owned by the Grok side.

Contract: run(framing_key, post_en, post_es, replies) -> BroadcastOut.
replies are the scenario's scripted_replies [{who, text}]. Answers are short, friendly,
point to ReadySanDiego, never invent new orders. Posts go to the in-app feed only.
Until this is built, /api/broadcast uses data/fixtures/broadcast.json.
"""
from ..schemas import BroadcastOut


async def run(framing_key: str, post_en: str, post_es: str | None, replies: list[dict]) -> BroadcastOut:
    raise NotImplementedError("Broadcaster (Grok) not built yet")
