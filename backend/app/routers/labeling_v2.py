"""Version-aware stage-four API; legacy labeling routes remain untouched."""
import sqlite3
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.context import store
from app.label import audit, rule
from app.label.overview import (session, labels_for, caches_for, index_documents,
                                overview, LEGACY_MESSAGE)
from app.label.route import next_item, rebuild_queue, submit_item
from app.label.schema import Tags
from app.routers.context import ContextRoute
from app.work import runner

class LabelRoute(ContextRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request):
            try:
                return await handler(request)
            except sqlite3.Error:
                return JSONResponse(status_code=500, content={'status': 'error', 'error': {
                    'kind': 'storage', 'message': '저장하지 못했습니다. 입력은 그대로 있습니다. 다시 제출하세요.'}})
        return wrapped


router = APIRouter(prefix='/label', route_class=LabelRoute)
ReviewMode = Literal['escalate', 'audit', 'reissue']


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Mode(Body):
    mode: Literal['llm', 'model']
    modelId: str | None = None


class Preview(Body):
    tags: Tags


class Submit(Preview):
    doc_id: str = Field(min_length=1)
    labeler: str = Field(min_length=1)
    mode: ReviewMode
    round: int | None = Field(default=None, ge=1)
    elapsedSeconds: float | None = Field(default=None, gt=0, le=3600, allow_inf_nan=False)


@router.post('/rule/preview')
def preview(body: Preview):
    return {'level': rule.grade(dict(anchor=int(body.tags.anchor), situation=int(body.tags.situation), **body.tags.sem))}


@router.post('/{sid}/mode')
def mode(sid: str, body: Mode, version: str | None = None):
    with store.locked(sid):
        data = session(sid, version, writable=True)
        if data.get('labeling', {}).get('started'):
            raise store.StoreError('새 버전에서 방식을 바꾸세요')
        if body.mode == 'model' and not body.modelId:
            raise store.StoreError('분류 모델을 선택하세요.', 422, 'validation')
        store._update_locked(sid, {'labeling': body.model_dump()})
        return body.model_dump()


@router.post('/{sid}/start')
@router.post('/{sid}/judge')
def start(sid: str, version: str | None = None):
    with store.locked(sid):
        data = session(sid, version, writable=True)
        if data.get('prep', {}).get('status') != 'done' or not data.get('prep', {}).get('derivedRef'):
            raise store.StoreError('전처리를 먼저 완료하세요.')
        labels = labels_for(sid, data)
        index_documents(sid, data, labels)
        caches = caches_for(sid, data)
        refs = {name: str(cache.path.parent.relative_to(settings.local_data_dir)) for name, cache in caches.items()}
        # Persist the start lock and each successful launch, including a partial launch.
        store._update_locked(sid, {'labeling': {'started': True, 'mode': data.get('labeling', {}).get('mode', 'llm'),
            'modelId': data.get('labeling', {}).get('modelId'), 'judgeRefs': refs}})
        works = {}
        for name in ('jev', 'gpt'):
            works[name] = runner.start(sid, data['version'], 'judge', {'labeler': name})
            store._update_locked(sid, {'labeling': {'judgeRuns': {name: works[name]['runId']}}})
        return dict(started=True, workers=works)


@router.post('/{sid}/judge/{labeler}/{action}')
def control(sid: str, labeler: Literal['jev', 'gpt'], action: Literal['pause', 'resume'], version: str | None = None):
    with store.locked(sid):
        data = session(sid, version, writable=True)
        run_id = data.get('labeling', {}).get('judgeRuns', {}).get(labeler)
        work = next((r for r in runner.status(sid) if r['runId'] == run_id), None)
        if work is None:
            raise store.StoreError('판정을 먼저 시작하세요.')
        if action == 'resume' and work['state'] in ('failed', 'interrupted'):
            result = runner.start(sid, data['version'], 'judge', {'labeler': labeler})
            store._update_locked(sid, {'labeling': {'judgeRuns': {labeler: result['runId']}}})
            return result
        return runner.request(sid, run_id, action)


@router.get('/{sid}/overview')
def get_overview(sid: str, version: str | None = None):
    with store.locked(sid):
        data = session(sid, version)
        writable = not store.is_legacy(data) and (version is None or version == store.load_session(sid)['version'])
        return overview(sid, version, mark_seen=writable, sync=writable)


@router.get('/{sid}/next')
def next_review(sid: str, mode: ReviewMode = 'escalate', version: str | None = None, round: int | None = None):
    with store.locked(sid):
        data = session(sid, version)
        if store.is_legacy(data):
            raise store.StoreError(LEGACY_MESSAGE)
        item = next_item(labels_for(sid, data), mode, round)
        return dict(item=item, message=None if item else '사람이 볼 문서가 없습니다. 감사 라운드를 만들거나 학습으로 넘어가세요.')


@router.post('/{sid}/submit')
def submit(sid: str, body: Submit, version: str | None = None):
    with store.locked(sid):
        data = session(sid, version, writable=True)
        return submit_item(labels_for(sid, data), body.doc_id, body.labeler, body.mode,
                           body.tags, body.round, body.elapsedSeconds, caches_for(sid, data))


@router.post('/{sid}/audit')
def new_audit(sid: str, version: str | None = None):
    with store.locked(sid):
        data = session(sid, version, writable=True)
        labels = labels_for(sid, data)
        caches = caches_for(sid, data)
        rebuild_queue(labels, caches.get('jev'), caches.get('gpt'))
        if next_item(labels, 'audit') or next_item(labels, 'reissue'):
            raise store.StoreError('진행 중인 감사 라운드를 먼저 완료하세요.')
        with labels._db() as db:
            count = db.execute("SELECT count(*) FROM final WHERE route='accepted'").fetchone()[0]
            previous = db.execute('SELECT COALESCE(MAX(round),0) FROM audit_set').fetchone()[0]
        if count < settings.audit_size:
            raise store.StoreError(f'채택 라벨 {settings.audit_size}건 이상일 때 감사를 만들 수 있습니다.')
        # T10 exposes a threshold-driven sampler; manual creation bypasses only the threshold.
        round_id = audit.maybe_new_round(labels, settings.audit_first + previous * settings.audit_every)
        return {'round': round_id}
