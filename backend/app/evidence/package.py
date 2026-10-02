"""Evidence Package v1: the sole stage 7 -> 8 wire contract (design 2.4).

Serialize with by_alias=True for the external `schema` key. Nullable metrics
represent unavailable observations; they must not silently become zero.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PackageModel(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)


class Quote(PackageModel):
    field: Literal['title', 'body', 'comment']
    idx: int | None
    start: int | None
    end: int | None
    text: str
    verified: bool


class EvidenceItem(PackageModel):
    doc_id: str
    source: str
    quote: Quote | None
    tags: list[str]
    polarity: float | None
    novelty: str | None
    known_match: str | None
    tab: list[Literal['all', 'new']]
    role: Literal['support', 'counter', 'rare']
    dist_centroid: float | None = None
    combo_rarity: float | None = None


class Situation(PackageModel):
    state: str | None
    emotion: str | None
    barrier: str | None


class Artifact(PackageModel):
    name: str
    mention_count: int


class PersonaMetrics(PackageModel):
    importance: float | None
    satisfaction: float | None
    odi: float | None
    doc_count: int
    author_count: int
    provisional: list[str]


class ContextMetrics(PersonaMetrics):
    quality: dict[str, float | None]


class ContextEvidence(PackageModel):
    context_id: str
    context_name: str
    action: str
    situation: Situation
    situation_origin: Literal['dims', 'tag']
    dominant_constraint: str | None
    keywords: list[str]
    metrics: ContextMetrics
    evidence: list[EvidenceItem]
    counter_evidence: list[EvidenceItem]
    rare_evidence: list[EvidenceItem]
    flags: list[str]


class PersonaEvidence(PackageModel):
    cluster_id: str
    persona_id: str
    persona_name: str
    desire: str
    goal: list[str]
    desire_support: list[EvidenceItem]
    artifacts: list[Artifact]
    metrics: PersonaMetrics
    quality: dict


class PersonaBlock(PackageModel):
    persona_evidence: PersonaEvidence
    context_evidence: list[ContextEvidence]


class EvidencePackage(PackageModel):
    schema_: Literal['evidence-package/1'] = Field(alias='schema')
    version: str
    params: dict
    personas: list[PersonaBlock]
