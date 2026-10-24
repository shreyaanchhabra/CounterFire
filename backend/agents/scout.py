"""Cluster posts without judging their truth. Calculate metrics locally."""

from backend.agents.runner import AgentRunner
from backend.schemas import AgentResult, Incident, ScoutInput, ScoutSelection

PROMPT = """
You are Scout for a county emergency communications team. Find the dominant
cluster of posts making the same factual claim. Extract its single core claim,
the exact selected_post_ids, and a short summary. Do not judge whether it is true.
Do not include unrelated posts. Do not return counts or velocity; Python computes
those. Only select IDs provided in the input. Return each selected ID once.
"""


def run(inputs: ScoutInput, runner: AgentRunner) -> AgentResult[Incident]:
    def produce(model):
        selection = runner.complete(PROMPT, inputs, ScoutSelection, model)
        by_id = {post.id: post for post in inputs.posts}
        ids = selection.selected_post_ids
        if len(set(ids)) != len(ids) or any(i not in by_id for i in ids):
            raise ValueError("Scout selected duplicate or unknown post IDs")
        selected = [by_id[i] for i in ids]
        times = [p.timestamp for p in selected]
        minutes = max((max(times) - min(times)).total_seconds() / 60, 1)
        return Incident(incident_id=inputs.incident_id, claim=selection.claim,
                        post_count=len(selected), velocity_per_min=round(len(selected) / minutes, 4),
                        languages=sorted({p.language for p in selected}), summary=selection.summary)
    return runner.run("scout", inputs, PROMPT, Incident, produce)
