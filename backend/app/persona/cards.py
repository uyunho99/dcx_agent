"""Generate an atomic Persona card from the stage-seven file contract.

Injected runners perform one attempt. The default registry already retries
parse/schema failures twice, so it is invoked once per logical call. Validation
of coverage and references lives in the task schema, including registry calls.
No storage writes occur here; callers persist only a successful CardResult.
"""
import json
from dataclasses import dataclass
from math import isclose
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.llm import registry
from app.llm.base import Attachment, LLMTask
from app.persona.grade import grade_card
from app.persona.package import PersonaBlock, evidence_index
from app.persona.params import CARD_CHUNK

FIELDS = ('state', 'emotion', 'barrier')


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Cell(Output):
    text: str | None
    cite: list[str]


class ContextOut(Output):
    context_id: str
    state: Cell
    emotion: Cell
    barrier: Cell


class CardOut(Output):
    contexts: list[ContextOut] = Field(max_length=CARD_CHUNK)


class Intent(Output):
    text: str | None
    basis_context_ids: list[str]
    reserved_context_ids: list[str]


class Journey(Output):
    pre_purchase: float | None = Field(ge=0, le=1)
    purchase: float | None = Field(ge=0, le=1)
    post_purchase: float | None = Field(ge=0, le=1)

    @model_validator(mode='after')
    def total(self):
        values = (self.pre_purchase, self.purchase, self.post_purchase)
        if all(v is None for v in values):
            return self
        if any(v is None for v in values) or not isclose(sum(values), 1, abs_tol=1e-9):
            raise ValueError('Journey ratios must sum to one or all be null')
        return self


class Sensitivity(Output):
    price: Literal['상', '중', '하'] | None
    brand: Literal['상', '중', '하'] | None
    feature: Literal['상', '중', '하'] | None


class SummaryOut(Output):
    intent: Intent
    usage_context: Cell
    jtbd: Cell
    journey: Journey
    sensitivity: Sensitivity
    values: str | None
    decision_style: str | None


@dataclass(frozen=True)
class CardResult:
    status: Literal['done', 'failed']
    card: dict | None = None
    error: str | None = None


def _card_schema(context_ids, local_refs):
    class ChunkOut(CardOut):
        @model_validator(mode='after')
        def references(self):
            ids = [row.context_id for row in self.contexts]
            if len(ids) != len(context_ids) or set(ids) != set(context_ids):
                raise ValueError('Each requested Context must occur exactly once')
            for row in self.contexts:
                for field in FIELDS:
                    for cite in getattr(row, field).cite:
                        if cite not in local_refs or local_refs[cite].context_id != row.context_id:
                            raise ValueError('Citation must belong to this Context')
            return self
    return ChunkOut


def _summary_schema(context_ids, refs):
    class PersonaSummaryOut(SummaryOut):
        @model_validator(mode='after')
        def references(self):
            for cid in self.intent.basis_context_ids + self.intent.reserved_context_ids:
                if cid not in context_ids:
                    raise ValueError('Unknown intent Context')
            for cell in (self.usage_context, self.jtbd):
                if any(cite not in refs for cite in cell.cite):
                    raise ValueError('Unknown summary citation')
            return self
    return PersonaSummaryOut


def _call(sid, name, payload, schema, runner):
    prompt = (Path(__file__).with_name('prompts') / f'{name}.v1.md').read_text(encoding='utf-8')
    task = LLMTask(task=f'persona.{name}', sid=sid, instructions=prompt,
                   attachments=[Attachment(title='관찰 근거', body=json.dumps(payload, ensure_ascii=False))],
                   output_schema=schema)
    attempts = 1 if (runner is registry.run_task or
        getattr(getattr(runner, '__self__', runner), 'retries_schema', False)) else 2
    for _ in range(attempts):
        try:
            result = runner(task)
        except Exception:
            return None, 'backend'
        if not result.ok:
            kind = result.error.kind if result.error else 'backend'
            if kind not in ('parse', 'schema'):
                return None, kind
            continue
        try:
            data = result.data.model_dump() if isinstance(result.data, BaseModel) else result.data
            return schema.model_validate(data).model_dump(), None
        except (ValidationError, TypeError):
            pass
    return None, 'schema'


def _evidence_payload(ref):
    # Explicit projection prevents producer extras/project metadata leaking into prompts.
    return dict(context_id=ref.context_id, role=ref.role, doc_id=ref.doc_id,
                source=ref.source, quote={key: getattr(ref.quote, key) for key in
                    ('field', 'idx', 'start', 'end', 'text', 'verified')})


def generate_card(sid, block: PersonaBlock, *, run_task=None) -> CardResult:
    """At most four Contexts per card call, then one Persona-wide summary.

    Confirmed identity/action are copied from the package. For dims-derived
    situations, preserve the original text conservatively: semantic equivalence
    of arbitrary LLM rewrites cannot be guaranteed by schema validation.
    """
    runner = registry.run_task if run_task is None else run_task
    refs = evidence_index(block)
    persona = block.persona_evidence
    identity = {key: getattr(persona, key) for key in
                ('cluster_id', 'persona_id', 'persona_name', 'desire', 'goal')}
    rows = []
    for offset in range(0, len(block.context_evidence), CARD_CHUNK):
        chunk = block.context_evidence[offset:offset + CARD_CHUNK]
        ids = [context.context_id for context in chunk]
        global_keys = [key for key, ref in refs.items() if ref.context_id in ids]
        mapping = {f'E{i+1}': key for i, key in enumerate(global_keys)}
        local_refs = {local: refs[global_id] for local, global_id in mapping.items()}
        payload = dict(**identity, context_ids=ids, context_evidence=[dict(
            context_id=c.context_id, context_name=c.context_name,
            situation={field: getattr(c.situation, field) for field in FIELDS},
            situation_origin=c.situation_origin,
            counter_context='counter_context' in c.flags) for c in chunk],
            evidence={key: _evidence_payload(ref) for key, ref in local_refs.items()})
        if local_refs:
            data, error = _call(sid, 'card', payload, _card_schema(ids, local_refs), runner)
        else:
            data = {'contexts': [dict(context_id=cid, **{field: dict(text=None, cite=[])
                                                       for field in FIELDS}) for cid in ids]}
            error = None
        if error:
            return CardResult('failed', error=error)
        generated = {row['context_id']: row for row in data['contexts']}
        for context in chunk:
            row = generated[context.context_id]
            has_evidence = any(ref.context_id == context.context_id for ref in local_refs.values())
            for field in FIELDS:
                cell = row[field]
                if not has_evidence:
                    cell.update(text=None, cite=[])
                elif (cell['text'] is not None and context.situation_origin == 'dims'
                      and getattr(context.situation, field) is not None):
                    cell['text'] = getattr(context.situation, field)
                if cell['text'] is None:
                    cell['cite'] = []
                cell['cite'] = [mapping[cite] for cite in cell['cite']]
            row.update(keywords=list(context.keywords), action=context.action, context_name=context.context_name,
                       situation_origin=context.situation_origin, metrics=context.metrics.model_dump())
            rows.append(row)
    ids = [c.context_id for c in block.context_evidence]
    # Metrics and confirmed Action are code-owned, so exclude them from synthesis.
    payload = dict(**identity, context_ids=ids,
        contexts=[{key: row[key] for key in ('context_id', *FIELDS)} for row in rows],
        counter_context_ids=[c.context_id for c in block.context_evidence if 'counter_context' in c.flags],
        evidence={key: _evidence_payload(ref) for key, ref in refs.items()})
    if refs:
        summary, error = _call(sid, 'summary', payload, _summary_schema(ids, refs), runner)
        if error:
            return CardResult('failed', error=error)
    else:
        summary = dict(intent=dict(text=None, basis_context_ids=[], reserved_context_ids=[]),
            usage_context=dict(text=None, cite=[]), jtbd=dict(text=None, cite=[]),
            journey=dict(pre_purchase=None, purchase=None, post_purchase=None),
            sensitivity=dict(price=None, brand=None, feature=None), values=None, decision_style=None)
    card = dict(**identity, artifacts=[a.model_dump() for a in persona.artifacts], contexts=rows, **summary, intent_warning='의도 ≠ 행동',
                metrics=persona.metrics.model_dump(), quality=persona.quality.model_dump())
    card.update(grade_card(card, refs))
    return CardResult('done', card=card)
