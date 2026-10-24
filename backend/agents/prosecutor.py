"""Prosecutor (Gemini): image forensics with boxes, plus a Google Search provenance check.

Two rounds of calls:
  1. in parallel: vision findings with box_2d, and a grounded web search for earlier copies
  2. structure the search report into ProvenanceOut
Google Search grounding searches text, not images. If it finds no specific earlier copy,
we say nothing about provenance rather than invent one, and use the account age instead.
"""
import asyncio
import logging

from ..clients.gemini_client import gemini_grounded_text, gemini_json
from ..schemas import Finding, ProsecutorOut, ProvenanceOut, VisionOut
from ._util import clean_box, short

log = logging.getLogger("firebreak.prosecutor")

SYSTEM = "You are a forensic image analyst for a county emergency communications team. You are careful and literal."

VISION_PROMPT = """A social media post claims: "{claim}"
Posted at: {post_time}. Claimed location: {location}.
Sunset that day: {sunset}.
{image_note}
Find evidence that this image is NOT what the post claims. Check:
- readable signs and text, and what places they name
- landmarks, road and terrain features
- light and shadows vs the claimed time of day
- weather and smoke direction
- signs of editing or AI generation

Rules:
- Only report what you can actually see. Do not invent evidence. If something is consistent with the claim, leave it out.
- For each finding, box_2d is [ymin, xmin, ymax, xmax] normalized to 0-1000, drawn tightly around the evidence.
- Up to 3 findings, strongest first, ids 1, 2, 3.
- label: plain language, under 90 characters. Example: "Sign reads Loop 101, Scottsdale Rd. That's Arizona, not I-15."
- bullets: up to 3 very short points (under 50 characters each) for the case against the post.
- image_description: 2 or 3 literal sentences describing the scene and any visible text."""

SEARCH_PROMPT = """Search the web. Has this exact image, or a photo clearly matching it, been published online before {date}?
Visible clues: road sign text, landscape, fire. The post claims: "{claim}".
Only report a match if you find a specific earlier page with a date. If you find nothing reliable, say "No earlier copy found"."""

STRUCTURE_PROMPT = """Here is a web search report about whether an image appeared online before {date}:

{report}

Extract: earlier_copy_found (true only if the report names a specific earlier page with a date),
earliest_date (like "June 2019") and source (site or URL). Use null when unknown."""

TEXT_PROMPT = """A claim is circulating: "{claim}"
{context}
You are the Prosecutor. Make the strongest honest case that this claim is false or misleading, using only well-established facts.
Do not invent evidence. findings: up to 3, box_2d null, category "other" unless another fits, label under 90 characters.
bullets: up to 3 short points under 50 characters. image_description: empty string."""


_search_blocked = False  # set after a quota error so we stop spending time on it


async def _provenance(image: bytes, mime: str, claim: str, date: str) -> ProvenanceOut | None:
    global _search_blocked
    if _search_blocked:
        return None
    try:
        report = await gemini_grounded_text(SEARCH_PROMPT.format(date=date, claim=claim), image, mime)
        return await gemini_json(STRUCTURE_PROMPT.format(date=date, report=report), ProvenanceOut)
    except Exception as e:  # noqa: BLE001 - provenance is optional (scope cut #4)
        _search_blocked = "429" in str(e)
        log.warning("provenance search failed: %s", str(e)[:120])
        return None


def _finalize(vision: VisionOut, prov: ProvenanceOut | None, account_age: str | None) -> ProsecutorOut:
    visual = []
    for f in vision.findings:
        visual.append(Finding(id=0, label=short(f.label, 90), box_2d=clean_box(f.box_2d), category=f.category))
    bullets = [short(b, 50) for b in vision.bullets if b.strip()]

    extra = None
    if prov and prov.earlier_copy_found and prov.earliest_date:
        src = f" on {prov.source}" if prov.source else ""
        extra = Finding(id=0, label=short(f"Earlier copy found{src}, from {prov.earliest_date}.", 90),
                        box_2d=None, category="provenance")
        bullets = bullets[:2] + [short(f"Photo online since {prov.earliest_date}", 50)]
    elif account_age:
        extra = Finding(id=0, label=f"Posted by an account that is {account_age} old.", box_2d=None, category="account")
        bullets = bullets[:2] + [short(f"Account is {account_age} old", 50)]

    findings = visual[:2] + [extra] if extra else visual[:3]
    for i, f in enumerate(findings, 1):
        f.id = i
    return ProsecutorOut(findings=findings, bullets=bullets[:3])


async def run(image: bytes, mime: str, claim: str, ctx: dict) -> ProsecutorOut:
    vision_task = gemini_json(
        VISION_PROMPT.format(claim=claim, post_time=ctx.get("post_time", "unknown"),
                             location=ctx.get("location", "unknown"), sunset=ctx.get("sunset", "unknown"),
                             image_note=ctx.get("image_note", "")),
        VisionOut, image, mime, system=SYSTEM)
    prov_task = _provenance(image, mime, claim, ctx.get("date", "today"))
    vision, prov = await asyncio.gather(vision_task, prov_task)
    return _finalize(vision, prov, ctx.get("account_age"))


async def run_text(claim: str, context: str = "") -> ProsecutorOut:
    """Text-only mode for the eval. No search grounding, so it can't just look up the fact check."""
    v = await gemini_json(TEXT_PROMPT.format(claim=claim, context=context), VisionOut, system=SYSTEM)
    findings = [Finding(id=i, label=short(f.label, 90), box_2d=None, category=f.category)
                for i, f in enumerate(v.findings[:3], 1)]
    return ProsecutorOut(findings=findings, bullets=[short(b, 50) for b in v.bullets[:3]])
