"""Persisted keyword fields used across generation and review."""

from typing import Literal

from pydantic import BaseModel, Field


class Keyword(BaseModel):
    id: str
    kw: str
    axis: Literal["physical", "psychological", "behavioral"]
    sub: str
    round: int = Field(ge=1, le=4)
    origin: Literal["llm", "manual", "suggested"]
    status: Literal["pending", "approved", "rejected"] = "pending"
    reject: dict | None = None
    volume: dict | None = None
    badges: list[str] = Field(default_factory=list)
