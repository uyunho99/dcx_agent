"""Shared label payloads for automatic and human judgments."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.label.questions import QVER
from app.label.rule import RULE_VERSION, SEM

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
ReasonCode = Literal['ad', 'no_needs', 'pure_criticism', 'other']
Signal = Literal['pain', 'unmet', 'workaround', 'delight', 'none']


class Tags(BaseModel):
    anchor: bool
    sem: dict[str, Literal[0, 1]]
    situation: bool
    reason_code: ReasonCode | None = None
    signal: Signal | None = None

    @field_validator('sem')
    @classmethod
    def complete_sem(cls, value):
        if set(value) != set(SEM):
            raise ValueError('sem must contain exactly the six semantic tags')
        return value


class JevVote(BaseModel):
    probs: dict[str, Probability]
    reason_probs: dict[str, Probability]
    model: str
    truncated: bool = False


class Label(Tags):
    doc_id: str
    evidence_level: Literal['core', 'supporting', 'non']
    confidence: Probability
    source: Literal['agreed', 'human', 'model']
    votes: dict = Field(default_factory=dict)
    route: str = Field(pattern=r'^(accepted|audited|escalated:.+)$')
    rule_version: str = RULE_VERSION
    questions_version: str = QVER
