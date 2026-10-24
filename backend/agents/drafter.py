"""Drafter (Grok). STUB: owned by the Grok side.

Contract: run(incident, judge) -> DrafterOut with framings A (Fact check), B (Action first),
C (Neighbor voice), each with text_en and text_es under 280 chars.
Until this is built, the pipeline uses data/fixtures/drafter.json.
"""
from ..schemas import DrafterOut, Incident, JudgeOut


async def run(incident: Incident, judge: JudgeOut) -> DrafterOut:
    raise NotImplementedError("Drafter (Grok) not built yet")
