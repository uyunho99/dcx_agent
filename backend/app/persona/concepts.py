"""8-F concepts with package-owned evidence and append-only revisions.

Each journey row pairs AS-IS action/feeling/context with TO-BE service/actions.
Evidence numbers retain Persona-wide numbering; multi-Persona inputs qualify
numbers as ``persona_id:E1``. Basis counts distinct package evidence documents
and their distinct non-null authors from the version-local segment store.
Store mutations acquire their own session lock; callers must not hold it.
"""
from contextlib import closing
import json
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.context import store as sessions
from app.llm import registry
from app.llm.base import Attachment, LLMTask
from app.persona import prescribe as prescriptions
from app.persona.package import evidence_index, load_package
from app.persona.params import CX_4D
from app.persona.store import PersonaStore
from app.segment.store import SegmentStore

Text = Annotated[str, Field(min_length=1)]


class _Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class JourneyRow(_Output):
    context_id: Text
    action: Text
    feeling: Text
    service: Text
    service_action: Text
    cx_4d: Literal['정신적', '물리적', '문화적', '시스템']


class ConceptOut(_Output):
    persona_profile: Text
    pain_points: Annotated[list[Text], Field(min_length=3, max_length=3)]
    journey: Annotated[list[JourneyRow], Field(min_length=1)]
    # Compatibility with the shared fake/legacy response. Never trusted or saved:
    # the separate persona.constraint_check call owns the final verdicts.
    constraint_check: list[prescriptions.ConstraintVerdict] = Field(default_factory=list)


class ConceptError(RuntimeError):
    """Concept generation or evidence validation failed; no revision was saved."""


def _generate(sid, payload, run_task):
    prompt = Path(__file__).with_name('prompts').joinpath('concept.v1.md').read_text(encoding='utf-8')
    task = LLMTask(task='insight.concept', sid=sid, instructions=prompt,
                   attachments=[Attachment(title='컨셉 입력', body=json.dumps(payload, ensure_ascii=False))],
                   output_schema=ConceptOut)
    try:
        result = run_task(task)
    except Exception as exc:
        raise ConceptError('insight.concept: backend failed') from exc
    if not result.ok or not isinstance(result.data, ConceptOut):
        kind = result.error.kind if result.error else 'schema'
        raise ConceptError(f'insight.concept: {kind}')
    return result.data.model_dump(exclude={'constraint_check'})


def _inputs(package, insight):
    context_ids = insight.get('context_ids', [])
    contexts = {c.context_id: c for b in package.personas for c in b.context_evidence}
    if (not isinstance(context_ids, list) or not context_ids
            or any(not isinstance(cid, str) or cid not in contexts for cid in context_ids)):
        raise ConceptError('insight.concept: unknown or missing insight contexts')
    selected = set(context_ids)
    blocks = [b for b in package.personas if any(c.context_id in selected for c in b.context_evidence)]
    refs = {}
    owners = {}
    for block in blocks:
        pid = block.persona_evidence.persona_id
        for number, ref in evidence_index(block).items():
            if ref.context_id is not None and ref.context_id not in selected:
                continue
            key = number if len(blocks) == 1 else f'{pid}:{number}'
            refs[key] = ref
            owners[key] = pid
    return [contexts[cid] for cid in dict.fromkeys(context_ids)], blocks, refs, owners


def _basis(sid, version, contexts):
    """Read authors for selected package documents without changing segment rows."""
    doc_ids = sorted({item.doc_id for context in contexts
                      for items in (context.evidence, context.counter_evidence, context.rare_evidence)
                      for item in items})
    authors = set()
    if doc_ids:
        segment = SegmentStore.open(sid, version)
        with closing(sqlite3.connect(segment.path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            # Bound parameters stay below SQLite's variable limit for large packages.
            for offset in range(0, len(doc_ids), 500):
                batch = doc_ids[offset:offset + 500]
                placeholders = ','.join('?' for _ in batch)
                authors.update(row[0] for row in db.execute(
                    f'SELECT DISTINCT author_hash FROM docs WHERE doc_id IN ({placeholders}) '
                    'AND author_hash IS NOT NULL', batch))
    return f"근거 {len(doc_ids)}건 · 작성자 {len(authors)}명에서 종합"


def _hydrate(draft, insight_id, basis, refs, owners):
    points = []
    for number in draft['pain_points']:
        ref = refs[number]
        points.append(dict(evidence_number=number, persona_id=owners[number],
            quote=ref.quote.text, channel=ref.source, doc_id=ref.doc_id,
            location={key: getattr(ref.quote, key) for key in ('field', 'idx', 'start', 'end')},
            context_id=ref.context_id, verified=ref.verified))
    journey = [dict(row, service_grade='prescription', service_label='처방') for row in draft['journey']]
    return dict(id=insight_id, insight_id=insight_id,
        persona_profile=dict(text=draft['persona_profile'], grade='speculated', label='합성값'),
        basis=basis,
        pain_points=points, journey=journey,
        cx_4d_distribution={axis: sum(row['cx_4d'] == axis for row in journey) for axis in CX_4D})



def _validated_draft(sid, payload, context_ids, refs, regenerated, run_task):
    """Keep semantic repair separate from registry-owned schema retries."""
    while True:
        draft = _generate(sid, payload, run_task)
        if any(number not in refs for number in draft['pain_points']):
            raise ConceptError('insight.concept: unknown evidence number')
        invalid = [row['context_id'] for row in draft['journey'] if row['context_id'] not in context_ids]
        if not invalid:
            return draft, regenerated
        if regenerated:
            raise ConceptError('insight.concept: AS-IS context outside insight after regeneration')
        regenerated = True
        payload = {**payload, 'previous_concept': draft, 'invalid_context_ids': invalid}


def make_concept(sid, version, insight_id, *, run_task=None) -> dict:
    """Generate one target, repair invalid contexts once, check and save a revision.

    A constraint violation allows one new concept and a fresh check, just as in
    prescribe(). Remaining violations are saved as blocked. Backend/check errors
    and invalid evidence never save. The returned concept adds its revision.
    AS-IS repair has one shared budget across both prescription attempts.
    """
    run_task = registry.run_task if run_task is None else run_task
    store = PersonaStore.open(sid, version)
    insight = next((row for row in (store.read('insights') or {}).get('items', [])
                    if row.get('id') == insight_id), None)
    if insight is None:
        raise ConceptError(f'insight.concept: insight not found: {insight_id}')
    package = load_package(sid, version)
    contexts, blocks, refs, owners = _inputs(package, insight)
    context_ids = {c.context_id for c in contexts}
    project = (sessions.load_session(sid) or {}).get('projectContext') or getattr(package, 'projectContext', {})
    constraints = list(dict.fromkeys(project.get('constraints', [])))
    payload = dict(insight=insight,
        personas=[dict(persona_id=b.persona_evidence.persona_id,
                       persona_name=b.persona_evidence.persona_name,
                       desire=b.persona_evidence.desire, goal=b.persona_evidence.goal) for b in blocks],
        contexts=[dict(context_id=c.context_id, action=c.action, situation=c.situation.model_dump()) for c in contexts],
        evidence={number: ref.model_dump() for number, ref in refs.items()},
        analysisGoal=project.get('analysisGoal'), keyMetrics=project.get('keyMetrics', []), constraints=constraints)
    basis = _basis(sid, version, contexts)
    regenerated = False
    for attempt in range(2):
        draft, regenerated = _validated_draft(
            sid, payload, context_ids, refs, regenerated, run_task)
        concept = _hydrate(draft, insight_id, basis, refs, owners)
        checked = prescriptions.check_constraints(sid, concept, project, run_task=run_task)
        violations = [row for row in checked if row['verdict'] == 'violates']
        if violations and attempt == 0:
            payload = {**payload, 'previous_concept': draft, 'violations': violations}
            continue
        concept.update(constraint_check=checked, blocked=bool(violations),
                       represcribed=bool(attempt), regenerated=regenerated)
        if violations:
            concept['message'] = '\n'.join(
                f"사내 제약 '{row['constraint']}'를 지키는 처방을 만들지 못했습니다."
                for row in violations)
        current = (store.read('concepts') or {}).get('items', [])
        items = [row for row in current if row.get('insight_id', row.get('id')) != insight_id]
        revision = store.new_revision('concepts', [*items, concept], by='generate', message=None)
        return {**concept, 'revision': revision}
