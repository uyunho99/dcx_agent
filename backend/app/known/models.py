"""Known Insight wire format, including legacy string-list compatibility."""
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.context.store import now


class KnownInsight(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: 'ki_' + uuid4().hex)
    type: Literal['statement', 'doc']
    text: str = ''
    doc_id: str | None = None
    origin: Literal['stage0', 'drawer', 'rag', 'prev_session'] = Field(default='drawer', alias='from')
    createdAt: str = Field(default_factory=now)
    vectorRow: int | None = None


def read_known(session) -> list[KnownInsight]:
    return [KnownInsight(type='statement', text=item, id=f'ki_legacy_{i}', origin='stage0', createdAt='')
            if isinstance(item, str) else KnownInsight.model_validate(item)
            for i, item in enumerate(session.get('knownInsights', []))]
