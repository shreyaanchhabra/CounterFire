"""Data contracts. The UI reads exactly these shapes. Keep field names (plan Section 5)."""
from typing import Literal

from pydantic import BaseModel


class Incident(BaseModel):
    incident_id: str
    claim: str
    post_count: int
    velocity_per_min: float
    languages: list[str]
    summary: str


class Finding(BaseModel):
    id: int
    label: str
    box_2d: list[int] | None  # [ymin, xmin, ymax, xmax] normalized 0-1000
    category: Literal["location", "shadow_light", "weather", "provenance", "account", "other"]


class ProsecutorOut(BaseModel):
    findings: list[Finding]
    bullets: list[str]


class DefenderOut(BaseModel):
    bullets: list[str]


class MissingEvidence(BaseModel):
    item: str
    ask_target: str


class JudgeOut(BaseModel):
    verdict: Literal["False", "Misleading", "Unverified", "True"]
    confidence: int
    reasoning: str
    missing: list[MissingEvidence]


class Framing(BaseModel):
    key: Literal["A", "B", "C"]
    name: str
    text_en: str
    text_es: str


class DrafterOut(BaseModel):
    framings: list[Framing]


class GroupScore(BaseModel):
    group_id: int
    belief_drop: float
    reaction: str


class SocietyOut(BaseModel):
    framing_key: str
    scores: list[GroupScore]
    es_group_en_only_drop: float


class SocietyAll(BaseModel):
    framings: list[SocietyOut]


class VoiceIntent(BaseModel):
    action: Literal["approve", "kill", "edit", "none"]
    languages: list[str]
    facts: list[str]
    framing_hint: Literal["A", "B", "C"] | None


class EditorOut(BaseModel):
    raw: str
    clean: str
    filler_spans: list[list[int]]
    command_spans: list[list[int]]
    intent: VoiceIntent
    post_en: str
    post_es: str | None


class Reply(BaseModel):
    who: str
    question: str
    answer: str


class BroadcastOut(BaseModel):
    replies: list[Reply]


# ---- Gemini-internal shapes (not sent to the UI as-is) ----

class VisionOut(BaseModel):
    image_description: str
    findings: list[Finding]
    bullets: list[str]


class ProvenanceOut(BaseModel):
    earlier_copy_found: bool
    earliest_date: str | None
    source: str | None


class AskOut(BaseModel):
    text: str


class VoiceParse(BaseModel):
    clean: str
    filler_words: list[str]
    command_phrases: list[str]
    intent: VoiceIntent
    post_en: str
    post_es: str | None


class Transcript(BaseModel):
    raw: str


class AnalyzeOut(BaseModel):
    prosecutor: ProsecutorOut
    defender: DefenderOut
    judge: JudgeOut
    image_hash: str
