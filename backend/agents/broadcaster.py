"""Produce in-app feed items. No network publishing capability exists here."""

from backend.agents.runner import AgentRunner
from backend.cache import CacheMiss
from backend.schemas import (AgentResult, BroadcastInput, BroadcasterOut,
                             BroadcasterReplies, FeedPost)

PROMPT = """
You are Broadcaster for @CountyComms_demo, an in-app emergency response demo.
Answer every supplied question once, identifying it by question_id. Use each
question's language. Each reply must be at most 280 characters, friendly and
short. Acknowledge frustration without inventing promises or incident history.
Use only supplied verified_facts and approved copy. Refer people to the supplied
official_source (ReadySanDiego in the demo). If asked whether a place is safe or
under an order and the supplied facts do not establish it, say you cannot confirm
and direct them to official updates. Never invent new orders or claim all-clear.
Do not rewrite the approved posts. Return only replies.
"""


def run(inputs: BroadcastInput, runner: AgentRunner) -> AgentResult[BroadcasterOut]:
    if not inputs.approved:
        raise PermissionError("The comms officer must approve the correction first")

    posts = [FeedPost(language="en", text=inputs.post_en)]
    if inputs.post_es is not None:
        posts.append(FeedPost(language="es", text=inputs.post_es))

    def produce(model):
        output = (runner.complete(PROMPT, inputs, BroadcasterReplies, model)
                  if inputs.questions else BroadcasterReplies(replies=[]))
        answers = {reply.question_id: reply for reply in output.replies}
        if len(answers) != len(output.replies) or set(answers) != {q.id for q in inputs.questions}:
            raise ValueError("Broadcaster must answer each question ID exactly once")
        return output

    try:
        result = runner.run("broadcaster", inputs, PROMPT, BroadcasterReplies, produce)
    except CacheMiss:
        # Preserve replay's strict cache-only contract.
        raise
    except Exception:
        # Replies are optional. Failure must not discard already-approved copy.
        return AgentResult(payload=BroadcasterOut(posts=posts, replies=[], reply_status="unavailable"), status="done")
    answers = {reply.question_id: reply for reply in result.payload.replies}
    replies = [FeedPost(language=q.language, text=answers[q.id].text, in_reply_to=q.id)
               for q in inputs.questions]
    return AgentResult(payload=BroadcasterOut(posts=posts, replies=replies,
        reply_status="done" if inputs.questions else "not_requested"), status=result.status)
