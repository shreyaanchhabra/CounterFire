"""Scout (Grok). STUB: owned by the Grok side.

Contract: run(posts) -> Incident. Velocity is computed in Python by the pipeline, not by the model.
Until this is built, the pipeline uses data/fixtures/scout.json.
"""
from ..schemas import Incident


async def run(posts: list[dict], incident_id: str) -> Incident:
    raise NotImplementedError("Scout (Grok) not built yet")
