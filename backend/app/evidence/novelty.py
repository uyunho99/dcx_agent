"""One schema-validated novelty cross-check for the final new tab per Context."""
import json
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from app.evidence import params
from app.llm import registry
from app.llm.base import Attachment, LLMTask


class NoveltyItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    doc_id: str
    novelty: Literal['none', 'low', 'medium', 'high', 'very_high']
    reason: str = Field(min_length=1, pattern=r'^[^\r\n]+$')


class NoveltyOut(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[NoveltyItem]


def core_representatives(core_rows, vectors, centroid) -> list[dict]:
    """Choose up to five Context core documents nearest its cosine centroid.

    Caller supplies this Context's document rows enriched with original text.
    Ties use doc_id; absent/invalid vectors cannot be representatives.
    """
    center = np.asarray(centroid, dtype=float)
    norm = np.linalg.norm(center)
    if norm == 0 or not np.isfinite(center).all():
        return []
    center = center / norm
    scores = {}
    for row in core_rows:
        if row.get('band', row.get('evidence_level')) != 'core':
            continue
        doc_id = row['doc_id']
        if doc_id not in vectors:
            continue
        vector = np.asarray(vectors[doc_id], dtype=float)
        length = np.linalg.norm(vector)
        if length > 0 and np.isfinite(vector).all():
            scores[doc_id] = (float(vector @ center / length), row)
    ordered = sorted(scores, key=lambda i: (-scores[i][0], i))
    return [dict(scores[i][1]) for i in ordered[:params.NOVELTY_CORE_REPS]]


def judge_novelty(sid, context, new_rows, core_reps, known_items, *,
                  run_task=registry.run_task) -> dict[str, tuple[str, str]]:
    """Call once, without a local retry; missing/failed judgments remain absent.

    new_rows and core_reps must include prepared text/quotes, not only selection
    IDs. The caller invokes this after final selection, never during refresh.
    The registry owns provider/schema retries. Unknown response IDs are ignored.
    """
    if not new_rows:
        return {}
    if len(new_rows) > params.SELECT_N or len(core_reps) > params.NOVELTY_CORE_REPS:
        raise ValueError('novelty requires final new-tab <= 10 and core representatives <= 5')
    known = [i.model_dump() if isinstance(i, BaseModel) else dict(i) for i in known_items]
    payload = dict(context=context, new_rows=new_rows, core_reps=core_reps, known_items=known)
    task = LLMTask(task='evidence.novelty', sid=sid,
                   instructions=Path(__file__).with_name('prompts').joinpath('novelty.v1.md').read_text(encoding='utf-8'),
                   attachments=[Attachment(title='Context novelty cross-check', body=json.dumps(payload, ensure_ascii=False))],
                   output_schema=NoveltyOut)
    result = run_task(task)
    if not result.ok or not isinstance(result.data, NoveltyOut):
        return {}
    wanted = {r['doc_id'] for r in new_rows}
    judgments = {}
    for item in result.data.items:
        if item.doc_id in wanted:
            judgments.setdefault(item.doc_id, (item.novelty, item.reason))
    return judgments


def apply_novelty(all_rows, new_rows, judgments):
    """Return copies with novelty only for current new-tab membership."""
    new_ids = {r['doc_id'] for r in new_rows}

    def decorate(row):
        level, reason = judgments.get(row['doc_id'], (None, None)) if row['doc_id'] in new_ids else (None, None)
        return dict(row, novelty=level, novelty_reason=reason, show_novelty=level in params.NOVELTY_SHOW)

    return [decorate(r) for r in all_rows], [decorate(r) for r in new_rows]
