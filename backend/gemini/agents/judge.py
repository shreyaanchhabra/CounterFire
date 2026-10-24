"""Judge (Gemini): verdict, calibrated confidence, and what evidence is missing. Strict JSON."""
from ..clients.gemini_client import gemini_json, judge_model
from ..schemas import DefenderOut, JudgeOut, MissingEvidence, ProsecutorOut
from ._util import short

SYSTEM = "You are the Judge in a fact-checking debate for a county emergency communications team. You are calibrated and fair."

PROMPT = """Claim: "{claim}"

Prosecutor (argues the post is false):
{pro}

Defender (argues the post could be real):
{defn}

Output:
- verdict: "False" (the claim is wrong), "Misleading" (real elements, wrong framing or place or time),
  "Unverified" (not enough evidence either way), or "True".
- confidence from 0 to 100. Be calibrated: only go above 90 if location or provenance evidence is decisive.
- reasoning: one or two plain sentences.
- missing: up to 2 pieces of evidence that would most change your confidence, each with who to ask.
  item is a short noun phrase under 40 characters, like "Original file from uploader" or "Fire perimeter after 7:30 PM".
  ask_target must be one of: {targets}."""


def _fmt_pro(p: ProsecutorOut) -> str:
    lines = [f"- {f.label}" for f in p.findings] + [f"- {b}" for b in p.bullets]
    return "\n".join(lines) or "- (no points)"


async def run(claim: str, pro: ProsecutorOut, defn: DefenderOut, targets: list[str]) -> JudgeOut:
    targets = targets or ["the original poster", "the local fire agency"]
    out = await gemini_json(
        PROMPT.format(claim=claim, pro=_fmt_pro(pro), defn="\n".join(f"- {b}" for b in defn.bullets) or "- (no points)",
                      targets=", ".join(targets)),
        JudgeOut, system=SYSTEM, temperature=0.1, model_name=judge_model())
    return JudgeOut(
        verdict=out.verdict,
        confidence=max(0, min(100, out.confidence)),
        reasoning=short(out.reasoning, 240),
        missing=[MissingEvidence(item=short(m.item, 70), ask_target=m.ask_target) for m in out.missing[:2]],
    )
