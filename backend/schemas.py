"""Validated Grok contracts. UI-facing field names follow FIREBREAK_PLAN.md."""

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1)]
PostText = Annotated[str, Field(min_length=1, max_length=280)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
FramingKey = Literal["A", "B", "C"]
GROUPS = ("Poway residents", "Escondido parents (ES)", "Local influencers",
          "Retirees on Facebook", "Reporters", "Skeptics")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SocialPost(Contract):
    id: Text
    timestamp: datetime
    text: Text
    language: Text
    who: Text

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Post timestamps must include a timezone")
        return value


class ScoutInput(Contract):
    incident_id: Text
    posts: list[SocialPost] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({p.id for p in self.posts}) != len(self.posts):
            raise ValueError("Post IDs must be unique")
        return self


class ScoutSelection(Contract):
    claim: Text
    selected_post_ids: list[Text] = Field(min_length=1)
    summary: Text


class Incident(Contract):
    incident_id: Text
    claim: Text
    post_count: int = Field(ge=1)
    velocity_per_min: float = Field(ge=0, allow_inf_nan=False)
    languages: list[Text] = Field(min_length=1)
    summary: Text


class DraftInput(Contract):
    claim: Text
    verdict: Literal["False", "Misleading", "Unverified", "True"]
    verified_facts: list[Text] = Field(min_length=1)
    safety_action: Text
    official_source: Text


class Framing(Contract):
    key: FramingKey
    name: Literal["Fact check", "Action first", "Neighbor voice"]
    text_en: PostText
    text_es: PostText

    @model_validator(mode="after")
    def name_matches_key(self):
        if self.name != {"A": "Fact check", "B": "Action first", "C": "Neighbor voice"}[self.key]:
            raise ValueError("Framing name must match key")
        return self


class DrafterOut(Contract):
    framings: list[Framing] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def all_framings(self):
        if {f.key for f in self.framings} != {"A", "B", "C"}:
            raise ValueError("Return A, B, and C exactly once")
        self.framings.sort(key=lambda f: f.key)
        return self


class Persona(Contract):
    name: Text
    age: int = Field(ge=18, le=110)
    platform: Text
    trust_in_government: Literal["low", "med", "high"]
    language: Literal["en", "es"]


class PersonaGroup(Contract):
    group_id: int = Field(ge=0, le=5)
    name: Text
    personas: list[Persona] = Field(min_length=3, max_length=4)


class SocietyInput(Contract):
    claim: Text
    framing: Framing
    groups: list[PersonaGroup] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def group_contract(self):
        if sorted(g.group_id for g in self.groups) != list(range(6)):
            raise ValueError("Each group 0-5 must occur once")
        self.groups.sort(key=lambda g: g.group_id)
        if any(g.name != GROUPS[g.group_id] for g in self.groups):
            raise ValueError("Group names must match the existing UI")
        if sum(len(g.personas) for g in self.groups) != 20:
            raise ValueError("The simulation requires 20 personas")
        return self


class GroupScore(Contract):
    group_id: int = Field(ge=0, le=5)
    belief_drop: Probability
    reaction: Annotated[str, Field(min_length=1, max_length=280)]


class SocietyOut(Contract):
    framing_key: FramingKey
    scores: list[GroupScore] = Field(min_length=6, max_length=6)
    es_group_en_only_drop: Probability

    @model_validator(mode="after")
    def ordered_unique_groups(self):
        if sorted(s.group_id for s in self.scores) != list(range(6)):
            raise ValueError("Each group 0-5 must occur once")
        self.scores.sort(key=lambda s: s.group_id)
        return self


class ReplyQuestion(Contract):
    id: Text
    text: Text
    language: Literal["en", "es"]


class BroadcastInput(Contract):
    approved: bool
    framing_key: FramingKey
    # Approved copy must retain its exact whitespace.
    post_en: Annotated[str, Field(min_length=1, max_length=280, strip_whitespace=False)]
    post_es: Annotated[str, Field(min_length=1, max_length=280, strip_whitespace=False)] | None = None
    verified_facts: list[Text]
    official_source: Text
    questions: list[ReplyQuestion] = Field(max_length=20)

    @field_validator("post_en", "post_es", mode="before")
    @classmethod
    def nonblank(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("Approved copy cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_questions(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Reply question IDs must be unique")
        return self


class ReplyAnswer(Contract):
    question_id: Text
    text: PostText


class BroadcasterReplies(Contract):
    replies: list[ReplyAnswer]


class FeedPost(Contract):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    who: Literal["@CountyComms_demo"] = "@CountyComms_demo"
    language: Literal["en", "es"]
    text: PostText
    in_reply_to: str | None = None


class BroadcasterOut(Contract):
    posts: list[FeedPost]
    replies: list[FeedPost]


T = TypeVar("T", bound=BaseModel)


class AgentResult(BaseModel, Generic[T]):
    payload: T
    status: Literal["done", "cached"]
