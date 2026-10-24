"""Gemini verification: Prosecutor + Defender in parallel, then Judge, and the evidence packet
the Grok desk imports (POST /api/episodes/{id}/evidence contract in FIREBREAK_PLAN.md section 7)."""
import asyncio
import hashlib

from . import config
from .agents import defender, judge, prosecutor
from .agents._util import image_hash
from .cache import get_or_run
from .clients import gemini_client
from .schemas import DefenderOut, JudgeOut, ProsecutorOut


def context_line(ctx: dict) -> str:
    return (f"Posted {ctx.get('post_time', 'unknown')} at {ctx.get('location', 'unknown')}. "
            f"{ctx.get('known_facts', '')}").strip()


def judge_targets(ctx: dict) -> list[str]:
    return [t for t in [ctx.get("poster")] + ctx.get("agencies", []) if t]


async def analyze(image: bytes, mime: str, claim: str, ctx: dict, live: bool):
    """Returns (pro, status), (defender, status), (judge, status), image_hash.

    live=False prefers cache in hybrid mode (the scripted scenario). live=True is a new upload:
    it never falls back to scripted findings, since those would describe a different image."""
    h = image_hash(image)
    k = f"{h}_{hashlib.sha1(claim.encode()).hexdigest()[:6]}"  # same image with a different claim is a new case
    fx = (lambda n: n) if not live else (lambda n: None)
    t = config.TIMEOUTS
    (pro, s1), (dfn, s2) = await asyncio.gather(
        get_or_run(f"prosecutor_{k}", lambda: prosecutor.run(image, mime, claim, ctx), ProsecutorOut,
                   t["prosecutor"], live=live, fixture_name=fx("prosecutor")),
        get_or_run(f"defender_{k}", lambda: defender.run(claim, context_line(ctx), image, mime), DefenderOut,
                   t["defender"], live=live, fixture_name=fx("defender")),
    )
    jdg, s3 = await get_or_run(f"judge_{k}", lambda: judge.run(claim, pro, dfn, judge_targets(ctx)), JudgeOut,
                               t["judge"], live=live, fixture_name=fx("judge"))
    return (pro, s1), (dfn, s2), (jdg, s3), h


def evidence_packet(pro: ProsecutorOut, dfn: DefenderOut, jdg: JudgeOut, *, h: str, status: str, sc: dict) -> dict:
    """The versioned packet the Grok desk stores, shows, and delivers to community Bots as evidence.

    verified_facts are Gemini's observations of the image (what it shows), not claims about
    current conditions. Safety guidance comes from the scenario's trusted bulletin."""
    bulletin = sc.get("verification", {})
    try:
        model = gemini_client.model() if config.GEMINI_API_KEY else None
    except Exception:  # noqa: BLE001 - model listing needs network; the packet doesn't
        model = config.GEMINI_MODEL or None
    return {
        "incident_id": sc["incident_id"],
        "claim": sc["claim"],
        "source": "gemini" if status == "done" or status == "cached" else "gemini-fixture",
        "status": status,
        "model": model,
        "image_hash": h,
        "verdict": jdg.verdict,
        "confidence": jdg.confidence,
        "reasoning": jdg.reasoning,
        "findings": [f.model_dump() for f in pro.findings],
        "prosecutor": pro.bullets,
        "defender": dfn.bullets,
        "missing": [m.model_dump() for m in jdg.missing],
        "verified_facts": [f.label for f in pro.findings] or [jdg.reasoning],
        "safety_action": bulletin.get("safety_action", "Check official evacuation updates before sharing."),
        "official_source": bulletin.get("official_source", "https://www.readysandiego.org/"),
        "source_refs": [f"image:{h}"],
    }
