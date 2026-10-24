"""Draft three bilingual framings using only supplied verification and actions."""

from backend.agents.runner import AgentRunner
from backend.schemas import AgentResult, DraftInput, DrafterOut

PROMPT = """
You are the Drafter for a county emergency response desk. Write exactly three
framings with these keys and names: A = Fact check, B = Action first, C = Neighbor
voice. Return them in framings. Each needs text_en and natural text_es, each at
most 280 characters. Write at a sixth grade reading level. Spanish should read
naturally to Spanish-speaking parents in North County San Diego.
Use only verified_facts. Include the supplied safety_action and direct people
to official_source. Do not infer that a false photo makes an area safe. For A,
lead with FALSE only when verdict is False; for other verdicts use the actual
verdict and its uncertainty. If verdict is True, confirm rather than debunk it.
B leads with the supplied action. C sounds like a helpful neighbor, but never
impersonates an eyewitness or claims to be on scene. Retain uncertainty in both
languages. These are drafts for human approval, not authorized public posts.
"""


def run(inputs: DraftInput, runner: AgentRunner) -> AgentResult[DrafterOut]:
    return runner.run("drafter", inputs, PROMPT, DrafterOut,
                      lambda model: runner.complete(PROMPT, inputs, DrafterOut, model))
