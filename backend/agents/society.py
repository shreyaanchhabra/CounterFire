"""Society Sim (Grok bots). STUB: owned by the Grok side.

Contract: run(framings, claim) -> SocietyAll with one SocietyOut per framing.
scores has 6 entries in GROUPS order: 0 Poway residents, 1 Escondido parents (ES),
2 Local influencers, 3 Retirees on Facebook, 4 Reporters, 5 Skeptics.
Until this is built, the pipeline uses data/fixtures/society.json.
"""
from ..schemas import Framing, SocietyAll


async def run(framings: list[Framing], claim: str) -> SocietyAll:
    raise NotImplementedError("Society Sim (Grok) not built yet")
