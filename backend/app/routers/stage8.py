"""Version-local persona and insight HTTP contracts.

Workers own inference; store/chat mutations own their session locks. Keep the
client's nested snake_case payloads intact while exposing runId at the boundary.
"""
from typing import Annotated, Literal
from functools import wraps
import json
import sqlite3

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.context import store as sessions
from app.label.overview import session
from app.persona import chat, insights, pipeline
from app.persona.package import PackageMissing, evidence_ready, load_package
from app.persona.store import PersonaStore
from app.persona.insight_pipeline import serialized
from app.persona.source import require_persona
from app.routers.labeling_v2 import LabelRoute
from app.work import runner

router = APIRouter(route_class=LabelRoute)
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Target = Annotated[str, StringConstraints(pattern=r'^(insights|concept:.+)$')]


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PersonaRun(Body):
    fresh: bool = False
    personas: list[Text] | None = None


class Retry(Body):
    run: Text


class InsightRun(Body):
    mode: Literal['derive', 'concept']
    target: Text | None = None


class Chat(Body):
    target: Target
    message: Text


class Revert(Body):
    target: Target
    revision: int = Field(ge=1, strict=True)


class Confirm(Body):
    ids: list[Text]


def _open(sid, version=None, writable=False):
    data = session(sid, version, writable=writable)
    if sessions.is_legacy(data):
        raise sessions.StoreError('구버전 세션은 기존 페르소나 화면에서 확인하세요.', 409, 'legacy_session')
    return data, PersonaStore.open(sid, data['version'])


def _idle(sid, version, kind):
    for work in reversed(runner.status(sid)):
        if work['version'] == version and work['state'] in ('running', 'paused'):
            same = work['kind'] == kind
            raise sessions.StoreError('이미 진행 중입니다.' if same else '진행 중인 작업이 끝난 뒤 다시 시도하세요.',
                                      409, 'running' if same else 'locked')


def _package(sid, version):
    try:
        if not evidence_ready(sid, version):
            raise PackageMissing()
        return load_package(sid, version)
    except PackageMissing as exc:
        raise sessions.StoreError('근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다.',
                                  409, 'evidence_required') from exc


def _ready(store, name):
    value = store.read(name)
    if value is None:
        raise sessions.StoreError('아직 결과가 준비되지 않았습니다.', 409, 'not_ready')
    return value


def _cards(store):
    value = _ready(store, 'cards')
    rows = {pid: {'card': None, **row} for pid, row in value['personas'].items()}
    if any(row['status'] == 'failed' for row in rows.values()):
        try:
            package = load_package(store.sid, store.version)
        except PackageMissing:
            package = None
        for block in package.personas if package else []:
            persona = block.persona_evidence
            row = rows.get(persona.persona_id)
            if row and row['status'] == 'failed':
                row['package_counts'] = dict(doc_count=persona.metrics.doc_count,
                    author_count=persona.metrics.author_count,
                    context_count=len(block.context_evidence))
    return {**value, 'personas': rows}


def _serialize_launch(function):
    @wraps(function)
    def launch(sid, *args, **kwargs):
        # Covers the idle check through durable registration for both kinds.
        # Distinct from session/inference locks; inline test workers are safe.
        with serialized(sid, '.stage8-launch.lock'):
            return function(sid, *args, **kwargs)
    return launch


@router.post('/persona/{sid}/run')
@_serialize_launch
def start_persona(sid: str, body: PersonaRun = PersonaRun(), version: str | None = None):
    with sessions.locked(sid):
        data, _ = _open(sid, version, writable=True)
        package = _package(sid, data['version'])
        ids = {b.persona_evidence.persona_id for b in package.personas}
        if body.personas is not None and not set(body.personas) <= ids:
            raise sessions.StoreError('Unknown Persona', 400, 'validation')
        _idle(sid, data['version'], 'persona')
    work = runner.start(sid, data['version'], 'persona', body.model_dump(exclude_none=True))
    return {'runId': work['runId']}


@router.get('/persona/{sid}/status')
def persona_status(sid: str, version: str | None = None):
    data, store = _open(sid, version)
    try:
        # Historical versions remain immutable even when their source is old.
        try:
            sessions.assert_writable(sid, data['version'])
        except sessions.StoreError:
            pass
        else:
            if pipeline.mark_stale_if_changed(sid, data['version']):
                data, store = _open(sid, data['version'])
        try:
            package = load_package(sid, data['version'])
            has_package = evidence_ready(sid, data['version'])
            evidence_required = not has_package or not pipeline._confirmed_matches(sid, data['version'], package)
        except PackageMissing:
            has_package = False
            evidence_required = True
    except sqlite3.Error as exc:
        raise sessions.StoreError('근거 상태를 확인하지 못했습니다. 다시 시도하세요.',
                                  409, 'evidence_unavailable') from exc
    state = data.get('persona', {})
    cards = store.read('cards') or {}
    result = dict(package=has_package, evidence_required=evidence_required, status=state.get('status', 'none'), run=cards.get('run', state.get('run')),
                  progress=state.get('progress', 0), personas=[
                      dict(id=pid, status=row['status'], error=row.get('error'))
                      for pid, row in cards.get('personas', {}).items()])
    work = next((w for w in reversed(runner.status(sid))
                 if w['kind'] == 'persona' and w['version'] == data['version']), None)
    if work and work['state'] != 'done' and result['status'] != 'stale':
        result.update(status=work['state'], progress=work.get('progress', result['progress']))
    report = store.read('stage_8')
    if report is not None:
        result['stage8'] = report
    return result


@router.get('/persona/{sid}/cards')
def persona_cards(sid: str, version: str | None = None):
    return _cards(_open(sid, version)[1])


@router.get('/persona/{sid}/cards/{item_id}')
def persona_card(sid: str, item_id: str, version: str | None = None):
    rows = _cards(_open(sid, version)[1])['personas']
    if item_id not in rows:
        raise sessions.StoreError('Persona not found', 404, 'not_found')
    return rows[item_id]


@router.post('/persona/{sid}/cards/{item_id}/retry')
@_serialize_launch
def retry_persona(sid: str, item_id: str, body: Retry, version: str | None = None):
    with sessions.locked(sid):
        data, store = _open(sid, version, writable=True)
        pipeline.assert_run(sid, data['version'], body.run)
        if item_id not in _ready(store, 'cards')['personas']:
            raise sessions.StoreError('Persona not found', 404, 'not_found')
        _package(sid, data['version'])
        _idle(sid, data['version'], 'persona')
    runner.start(sid, data['version'], 'persona', {'run': body.run, 'personas': [item_id]})
    return persona_status(sid, data['version'])


@router.get('/persona/{sid}/map')
def persona_map(sid: str, version: str | None = None):
    return _ready(_open(sid, version)[1], 'map')


@router.get('/persona/{sid}/tree')
def persona_tree(sid: str, version: str | None = None):
    return _ready(_open(sid, version)[1], 'tree')


def _persona_required(data):
    require_persona(data)


@router.post('/insight/{sid}/run')
@_serialize_launch
def start_insight(sid: str, body: InsightRun, version: str | None = None):
    data, _ = _open(sid, version, writable=True)
    # This helper owns its mutation lock; reconcile before the locked gate.
    pipeline.mark_stale_if_changed(sid, data['version'])
    with sessions.locked(sid):
        data, store = _open(sid, version, writable=True)
        _persona_required(data)
        _idle(sid, data['version'], 'insight')
        if body.mode == 'concept':
            ids = {row['id'] for row in (store.read('insights') or {}).get('items', [])}
            if not ids or (body.target is not None and body.target not in ids):
                raise sessions.StoreError('Unknown insight target', 400, 'validation')
    work = runner.start(sid, data['version'], 'insight', body.model_dump(exclude_none=True))
    # Register the accepted run even if the child fails before its first checkpoint.
    # Do not overwrite a checkpoint already published by a fast worker.
    with sessions.locked(sid):
        sessions.assert_writable(sid, data['version'])
        path = store.path.parent / 'session.json'
        accepted = sessions.read_json(path)
        state = accepted.setdefault('insight', {})
        if state.get('run') != work['runId']:
            state.update(run=work['runId'], mode=body.mode, target=body.target,
                         status='running', reason=None)
        sessions.write_json(path, accepted)
    return {'runId': work['runId']}


@router.get('/insight/{sid}')
def get_insights(sid: str, version: str | None = None):
    data, store = _open(sid, version)
    docs = {name: store.read(name) or dict(revision=0, items=[], history=[])
            for name in ('insights', 'concepts')}
    items = docs['insights']['items']
    bars = None
    radar = None
    if items:
        bars = dict(bars=[dict(id=row['id'], odi=row.get('odi')) for row in items],
                    mean=items[0].get('opportunity_mean'),
                    targets=[row['id'] for row in items if row.get('default_target')])
        radar = {row['id']: row['radar'] for row in items if 'radar' in row}
    return {**docs, 'bars': bars, 'radar': radar, 'worker': _insight_worker(sid, data)}


@router.post('/insight/{sid}/concept/{item_id}')
def create_concept(sid: str, item_id: str, version: str | None = None):
    return start_insight(sid, InsightRun(mode='concept', target=item_id), version)


@router.post('/insight/{sid}/chat')
def edit_insight(sid: str, body: Chat, version: str | None = None):
    data, _ = _open(sid, version, writable=True)
    return chat.edit(sid, data['version'], body.target, body.message)


@router.post('/insight/{sid}/revert')
def revert_insight(sid: str, body: Revert, version: str | None = None):
    data, _ = _open(sid, version, writable=True)
    return chat.revert(sid, data['version'], body.target, body.revision)


@router.put('/insight/{sid}/confirm')
def confirm_insights(sid: str, body: Confirm, version: str | None = None):
    data, _ = _open(sid, version, writable=True)
    return {'confirmed': insights.confirm(sid, data['version'], body.ids)}


def _insight_worker(sid, data):
    state = data.get('insight', {})
    work = next((w for w in reversed(runner.status(sid))
                 if w['kind'] == 'insight' and w['version'] == data['version']), None)
    status = state.get('status', 'idle')
    reason = state.get('reason')
    run_id = state.get('run')
    mode, target = state.get('mode'), state.get('target')
    # A reset removes the pipeline run; old terminal supervisor rows are history.
    if work and ((run_id and work.get('runId') == run_id) or work['state'] in ('running', 'paused')):
        same = work.get('runId') == run_id
        run_id = work.get('runId')
        # Supervisor detects crashes even when the pipeline never got to write.
        if not (same and status == 'done') and (work['state'] != 'done' or not same):
            status = work['state']
        reason = reason if same else None
        if not same:
            mode, target = None, None
        from app.work.status import database_path, transaction
        if database_path(sid).exists():
            with transaction(sid) as db:
                row = db.execute('SELECT args_json FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if row:
                args = json.loads(row[0])
                mode, target = args.get('mode'), args.get('target')
    if status == 'paused':
        status = 'running'
    if status not in ('idle', 'running', 'done', 'failed', 'interrupted'):
        status = 'idle'
    if status in ('failed', 'interrupted') and (not isinstance(reason, str) or not any('가' <= c <= '힣' for c in reason)):
        reason = (insights.CONCEPT_FAILURE_COPY if mode == 'concept' else insights.FAILURE_COPY) if status == 'failed' else '작업이 중단되었습니다. 이어서 진행하세요.'
    if status in ('idle', 'running', 'done'):
        reason = None
    return dict(status=status, reason=reason, runId=run_id, mode=mode, target=target)
