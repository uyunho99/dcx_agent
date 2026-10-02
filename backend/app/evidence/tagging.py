"""Lazy evidence tagging; workers call the LLM, callers alone publish caches."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import settings
from app.evidence import params
from app.evidence.cache import known_key
from app.evidence.quotes import locate
from app.known.store import list_known
from app.llm import registry
from app.llm.base import Attachment, LLMTask
from app.segment import dims


class Schema(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Situation(Schema):
    state: str | None
    emotion: str | None
    barrier: str | None


class ContextDims(Schema):
    environment: str | None
    internal_state: str | None
    task_goal: str | None
    activity_response: str | None
    resource_constraint: str | None


class PainPoint(Schema):
    text: str
    quote: str


class QuoteInput(Schema):
    field: Literal['title', 'body', 'comment']
    idx: int | None = None
    text: str


class TagItem(Schema):
    doc_id: str
    relevant: bool
    reason_code: Literal['ad', 'no_needs', 'pure_criticism', 'other'] | None = None
    polarity: float = Field(ge=-1, le=1)
    pain_point: PainPoint | None
    unmet_need: str | None
    situation: Situation | None = None
    context_dims: ContextDims | None = None
    artifacts: list[str]
    known_match: str = Field(pattern=r'^(#[1-9][0-9]*|none)$')
    quotes: list[QuoteInput]

    @model_validator(mode='after')
    def reason_required(self):
        if not self.relevant and self.reason_code is None:
            raise ValueError('Irrelevant documents need a reason_code')
        return self


class TagOut(Schema):
    items: list[TagItem]


@dataclass
class TagResult:
    tags: dict[str, dict]
    calls: int
    cache_hits: int
    untagged: int
    untagged_ids: list[str]
    reason_counts: dict[str, int]
    lazy_dims: int


def _model():
    backend = settings.llm_backend
    for pattern, override in settings.llm_backend_overrides.items():
        if fnmatchcase('evidence.tag', pattern):
            backend = override
            break
    return {'openai_api': settings.openai_model, 'claude_api': settings.claude_model,
            'codex_exec': settings.codex_profile}.get(backend, backend)


def _workers(concurrency):
    value = concurrency if concurrency is not None else getattr(settings, 'evidence_llm_concurrency', params.CONCURRENCY)
    if value < 1:
        raise ValueError('concurrency must be positive')
    return value


def _known_rows(items):
    return [i.model_dump() if isinstance(i, BaseModel) else dict(i) for i in items]


def _instructions(known):
    prompt = Path(__file__).with_name('prompts').joinpath('tag.v1.md').read_text(encoding='utf-8')
    lines = []
    for index, item in enumerate(known, 1):
        text = item.get('text') or item.get('summary') or ''
        if item['type'] == 'doc':
            text = text[:params.KI_SUMMARY_CHARS]
        lines.append(f'#{index} {text}')
    return prompt + '\nKnown Insight:\n' + '\n'.join(lines)


def _input(doc, context_dims):
    return dict(title=doc.get('title') or '', body=(doc.get('body') or '')[:params.TAG_BODY_CHARS],
                comments=[dict(idx=i, text=((c.get('text') or '') if isinstance(c, dict) else str(c))[:params.TAG_COMMENT_CHARS])
                          for i, c in enumerate((doc.get('comments') or [])[:params.TAG_COMMENTS])],
                channel=doc.get('channel') or doc.get('source') or '',
                evidence_level=doc.get('evidence_level', doc.get('evidence_level_pred')),
                context_dims=context_dims)


def _request(sid, batch, inputs, instructions, run_task):
    task = LLMTask(task='evidence.tag', sid=sid, instructions=instructions + '\n출력 JSON 스키마:\n' + json.dumps(TagOut.model_json_schema(), ensure_ascii=False),
                   attachments=[Attachment(title=i, body=json.dumps(dict(inputs[i], doc_id=i), ensure_ascii=False)) for i in batch],
                   output_schema=TagOut)
    result = run_task(task)
    if not result.ok or not isinstance(result.data, TagOut):
        return {}
    rows = {}
    for item in result.data.items:
        if item.doc_id in batch and item.doc_id not in rows:
            rows[item.doc_id] = item.model_dump()
    return rows


def _collect(sid, ids, inputs, known, run_task, concurrency):
    """Deterministic waves; missing IDs alone get one next-wave retry."""
    pending, attempts, rows, calls = list(ids), Counter(), {}, 0
    instructions = _instructions(known)
    with ThreadPoolExecutor(max_workers=_workers(concurrency)) as pool:
        while pending:
            batches = [pending[i:i + params.TAG_BATCH] for i in range(0, len(pending), params.TAG_BATCH)]
            futures = [pool.submit(_request, sid, batch, inputs, instructions, run_task) for batch in batches]
            retry = []
            for batch, future in zip(batches, futures):
                result = future.result()
                calls += 1
                rows.update(result)
                for doc_id in batch:
                    attempts[doc_id] += 1
                    if doc_id not in result and attempts[doc_id] < 2:
                        retry.append(doc_id)
            pending = retry
    return rows, calls


def _situation(values):
    return dict(state=' '.join(v for v in (values.get('environment'), values.get('task_goal')) if v) or None,
                emotion=values.get('internal_state'), barrier=values.get('resource_constraint'))


def _pairs(rows, known):
    result = {}
    labels = {f'#{i}': known_key(item) for i, item in enumerate(known, 1)}
    for doc_id, row in rows.items():
        match = row['known_match']
        if match == 'none':
            result.update({(doc_id, known_key(item)): False for item in known})
        elif match in labels:
            # A single match cannot establish negatives for other Known items.
            result[doc_id, labels[match]] = True
    return result


def tag_documents(sid, doc_ids, *, docs, dims_by_id, known_items, cache,
                  run_task=registry.run_task, concurrency=None) -> TagResult:
    ids = list(dict.fromkeys(doc_ids))
    known = [i for i in _known_rows(known_items) if i['type'] == 'statement']
    cached = cache.get_tags(ids, model=_model())
    pending = [i for i in ids if i not in cached]
    inputs = {i: _input(docs[i], dims_by_id.get(i) or docs[i].get('context_dims')) for i in pending}
    rows, calls = _collect(sid, pending, inputs, known, run_task, concurrency)
    pairs = _pairs(rows, known)
    lazy = {}
    model = _model()
    for doc_id, row in rows.items():
        values = inputs[doc_id]['context_dims']
        if not values and inputs[doc_id]['evidence_level'] == 'core' and row['context_dims'] is not None:
            values, too_long = dims._clean(row['context_dims'])
            lazy[doc_id] = (values, too_long)
        row['context_dims'] = values
        if values is not None:
            row['situation'] = _situation(values)
        row['situation_origin'] = 'dims' if values is not None else 'tag'
        row['quotes'] = [locate(q, docs[doc_id]) for q in row['quotes']]
        row['_input'] = inputs[doc_id]
        row['model'] = model
        row['known_match'] = 'none'  # Always project current stable IDs from pair cache below.
    if lazy:
        pver = hashlib.sha256(dims.PROMPT_PATH.read_bytes()).hexdigest()
        dims.write_cache(cache.path.parent / f'dims-{pver}.sqlite', lazy, origin='lazy', model=model)
    if rows:
        cache.put_tags(rows, model)
    if pairs:
        cache.put_known(pairs, model)
    tags = {i: (rows[i] if i in rows else cached[i]) for i in ids if i in rows or i in cached}
    judgments = cache.get_known(tags, [known_key(item) for item in known], model=_model())
    for doc_id, row in tags.items():
        row['known_match'] = next((item['id'] for item in known if judgments.get((doc_id, known_key(item)))), 'none')
    missing = [i for i in ids if i not in tags]
    return TagResult(tags, calls, len(cached), len(missing), missing,
                     dict(Counter(r['reason_code'] for r in tags.values() if not r['relevant'])), len(lazy))


def judge_known(sid, doc_ids, ki_ids, *, cache, run_task=registry.run_task, concurrency=None, known_items=None):
    """Judge only absent pairs using cached prepared excerpts and current KI text.

    Deleted items are ignored without deleting shared cache rows. Content
    fingerprints distinguish edits. Missing responses remain unjudged.
    """
    items = _known_rows(known_items) if known_items is not None else [item.model_dump() for item in list_known(sid)]
    known = {item['id']: item for item in items if item['type'] == 'statement'}
    wanted = [i for i in dict.fromkeys(ki_ids) if i in known]
    tags = cache.get_tags(doc_ids, model=_model())
    result = cache.get_known(tags, [known_key(known[i]) for i in wanted], model=_model())
    for ki_id in wanted:
        pending = [i for i in tags if (i, known_key(known[ki_id])) not in result]
        inputs = {i: tags[i].get('_input', tags[i]) for i in pending}
        rows, _ = _collect(sid, pending, inputs, [known[ki_id]], run_task, concurrency)
        pairs = _pairs(rows, [known[ki_id]])
        if pairs:
            cache.put_known(pairs, _model())
            result.update(pairs)
    return result
