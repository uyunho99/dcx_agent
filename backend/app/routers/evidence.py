"""Version-local stage-seven API; retrieval and mutations belong to the pipeline."""
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.context import store as sessions
from app.context.versions import version_dir
from app.evidence import assemble, pipeline, generation
from app.evidence.cache import known_snapshot
from app.evidence.cache import TagCache, prompt_version
from app.evidence.store import EvidenceStore
from app.label.overview import session
from app.model.infer import prepared_root
from app.routers.labeling_v2 import LabelRoute
from app.segment.store import SegmentStore
from app.work import runner

router = APIRouter(prefix='/evidence/{sid}', route_class=LabelRoute)
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PREREQUISITE = '6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요.'


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Run(Body):
    fresh: bool = False
    contexts: list[Text] | None = None


class Generation(Body):
    run: Text


def _open(sid, version=None, writable=False):
    data = session(sid, version, writable=writable)
    if sessions.is_legacy(data):
        raise sessions.StoreError('구버전 세션은 기존 화면에서 확인하세요.', 409, 'legacy_session')
    return data, EvidenceStore.open(sid, data['version'])


def _report(sid, data, name):
    return sessions.read_json(version_dir(sid, data['version']) / 'evidence' / name)


@router.post('/run')
def start(sid: str, body: Run = Run(), version: str | None = None):
    with sessions.locked(sid):
        data, _ = _open(sid, version, writable=True)
        contexts = SegmentStore.open(sid, data['version']).contexts()
        if (data.get('segment', {}).get('status') != 'done' or 'stage6' in data.get('stale', {})
                or not contexts or not all(c['confirmed_at'] for c in contexts)):
            raise sessions.StoreError(PREREQUISITE, 409, 'segment_required')
        active = [w for w in runner.status(sid) if w['version'] == data['version'] and w['state'] in ('running', 'paused')]
        if any(w['kind'] == 'evidence' for w in active):
            raise sessions.StoreError('근거 탐색이 이미 진행 중입니다.', 409, 'running')
        if active:
            raise sessions.StoreError('진행 중인 작업이 끝난 뒤 실행하세요.', 409, 'locked')
        if body.contexts is not None and not set(body.contexts) <= {c['context_id'] for c in contexts}:
            raise sessions.StoreError('Context not found', 404, 'not_found')
        selected = data['version']
    work = runner.start(sid, selected, 'evidence', body.model_dump())
    return {'runId': work['runId']}


@router.get('/status')
def status(sid: str, version: str | None = None):
    data, store = _open(sid, version)
    snapshot = store.snapshot()
    evidence = data.get('evidence', {})
    states = {r['context_id']: r for r in snapshot.contexts}
    known = pipeline._known(sid, data['version'])
    known_ids = {i['id'] for i in known}
    rows = []
    for context in SegmentStore.open(sid, data['version']).contexts():
        cid = context['context_id']
        row = states.get(cid, {})
        counts = row.get('counts') or {}
        public_counts = {k: v for k, v in counts.items() if type(v) in (int, float)}
        public_counts.update({tab: sum(r['context_id'] == cid and r['tab'] == tab for r in snapshot.selected) for tab in ('all', 'new')})
        rows.append(dict(id=cid, personaId=context['persona_id'], name=context.get('name') or context.get('name_draft') or cid,
                         status=row.get('status', 'queued'), coverage=row.get('coverage'), counts=public_counts,
                         error=row.get('error'), knownChanged=bool(row.get('status') == 'done' and
                         (counts.get('knownChanged') or set(counts.get('knownIds', [])) != known_ids or counts.get('knownSnapshot', {}) != known_snapshot(known)))))
    result = dict(status=evidence.get('status', 'none'), run=snapshot.run,
                  progress=evidence.get('progress', 0), contexts=rows, tagCalls=(evidence.get('detail') or {}).get('tagCalls', 0))
    work = next((w for w in reversed(runner.status(sid)) if w['kind'] == 'evidence' and w['version'] == data['version']), None)
    reason = evidence.get('reason')
    if work and work['state'] != 'done' and result['status'] != 'stale':
        result.update(status={'paused': 'interrupted', 'stopped': 'interrupted', 'cancelled': 'interrupted'}.get(work['state'], work['state']),
                      progress=work.get('progress', result['progress']))
        reason = reason or (work.get('detail') or {}).get('reason') or work.get('error')
    if reason:
        result['reason'] = reason
    report = _report(sid, data, 'stage_7.json')
    if report is not None:
        result['stage7'] = report
        result['tagCalls'] = max(result['tagCalls'], report.get('tag_calls', 0))
    return result


def _source(sid, data, seg, ids):
    """Load only requested originals and cached tags; read routes need no vectors."""
    generation.check_read(sid, data['version'], data)
    docs = {d['doc_id']: d for d in assemble._documents(seg) if d['doc_id'] in ids}
    data, tag_pver = generation.inputs(sid, data['version'], data)
    root = prepared_root(sid, data)
    if root is not None:
        for doc_id, original in assemble._load_docs(root, ids).items():
            docs[doc_id] = {**docs.get(doc_id, {}), **original}
    ref = data.get('prep', {}).get('derivedRef')
    tags = pipeline._project(TagCache.open(sid, ref['prepKey'], tag_pver), ids,
                             pipeline._known(sid, data['version'])) if ref else {}
    if data.get('training', {}).get('exportRef'):
        from app.known.filter import read_export
        for row in read_export(sid, data):
            if row['doc_id'] in docs:
                docs[row['doc_id']]['tagProbs'] = row.get('tagProbs')
    return docs, tags


def _view(row, docs, tags, role='support'):
    return assemble.item_view(row, docs, tags, role)


@router.get('/contexts/{context_id}')
def context(sid: str, context_id: str, tab: Literal['all', 'new'] = 'all', version: str | None = None):
    data, store = _open(sid, version)
    snapshot = store.snapshot()
    seg = SegmentStore.open(sid, data['version'])
    context = next((c for c in seg.contexts() if c['context_id'] == context_id), None)
    if context is None:
        raise sessions.StoreError('Context not found', 404, 'not_found')
    state = next((r for r in snapshot.contexts if r['context_id'] == context_id), {})
    if state.get('status') != 'done' and 'undifferentiated_candidate' not in (context.get('flags') or []):
        raise sessions.StoreError('Context not ready', 409, 'not_ready')
    pool = [r for r in snapshot.candidates if r['context_id'] == context_id]
    selected = [r for r in snapshot.selected if r['context_id'] == context_id and r['tab'] == tab]
    docs, tags = _source(sid, data, seg, {r['doc_id'] for r in pool + selected})
    counter = assemble.counter_evidence(pool, tags, context_mean=assemble.context_polarity_mean(pool, tags))
    rare = assemble.rare_evidence(pool, tags, docs)
    counts = state.get('counts') or {}
    return dict(context={k: v for k, v in context.items() if k != 'centroid'}, tab=tab,
                items=[_view(r, docs, tags, r['role']) for r in selected],
                counter=[_view(r, docs, tags, 'counter') for r in counter], rare=[_view(r, docs, tags, 'rare') for r in rare],
                excludedKnown=counts.get('excludedKnown', 0),
                queries=[{k: r[k] for k in ('dim', 'text', 'origin')} for r in snapshot.queries if r['owner'] == 'context:'+context_id],
                queryFailed=bool(counts.get('query_gen_fail')), undifferentiated=counts.get('undifferentiated', []))


@router.get('/personas/{persona_id}')
def persona(sid: str, persona_id: str, version: str | None = None):
    data, store = _open(sid, version)
    snapshot = store.snapshot()
    seg = SegmentStore.open(sid, data['version'])
    if not any(p['persona_id'] == persona_id for p in seg.personas()):
        raise sessions.StoreError('Persona not found', 404, 'not_found')
    ids = {d['doc_id'] for d in assemble._documents(seg) if d['persona_id'] == persona_id}
    docs, tags = _source(sid, data, seg, ids)
    support = assemble.desire_support([r for r in snapshot.persona_support if r['persona_id'] == persona_id], tags)
    return dict(desireSupport=[_view(r, docs, tags) for r in support],
                artifacts=assemble.artifacts(sorted(ids), tags, (data.get('projectContext') or {}).get('bk') or data.get('bk')))


@router.post('/contexts/{context_id}/refresh-new')
def refresh_new(sid: str, context_id: str, body: Generation, version: str | None = None):
    data, _ = _open(sid, version, writable=True)
    result = pipeline.refresh_new(sid, data['version'], context_id, body.run)
    # The pipeline's internal response predates the non-null frontend quote contract.
    result['queries'] = [{k: r[k] for k in ('dim', 'text', 'origin')} for r in result['queries']]
    for item in result['items'] + result['counter'] + result['rare']:
        if item['quote'] is None:
            item['quote'] = dict(text='', start=None, end=None, verified=False)
    return result


@router.post('/contexts/{context_id}/skip')
def skip(sid: str, context_id: str, body: Generation, version: str | None = None):
    data, _ = _open(sid, version, writable=True)
    pipeline.skip_context(sid, data['version'], context_id, body.run)
    return status(sid, data['version'])


@router.get('/package')
def package(sid: str, version: str | None = None):
    data, store = _open(sid, version)
    snapshot = store.snapshot()
    generation.check_read(sid, data['version'], data)
    if _report(sid, data, 'package_dirty.json'):
        with sessions.locked(sid):
            generation.check(sid, data['version'], store, snapshot.run)
            pipeline._assemble(sid, data['version'])
    result = _report(sid, data, 'package.json')
    if data.get('evidence', {}).get('status') != 'done' or not snapshot.contexts or any(r['status'] not in ('done', 'skipped') for r in snapshot.contexts) or result is None:
        raise sessions.StoreError('Evidence package not ready', 409, 'not_ready')
    return result
