"""Strict native-community action contracts, independent of transport."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt

ACTIONS = ('share', 'question', 'verify', 'reply', 'retract', 'wait')


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    persona_id: str = Field(min_length=1)
    action: Literal['share', 'question', 'verify', 'reply', 'retract', 'wait']
    belief: float = Field(ge=0, le=1, allow_inf_nan=False)
    message: str | None = Field(default=None, max_length=280)
    parent_id: str | None = None


class CommunityResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    group_id: StrictInt = Field(ge=0, le=5)
    decisions: list[Decision] = Field(min_length=1, max_length=4)
