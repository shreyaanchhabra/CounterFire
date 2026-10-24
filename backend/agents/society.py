"""Illustrative persona simulation, not a measurement of real public behavior."""

from backend.agents.runner import AgentRunner
from backend.schemas import AgentResult, SocietyInput, SocietyOut

PROMPT = """
You are Society Sim. This is a fictional audience experiment, not a forecast.
The 20 supplied personas partly believed claim. Simulate their reactions to the
supplied framing using their platform, trust, and language. Return framing_key
equal to framing.key, and exactly six scores, one for each group_id 0 through 5.
belief_drop is 0 (still believes) to 1 (convinced by the correction). Supply one
short representative in-character reaction per group. Give Spanish speakers the
Spanish correction for the main scores. Separately simulate group 1 receiving
only text_en and return that belief drop in es_group_en_only_drop. Do not assume
a particular framing wins or Spanish always helps. Do not add demographic facts.
"""


def run(inputs: SocietyInput, runner: AgentRunner) -> AgentResult[SocietyOut]:
    def produce(model):
        output = runner.complete(PROMPT, inputs, SocietyOut, model)
        if output.framing_key != inputs.framing.key:
            raise ValueError("Society result does not match the requested framing")
        return output
    return runner.run("society", inputs, PROMPT, SocietyOut, produce, fast=True)


def simulation_parameters(output: SocietyOut) -> dict:
    """Values for the existing UI; no changes to its simulation math."""
    clamp = lambda value, low, high: max(low, min(high, value))
    spanish = output.scores[1].belief_drop
    # A zero denominator implies no modeled bilingual benefit. Use neutral 1.0.
    multiplier = output.es_group_en_only_drop / spanish if spanish else 1.0
    return {"p": [clamp(.3 * score.belief_drop, .03, .32) for score in output.scores],
            "es_off_mult": clamp(multiplier, .1, 1.0)}


def recommend(outputs: list[SocietyOut]) -> str:
    if sorted(out.framing_key for out in outputs) != ["A", "B", "C"]:
        raise ValueError("Recommendation requires A, B, and C once each")
    return max(sorted(outputs, key=lambda out: out.framing_key),
               key=lambda out: sum(score.belief_drop for score in out.scores) / 6).framing_key
