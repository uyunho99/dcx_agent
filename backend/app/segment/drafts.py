"""LLM drafts and advisory cross-cluster badges; never confirm or merge rows.

``generate_drafts`` accepts a ProjectContext or its JSON mapping. Context reps
must be supplied by the caller (the contexts table has no reps column).
Returns per-item flags and persists them in meta.draft_flags, including Persona
flags which have no dedicated column in the committed store schema.
"""
import json
from pathlib import Path
import re

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.llm import registry
from app.llm.base import Attachment, LLMTask
from app.segment import params
from app.vectors.embedder import get_embedder


class _Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    name: str = Field(min_length=1)


class ClusterNameOut(_Output):
    @field_validator('name')
    @classmethod
    def clamp_name(cls, value):
        return value[:15]


class PersonaDraftOut(_Output):
    desire: str = Field(min_length=1)
    goals: list[str] = Field(min_length=1)

    @field_validator('desire')
    @classmethod
    def first_sentence(cls, value):
        return re.split(r'(?<=[.!?。！？])(?![0-9])\s*|[\r\n]+', value, maxsplit=1)[0]

    @field_validator('goals')
    @classmethod
    def first_goals(cls, values):
        values = [value.strip() for value in values[:3]]
        if not all(values):
            raise ValueError('Goals must not be blank')
        return values


class ContextDraftOut(_Output):
    action: str = Field(min_length=1)


def _save(store, table, key, item_id, values):
    encoded = store._encode(table, values)
    with store._db(write=True) as db:
        db.execute(f'UPDATE {table} SET ' + ', '.join(f'{column}=?' for column in encoded)
                   + f' WHERE {key}=?', (*encoded.values(), item_id))


def _draft(sid, task_name, model, one_liner, evidence):
    prompt = (Path(__file__).with_name('prompts') / f'{task_name}.v1.md').read_text(encoding='utf-8')
    task = LLMTask(task=f'segment.{task_name}', sid=sid, instructions=prompt,
                   attachments=[Attachment(title='프로젝트 맥락과 관찰 근거',
                       body=one_liner + '\n' + json.dumps(evidence, ensure_ascii=False))],
                   output_schema=model)
    try:
        result = registry.run_task(task)
        if result.ok and isinstance(result.data, model):
            return result.data.model_dump()
    except Exception:
        # One failed provider call must not prevent drafts for other items.
        pass
    return None


def generate_drafts(sid, store, project_context, *, context_reps=None):
    """Generate one draft per row in layer order, preserving confirmed fields."""
    context = (project_context.model_dump(mode='json')
               if isinstance(project_context, BaseModel) else project_context)
    one_liner = context.get('oneLiner', '')
    context_reps = context_reps or {}
    flags = {}
    clusters = {}
    personas = {}
    for table, key, task, model, empty in (
        ('clusters', 'cluster_id', 'cluster_name', ClusterNameOut, {'name': ''}),
        ('personas', 'persona_id', 'persona_draft', PersonaDraftOut, {'name': '', 'desire': '', 'goals': []}),
        ('contexts', 'context_id', 'context_draft', ContextDraftOut, {'name': '', 'action': ''}),
    ):
        for row in getattr(store, table)():
            item_id = row[key]
            if table == 'clusters':
                evidence = {'keywords': (row['keywords'] or [])[:params.CTFIDF_TOP],
                            'reps': (row['reps'] or [])[:params.REPS]}
            elif table == 'personas':
                evidence = {'targetScope': context.get('targetScope'),
                            'centrality': (row['centrality'] or [])[:params.CENTRALITY_TOP],
                            'reps': (row['reps'] or [])[:params.REPS],
                            'cluster_name': clusters.get(row['cluster_id'], '')}
            else:
                evidence = {'keywords': (row['keywords'] or [])[:params.CTFIDF_TOP],
                            'reps': context_reps.get(item_id, [])[:params.REPS],
                            'dominant_constraint': row['dominant_constraint'],
                            'persona_desire': personas.get(row['persona_id'], '')}
            draft = _draft(sid, task, model, one_liner, evidence)
            flags[item_id] = ['draft_failed'] if draft is None else []
            draft = empty if draft is None else draft
            values = {f'{field}_draft': value for field, value in draft.items()}
            if table == 'clusters':
                quality = dict(row['quality'] or {})
                quality['flags'] = [f for f in quality.get('flags', []) if f != 'draft_failed'] + flags[item_id]
                values['quality'] = quality
                clusters[item_id] = row['name'] or draft['name']
            elif table == 'personas':
                personas[item_id] = row['desire'] or draft['desire']
            else:
                values['flags'] = [f for f in (row['flags'] or []) if f != 'draft_failed'] + flags[item_id]
            _save(store, table, key, item_id, values)
    with store._db(write=True) as db:
        db.execute("INSERT INTO meta(key,value) VALUES ('draft_flags',?) "
                   'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   (json.dumps(flags, ensure_ascii=False),))
    similarity = update_desire_similarity(store)
    return {'flags': flags, 'similarity': similarity}


def update_desire_similarity(store):
    """Replace symmetric badges using normalized Desire draft embeddings only."""
    rows = store.personas()
    badges = {row['persona_id']: [] for row in rows}
    eligible = [row for row in rows if (row['desire_draft'] or '').strip()]
    failed = False
    if len({row['cluster_id'] for row in eligible}) > 1:
        try:
            vectors = np.asarray(get_embedder().embed([row['desire_draft'] for row in eligible]), dtype=np.float64)
            if vectors.ndim != 2 or len(vectors) != len(eligible):
                raise ValueError('Invalid embedding shape')
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = np.divide(vectors, norms, out=np.zeros_like(vectors), where=np.isfinite(norms) & (norms > 0))
            for i, left in enumerate(eligible):
                for j in range(i + 1, len(eligible)):
                    right = eligible[j]
                    if left['cluster_id'] == right['cluster_id']:
                        continue
                    score = float(np.clip(vectors[i] @ vectors[j], -1, 1))
                    if score >= params.DESIRE_SIMILAR:
                        for a, b in ((left, right), (right, left)):
                            badges[a['persona_id']].append({'id': b['persona_id'], 'score': score, 'desire': b['desire_draft']})
        except Exception:
            failed = True
            badges = {row['persona_id']: [] for row in rows}
    with store._db(write=True) as db:
        db.executemany('UPDATE personas SET similar_json=? WHERE persona_id=?',
                       [(json.dumps(value, ensure_ascii=False), key) for key, value in badges.items()])
    return {'failed': failed}
