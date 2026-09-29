from uuid import uuid4
from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from app.context.models import ProjectContext
from app.context.store import (StoreError, locked, assert_writable, load_session,
                               update_session, _update_locked)
from app.context.category import suggest_category
from app.context import versions
from app.external.base import integration_status


class ContextRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def wrapped(request: Request):
            try:
                return await handler(request)
            except StoreError as exc:
                return JSONResponse(status_code=exc.status, content={'status': 'error', 'error': {'kind': exc.kind, 'message': str(exc)}})
            except RequestValidationError:
                return JSONResponse(status_code=422, content={'status': 'error', 'error': {'kind': 'validation', 'message': '입력값을 확인하세요'}})
            except OSError:
                return JSONResponse(status_code=500, content={'status': 'error', 'error': {'kind': 'storage', 'message': '저장소 작업에 실패했습니다'}})
        return wrapped


router = APIRouter(route_class=ContextRoute)


class CategoryRequest(BaseModel):
    bk: str = Field(min_length=1)
    oneLiner: str = ''


class VersionRequest(BaseModel):
    from_v: str = Field(alias='from')
    restartFrom: str
    note: str = ''


class ActiveRequest(BaseModel):
    version: str


def context_patch(ctx):
    if not all(value.strip() for value in (ctx.bk, ctx.oneLiner, ctx.researchQuestion.text)):
        raise StoreError('필수값을 입력하세요', 422, 'validation')
    return {'projectContext': ctx.model_dump(mode='json'),
            'knownInsights': [{'id': f'ki_{i:02d}', 'type': 'statement', 'text': text, 'from': 'stage0'} for i, text in enumerate(ctx.knownInsights, 1)]}


@router.post('/context', status_code=201)
def post_context(ctx: ProjectContext):
    sid = 's' + uuid4().hex
    patch = context_patch(ctx)
    update_session(sid, {'schemaVersion': 2, 'sid': sid, 'step': 'start', 'drafts': {}, **patch})
    return {'sid': sid}


@router.post('/context/category-suggest')
def category_suggest(body: CategoryRequest):
    return suggest_category(body.bk, body.oneLiner)


@router.get('/context/{sid}')
def get_context(sid: str, version: str | None = None):
    data = versions._data(sid, version) if version else load_session(sid)
    if data is None:
        raise StoreError('Session not found', 404, 'not_found')
    return {'projectContext': data.get('projectContext'), 'knownInsights': data.get('knownInsights', []), 'draft': data.get('drafts', {}).get('start')}


@router.put('/context/{sid}')
def put_context(sid: str, ctx: ProjectContext, version: str | None = None):
    patch = context_patch(ctx)
    with locked(sid):
        old = assert_writable(sid, version)
        warnings = []
        if old.get('keywordRounds', {}).get('1'):
            for field in ('oneLiner', 'researchQuestion'):
                if old.get('projectContext', {}).get(field) != patch['projectContext'][field]:
                    warnings.append(field + '_changed_after_r1')
        data = _update_locked(sid, patch)
        return {'projectContext': data['projectContext'], 'warnings': warnings}


@router.patch('/session/{sid}')
def patch_session(sid: str, patch: dict, version: str | None = None):
    if set(patch) - {'step', 'drafts'} or ('step' in patch and not isinstance(patch['step'], str)) or ('drafts' in patch and not isinstance(patch['drafts'], dict)):
        raise StoreError('Only step and drafts may be patched', 400, 'validation')
    with locked(sid):
        assert_writable(sid, version)
        return {'status': 'ok', 'data': _update_locked(sid, patch)}


@router.get('/sessions/{sid}/versions')
def get_versions(sid: str):
    return versions.list_versions(sid)


@router.post('/sessions/{sid}/versions', status_code=201)
def post_version(sid: str, body: VersionRequest):
    return {'version': versions.create_version(sid, body.from_v, body.restartFrom, body.note)}


@router.put('/sessions/{sid}/active-version')
def activate(sid: str, body: ActiveRequest):
    versions.set_active(sid, body.version)
    return {'activeVersion': body.version}


@router.get('/sessions/{sid}/compare')
def compare(sid: str, a: str, b: str, stage: str):
    return versions.compare(sid, a, b, stage)


@router.get('/integrations')
def integrations():
    return integration_status()
