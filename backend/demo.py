"""Grok-only demonstration using a clearly labeled fictional scenario."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from backend.agents import broadcaster, drafter, scout, society
from backend.agents.runner import AgentRunner
from backend.config import ROOT
from backend.schemas import (BroadcastInput, BroadcasterReplies, DraftInput, DrafterOut,
                             ScoutInput, ScoutSelection, SocietyInput, SocietyOut)


class DemoFixtureProvider:
    """Explicit offline mode. These outputs were hand authored, not API generated."""

    def __init__(self):
        raw = (ROOT / "data/grok_demo_outputs.json").read_bytes()
        self.outputs = json.loads(raw)
        self.identity = "synthetic-fixtures-" + hashlib.sha256(raw).hexdigest()

    def generate(self, system, user, schema, *, model):
        inputs = json.loads(user)
        if schema is ScoutSelection:
            payload = self.outputs["scout"]
        elif schema is DrafterOut:
            payload = self.outputs["drafter"]
        elif schema is SocietyOut:
            payload = self.outputs["society"][inputs["framing"]["key"]]
        elif schema is BroadcasterReplies:
            payload = self.outputs["broadcaster"]
        else:
            raise ValueError(f"No synthetic fixture for {schema.__name__}")
        return schema.model_validate(payload)


def run_demo(runner: AgentRunner, *, approved: bool = False) -> dict:
    scenario = json.loads((ROOT / "data/scenario_sd1024.json").read_text(encoding='utf-8'))
    personas = json.loads((ROOT / "data/personas.json").read_text(encoding='utf-8'))
    incident = scout.run(ScoutInput(incident_id=scenario["incident_id"], posts=scenario["posts"]), runner)
    # Verification is supplied scenario data here. No Gemini agent is implemented.
    drafts = drafter.run(DraftInput(**{**scenario["verification"], "claim": incident.payload.claim}), runner)
    def simulate(framing):
        return society.run(SocietyInput(claim=incident.payload.claim, framing=framing,
                                       groups=personas["groups"]), runner)
    with ThreadPoolExecutor(max_workers=3) as pool:
        reactions = list(pool.map(simulate, drafts.payload.framings))
    recommended = society.recommend([out.payload for out in reactions])
    broadcast = None
    if approved:
        chosen = next(f for f in drafts.payload.framings if f.key == recommended)
        broadcast = broadcaster.run(BroadcastInput(approved=True, framing_key=chosen.key,
            post_en=chosen.text_en, post_es=chosen.text_es,
            verified_facts=scenario["verification"]["verified_facts"],
            official_source=scenario["verification"]["official_source"], questions=scenario["replies"]), runner)
    return {"source": "synthetic_fixtures" if isinstance(runner.provider, DemoFixtureProvider) else "xai_api_or_cache",
            "synthetic_scenario": scenario["synthetic"], "scenario_label": scenario["label"],
            "simulation_label": personas["label"],
            "scout": incident.model_dump(mode="json"), "drafter": drafts.model_dump(mode="json"),
            "society": {out.payload.framing_key: out.model_dump(mode="json") for out in reactions},
            "simulation": {out.payload.framing_key: society.simulation_parameters(out.payload) for out in reactions},
            "recommended_framing": recommended,
            "broadcast_status": "ready" if approved else "waiting_for_approval",
            "broadcast": broadcast.model_dump(mode="json") if broadcast else None}
