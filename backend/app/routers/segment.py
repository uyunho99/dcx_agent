"""Version-local stage-six review API; computation belongs to the worker."""
from contextlib import contextmanager
import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.config import settings
from app.context import store as sessions
from app.context.versions import version_dir
from app.label.overview import session
from app.model.infer import prepared_root
from app.routers.labeling_v2 import LabelRoute
from app.segment import pipeline
from app.segment.store import SegmentStore
from app.work import runner

router = APIRouter(prefix='/segment/{sid}', route_class=LabelRoute)
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
STALE = '다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요.'
LAYERS = {'clusters': 'cluster_id', 'personas': 'persona_id', 'contexts': 'context_id'}


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Run(Body):
    k: int | None = Field(default=None, ge=3, le=8, strict=True)
    confirmReset: bool = False


class Confirmation(Body):
    run: Text
    name: Text
    confirm: Literal[True]


class PersonaConfirmation(Confirmation):
    desire: Text
    goals: list[Text] = Field(min_length=1, max_length=3)


class ContextConfirmation(Confirmation):
    action: Text


class ContextItem(Body):
    id: Text
    name: Text
    action: Text


class BulkConfirmation(Body):
    run: Text
    contexts: list[ContextItem] = Field(min_length=1)


class RequestMemo(Body):
    layer: Literal['clusters']
    id: Text
    kind: Literal['split', 'merge']
    note: Text


def _check_run(store, run):
    if run != store.get_run():
        raise sessions.StoreError(STALE, 409, 'stale_run')


class ConfirmationStore(SegmentStore):
    """Serialize the generation check with each store confirmation transaction.

    A session lock alone is insufficient: the worker publishes its generation
    in SQLite independently. This instance is private to one HTTP request.
    """
    expected_run = None

    @contextmanager
    def _db(self, *, write=False):
        with super()._db(write=write) as db:
            if write and self.expected_run is not None:
                row = db.execute("SELECT value FROM meta WHERE key='run'").fetchone()
                if row is None or row['value'] != self.expected_run:
                    raise sessions.StoreError(STALE, 409, 'stale_run')
            yield db


def _open(sid, version=None, writable=False):
    data = session(sid, version, writable=writable)
    if sessions.is_legacy(data):
        raise sessions.StoreError('구버전 세션은 기존 구획 화면에서 확인하세요.', 409, 'legacy_session')
    return data, ConfirmationStore.open(sid, data['version'])


def _gate(store, layer):
    previous = {'personas': 'clusters', 'contexts': 'personas'}.get(layer)
    if previous:
        rows = getattr(store, previous)()
        if not rows or not all(r['confirmed_at'] for r in rows):
            raise sessions.StoreError('앞 층을 모두 확정한 뒤 진행하세요.', 409, 'locked')


def _counts(store):
    return {layer: f'{sum(bool(r["confirmed_at"]) for r in rows)}/{len(rows)}'
            for layer in LAYERS for rows in [getattr(store, layer)()]}


def _camel(key):
    first, *rest = key.split('_')
    return first + ''.join(word.capitalize() for word in rest)


def _rows(store, layer, parent=None):
    key = LAYERS[layer]
    rows = getattr(store, layer)(parent) if layer != 'clusters' else store.clusters()
    # Aggregate in SQLite rather than materializing up to a million documents.
    with store._db() as db:
        counts = {r[key]: (r['n'], r['authors']) for r in db.execute(
            f'SELECT {key}, count(*) AS n, count(DISTINCT NULLIF(author_hash, \'\')) AS authors '
            f'FROM docs GROUP BY {key}')}
    result = []
    array_fields = {'keywords', 'reps', 'requests', 'goals', 'goals_draft', 'centrality', 'similar', 'flags'}
    object_fields = {'quality', 'channels', 'dims_summary'}
    for row in rows:
        item = {_camel(k): v for k, v in row.items()
                if k not in {key, 'confirmed_at', 'centroid', 'metrics'}}
        for field in array_fields & row.keys():
            item[_camel(field)] = row[field] or []
        for field in object_fields & row.keys():
            item[_camel(field)] = row[field] or {}
        item.update(id=row[key], confirmed=bool(row['confirmed_at']), docs=counts.get(row[key], (0, 0))[0])
        if layer == 'clusters':
            item['channelSkew'] = (row.get('metrics') or {}).get('channel_skew', False)
        if layer == 'personas':
            item['authors'] = counts.get(row[key], (0, 0))[1]
            item['network'] = row.get('network') or {'nodes': [], 'edges': []}
        result.append(item)
    return result


def _report(sid, data):
    return sessions.read_json(version_dir(sid, data['version']) / 'segment/stage_6.json')


@router.post('/run')
def start(sid: str, body: Run = Run(), version: str | None = None):
    with sessions.locked(sid):
        data, store = _open(sid, version, writable=True)
        ref = data.get('training', {}).get('exportRef')
        path = (Path(settings.local_data_dir) / ref).resolve() if isinstance(ref, str) and ref else None
        base = (Path(settings.local_data_dir) / 'classified' / sid).resolve()
        if path is None or not path.is_relative_to(base) or path.name != 'relevant.jsonl' or not path.is_file():
            raise sessions.StoreError('학습 단계에서 결과를 저장한 뒤 클러스터링을 실행하세요.', 409, 'stage5_required')
        if (body.k is not None or any(getattr(store, layer)() for layer in LAYERS)) and not body.confirmReset:
            raise sessions.StoreError('다시 나누면 확정값이 지워집니다. 다시 나누기를 확인하세요.', 409, 'confirm_required')
        selected = data['version']
    work = runner.start(sid, selected, 'segment', {'k': body.k, 'fresh': body.confirmReset})
    return {'runId': work['runId']}


@router.get('/status')
def status(sid: str, version: str | None = None):
    data, store = _open(sid, version)
    segment = data.get('segment', {})
    work = next((r for r in reversed(runner.status(sid))
                 if r['kind'] == 'segment' and r['version'] == data['version']), None)
    result = dict(run=store.get_run(), status=segment.get('status', 'none'),
                  step=segment.get('step', 'load'), progress=segment.get('progress', 0), confirm=_counts(store))
    if work and work['state'] != 'done':
        detail = work.get('detail') or {}
        result.update(status=work['state'], step=detail.get('step', result['step']),
                      progress=work.get('progress', result['progress']))
        reason = detail.get('reason') or work.get('error')
        if reason or work['state'] in ('failed', 'interrupted'):
            result['reason'] = reason or '이어서 진행'
    report = _report(sid, data)
    if report:
        result['stage6'] = report
    return result


@router.get('/clusters')
def clusters(sid: str, version: str | None = None):
    data, store = _open(sid, version)
    return dict(run=store.get_run(), clusters=_rows(store, 'clusters'),
                kSuggest=(_report(sid, data) or {}).get('L1'))


@router.get('/personas')
def personas(sid: str, cluster: str | None = None, version: str | None = None):
    _, store = _open(sid, version)
    _gate(store, 'personas')
    return dict(run=store.get_run(), personas=_rows(store, 'personas', cluster))


@router.get('/contexts')
def contexts(sid: str, persona: str | None = None, version: str | None = None):
    data, store = _open(sid, version)
    _gate(store, 'contexts')
    dims = (_report(sid, data) or {}).get('dims', {})
    return dict(run=store.get_run(), contexts=_rows(store, 'contexts', persona),
                emptyGoalConstraintRatio=dims.get('empty_goal_or_constraint', 0))


@contextmanager
def _confirmation(sid, version, layer, run):
    with sessions.locked(sid):
        data, store = _open(sid, version, writable=True)
        _check_run(store, run)
        _gate(store, layer)
        store.expected_run = run
        yield data, store


def _confirm(sid, version, layer, item_id, body):
    with _confirmation(sid, version, layer, body.run) as (data, store):
        store.confirm(layer, item_id, body.model_dump(exclude={'run', 'confirm'}))
        sessions._update_locked(sid, {'segment': {'confirm': _counts(store)}})
        result = next(r for r in _rows(store, layer) if r['id'] == item_id)
    if layer == 'contexts':
        pipeline.mark_done_if_complete(sid, data['version'])
    return result


@router.put('/clusters/{item_id}')
def confirm_cluster(sid: str, item_id: str, body: Confirmation, version: str | None = None):
    return _confirm(sid, version, 'clusters', item_id, body)


@router.put('/personas/{item_id}')
def confirm_persona(sid: str, item_id: str, body: PersonaConfirmation, version: str | None = None):
    return _confirm(sid, version, 'personas', item_id, body)


@router.put('/contexts/{item_id}')
def confirm_context(sid: str, item_id: str, body: ContextConfirmation, version: str | None = None):
    return _confirm(sid, version, 'contexts', item_id, body)


@router.post('/personas/{item_id}/confirm-contexts')
def confirm_contexts(sid: str, item_id: str, body: BulkConfirmation, version: str | None = None):
    with _confirmation(sid, version, 'contexts', body.run) as (data, store):
        store.confirm_contexts(item_id, [item.model_dump() for item in body.contexts])
        ids = {item.id for item in body.contexts}
        result = dict(run=body.run, contexts=[r for r in _rows(store, 'contexts', item_id) if r['id'] in ids])
    pipeline.mark_done_if_complete(sid, data['version'])
    return result


@router.post('/requests')
def request_memo(sid: str, body: RequestMemo, version: str | None = None):
    with sessions.locked(sid):
        _, store = _open(sid, version, writable=True)
        return store.add_request(body.layer, body.id, body.kind, body.note)


@router.get('/docs')
def docs(sid: str, context: str | None = None, band: Literal['core', 'fringe', 'edge'] | None = None,
         offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000),
         version: str | None = None):
    data, store = _open(sid, version)
    # Capture before reading: a concurrent reset must never label old rows with
    # the new generation, which would let an old page submit valid confirmations.
    run = store.get_run()
    rows = store.docs(context_id=context, band=band, limit=limit, offset=offset)
    filters, values = [], []
    for key, value in (('context_id', context), ('band', band)):
        if value is not None:
            filters.append(f'{key}=?')
            values.append(value)
    with store._db() as db:
        total = db.execute('SELECT count(*) FROM docs' + (' WHERE ' + ' AND '.join(filters) if filters else ''), values).fetchone()[0]
    # Read only the requested originals into memory, preserving collection source.
    wanted = {r['doc_id'] for r in rows}
    originals = {}
    if wanted:
        for path in sorted((prepared_root(sid, data) / 'docs').glob('*.jsonl')):
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    doc = json.loads(line)
                    if doc['doc_id'] in wanted:
                        originals[doc['doc_id']] = doc
                        if len(originals) == len(wanted):
                            break
            if len(originals) == len(wanted):
                break
    items = []
    for row in rows:
        original = originals.get(row['doc_id'], {})
        items.append({**{k: original.get(k, [] if k == 'comments' else '')
                         for k in ('title', 'body', 'comments', 'url')},
                      **{_camel(k): v for k, v in row.items()}})
    return dict(run=run, docs=items, total=total, offset=offset, limit=limit)
