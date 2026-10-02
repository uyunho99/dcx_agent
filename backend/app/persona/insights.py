"""Derive textual insights, enrich with code metrics, and persist full revisions.

Calculated fields live on each item (radar, odi, opportunity_mean,
default_target, known_badge) so revision/revert retains a coherent snapshot.
"""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Annotated

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from app.context import store as sessions
from app.context.versions import version_dir
from app.llm import registry
from app.llm.base import Attachment, LLMTask
from app.persona.package import load_package
from app.persona.params import INSIGHT_RANGE, RADAR_AXES
from app.persona.radar import embed_axes, radar, session_percentiles
from app.persona.store import PersonaStore

CONCEPT_FAILURE_COPY = '컨셉을 만들지 못했습니다. 다시 시도하세요.'
FAILURE_COPY = '인사이트를 만들지 못했습니다. 다시 시도하세요.'
Text = Annotated[str, Field(min_length=1)]


class InsightItem(BaseModel):
    # Ignore ALL untrusted computed fields, including numeric fields.
    model_config = ConfigDict(extra='ignore', strict=True, str_strip_whitespace=True)
    id: Text
    title: Text
    pain_point: Text
    context_ids: list[Text] = Field(min_length=1)
    known_ki_id: Text | None


class DeriveOut(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)
    # Business range is checked outside the schema to bound regeneration to one.
    items: list[InsightItem]


class InsightError(RuntimeError):
    def __init__(self, reason=None):
        super().__init__(reason or FAILURE_COPY)


def opportunity_bars(insights, odi_by_context) -> dict:
    bars = []
    for item in insights:
        values = [odi_by_context[cid] for cid in dict.fromkeys(item['context_ids'])
                  if odi_by_context[cid] is not None]
        bars.append({'id': item['id'], 'odi': float(np.mean(values)) if values else None})
    available = [bar['odi'] for bar in bars if bar['odi'] is not None]
    mean = float(np.mean(available)) if available else None
    return {'bars': bars, 'mean': mean,
            'targets': [bar['id'] for bar in bars
                        if bar['odi'] is not None and mean is not None and bar['odi'] >= mean]}


def _centroids(sid, version, ids):
    path = version_dir(sid, version) / 'segment' / 'segment.sqlite'
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT context_id, centroid FROM contexts').fetchall()
    vectors = {cid: np.frombuffer(blob, dtype=np.float32).copy()
               for cid, blob in rows if cid in ids and blob is not None}
    if set(vectors) != set(ids):
        raise ValueError('Missing Context centroids')
    return vectors


def derive(sid, version, *, run_task=None, embedder, before_publish=None) -> int:
    store = PersonaStore.open(sid, version)
    store.guard = before_publish
    cards = store.read('cards')
    if cards is None:
        raise InsightError()
    package = load_package(sid, version)
    contexts = {c.context_id: c for b in package.personas for c in b.context_evidence}
    session = sessions.load_session(sid) or {}
    known = session.get('knownInsights', session.get('projectContext', {}).get('knownInsights', []))
    payload = {'cards': cards, 'known_insights': known,
               'contexts': [{'context_id': cid, 'odi': c.metrics.odi} for cid, c in contexts.items()]}
    prompt = (Path(__file__).with_name('prompts') / 'derive.v1.md').read_text(encoding='utf-8')
    run_task = registry.run_task if run_task is None else run_task
    items = None
    for _ in range(2):
        task = LLMTask(task='insight.derive', sid=sid, instructions=prompt,
                       attachments=[Attachment(title='인사이트 입력', body=json.dumps(payload, ensure_ascii=False))],
                       output_schema=DeriveOut)
        try:
            result = run_task(task)
        except sessions.StoreError:
            raise
        except Exception as exc:
            raise InsightError() from exc
        if not result.ok or not isinstance(result.data, DeriveOut):
            raise InsightError()
        candidates = [item.model_dump() for item in result.data.items]
        if (INSIGHT_RANGE[0] <= len(candidates) <= INSIGHT_RANGE[1] and
                len({item['id'] for item in candidates}) == len(candidates) and
                all(set(item['context_ids']) <= contexts.keys() and
                    len(set(item['context_ids'])) == len(item['context_ids']) for item in candidates)):
            items = candidates
            break
        payload['retry'] = '인사이트를 3~8개 생성하고 고유 ID와 입력에 있는 Context ID만 사용하세요.'
    if items is None:
        raise InsightError()
    recompute(sid, version, items, package=package, embedder=embedder)
    # PersonaStore owns its lock. Never surround this mutation with sessions.locked.
    return store.new_revision('insights', items, by='generate', message=None)


def recompute(sid, version, items, *, package=None, embedder):
    """Hydrate validated text with version-local, code-owned metrics in place."""
    package = package or load_package(sid, version)
    data = sessions.read_json(version_dir(sid, version) / 'session.json') or {}
    known = data.get('knownInsights', [])
    known_ids = {row.get('id') if isinstance(row, dict) else f'ki_legacy_{i}'
                 for i, row in enumerate(known)}
    for item in items:
        if item.get('known_ki_id') not in known_ids:
            item['known_ki_id'] = None
    contexts = {c.context_id: c for b in package.personas for c in b.context_evidence}
    try:
        selected = {cid for item in items for cid in item['context_ids']}
        centroids = _centroids(sid, version, selected)
        axes = embed_axes(embedder)
        if axes.ndim != 2 or any(v.shape != (axes.shape[1],) for v in centroids.values()):
            raise InsightError('Preparation embedding dimension does not match Context centroids')
        weights = {cid: c.metrics.doc_count for cid, c in contexts.items()}
        for item in items:
            item['radar'] = radar({cid: centroids[cid] for cid in item['context_ids']}, weights, axes)
        for axis in RADAR_AXES:
            ranks = session_percentiles([item['radar']['raw'][axis] for item in items])
            for item, rank in zip(items, ranks):
                item['radar']['percentile'][axis] = rank
        bars = opportunity_bars(items, {cid: c.metrics.odi for cid, c in contexts.items()})
        for item, bar in zip(items, bars['bars']):
            item.update(odi=bar['odi'], opportunity_mean=bars['mean'],
                        default_target=item['id'] in bars['targets'],
                        known_badge=(f"Known Insight #{item['known_ki_id']}와 같은 내용"
                                     if item['known_ki_id'] is not None else None))
    except (ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        raise InsightError() from exc
    return items


def confirm(sid, version, ids) -> list[str]:
    """Replace the user's confirmed selection; reject unknown IDs atomically."""
    with sessions.locked(sid):
        from app.persona.source import Source
        Source(sid, version).check()
        current = PersonaStore.open(sid, version).read('insights') or {}
        available = {item['id'] for item in current.get('items', [])}
        if not isinstance(ids, list) or any(not isinstance(i, str) or i not in available for i in ids):
            raise sessions.StoreError('Unknown insight ID', 400, 'validation')
        confirmed = list(dict.fromkeys(ids))
        state = sessions.load_session(sid).get('insight', {})
        hidden = [i for i in state.get('confirmed_ids', state.get('confirmed', [])) if i not in available]
        sessions._update_locked(sid, {'insight': {'confirmed': confirmed, 'confirmed_ids': hidden + confirmed}})
    return confirmed
