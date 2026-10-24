"""Draft ask (Gemini): short message requesting a missing piece of evidence."""
from ..clients.gemini_client import gemini_json
from ..schemas import AskOut
from ._util import short

PROMPT = """Write a short, polite message from the San Diego County emergency comms team to {target},
asking for: {item}. It's about a viral post claiming: "{claim}".
Plain language, no em dashes, under 260 characters. If the target is a social media handle, start with it."""


async def run(item: str, ask_target: str, claim: str) -> AskOut:
    out = await gemini_json(PROMPT.format(target=ask_target, item=item, claim=claim), AskOut, temperature=0.5)
    return AskOut(text=short(out.text.replace("—", ", "), 280))


def template(item: str, ask_target: str) -> AskOut:
    """Used if Gemini is unreachable."""
    return AskOut(text=f"{ask_target}, this is San Diego County emergency comms. Could you share the {item.lower()}? "
                       "It helps us confirm what's happening. Thank you.")
