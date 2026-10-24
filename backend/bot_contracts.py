"""Typed native Bot responses. Routine inputs determine the response schema."""

from pydantic import BaseModel, ConfigDict, Field, create_model

from backend.schemas import BroadcasterReplies, DrafterOut, ScoutSelection


class BotEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=120)
    episode_id: str = Field(min_length=1, max_length=120)
    round_id: int = Field(ge=0)
    group_id: int = Field(ge=0, le=5)
    observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def result_schema(task_type: str):
    if task_type == "action":
        from backend.grokbots_return import ActionPacket
        return ActionPacket
    if task_type == "community":
        from backend.society_models import CommunityResult
        payload = CommunityResult
    else:
        payload = {"scout": ScoutSelection, "draft": DrafterOut, "broadcast": BroadcasterReplies}.get(task_type)
    if payload is None:
        raise ValueError("Unknown native Bot task type")
    return create_model(task_type.title() + "Packet", __base__=BotEnvelope, payload=(payload, ...))
