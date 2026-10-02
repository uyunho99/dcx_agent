"""Version-local persona and insight HTTP contracts.

Workers own inference; store/chat mutations own their session locks. Keep the
client's nested snake_case payloads intact while exposing runId at the boundary.
"""
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.context import store as sessions
from app.label.overview import session
from app.persona import chat, insights, pipeline
from app.persona.package import PackageMissing, load_package
from app.persona.store import PersonaStore
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
    return {**value, 'personas': {pid: {'card': None, **row}
                                for pid, row in value['personas'].items()}}


@router.post('/persona/{sid}/run')
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
    # Historical versions remain immutable even when their source is old.
    try:
        sessions.assert_writable(sid, data['version'])
    except sessions.StoreError:
        pass
    else:
        if pipeline.mark_stale_if_changed(sid, data['version']):
            data, store = _open(sid, data['version'])
    state = data.get('persona', {})
    cards = store.read('cards') or {}
    result = dict(status=state.get('status', 'none'), run=cards.get('run', state.get('run')),
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
    if data.get('persona', {}).get('status') != 'done' or 'stage8' in data.get('stale', {}):
        raise sessions.StoreError('페르소나를 만든 뒤 인사이트를 도출할 수 있습니다.', 409, 'persona_required')


@router.post('/insight/{sid}/run')
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
    return {'runId': work['runId']}


@router.get('/insight/{sid}')
def get_insights(sid: str, version: str | None = None):
    _, store = _open(sid, version)
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
    return {**docs, 'bars': bars, 'radar': radar}


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
