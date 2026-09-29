"""Session-owned keyword API; request bodies never supply project context."""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, ValidationError

from app.context import store
from app.context import versions
from app.keywords import rounds
from app.keywords.events import KeywordEvent, append_event
from app.keywords.feedback import write_feedback_md
from app.keywords.taxonomy import is_valid


class KeywordRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def wrapped(request: Request):
            try:
                return await handler(request)
            except store.StoreError as exc:
                body = {'status': 'error', 'error': {'kind': exc.kind, 'message': str(exc)}}
                if isinstance(exc, rounds.Duplicate):
                    body['duplicateOf'] = exc.duplicateOf
                return JSONResponse(body, status_code=exc.status)
            except (RequestValidationError, ValidationError):
                return JSONResponse({'status': 'error', 'error': {'kind': 'validation', 'message': '입력값을 확인하세요'}}, status_code=422)
            except OSError:
                return JSONResponse({'status': 'error', 'error': {'kind': 'storage', 'message': '저장소 작업에 실패했습니다'}}, status_code=500)
        return wrapped


def guard_version(request: Request, sid: str, version: str | None = None):
    if request.method != 'GET':
        store.assert_writable(sid, version=version)


router = APIRouter(prefix='/keywords', route_class=KeywordRoute, dependencies=[Depends(guard_version)])


class Decision(BaseModel):
    id: str
    status: Literal['approved', 'rejected']
    reject: dict | None = None


class CommitRequest(BaseModel):
    gen: int = Field(ge=1)
    decisions: list[Decision]


class ManualRequest(BaseModel):
    kw: str = Field(min_length=1)
    axis: Literal['physical', 'psychological', 'behavioral']
    sub: str
    origin: Literal['manual', 'suggested'] = 'manual'


class SuggestRequest(BaseModel):
    axis: Literal['physical', 'psychological', 'behavioral']
    sub: str


class EventRequest(BaseModel):
    round: int = Field(ge=1, le=4)
    type: Literal['direction', 'approve', 'reject', 'move', 'add', 'unreject']
    kwId: str | None = None
    kw: str | None = None
    tags: list[str] | None = None
    note: str | None = None
    text: str | None = None
    to: dict[str, str] | None = None


@router.post('/{sid}/rounds/{n}')
def start_round(sid: str, n: int):
    return rounds.start_round(sid, n)


@router.get('/{sid}/rounds/{n}')
def round_status(sid: str, n: int, version: str | None = None):
    if version:
        data = store.read_json(versions.version_dir(sid, version) / 'session.json')
        value = (data or {}).get('keywordRounds', {}).get(str(n))
        if value is None:
            raise store.StoreError('라운드 작업이 없습니다', 404, 'not_found')
        return {**value['job'], **{key: value.get(key) for key in ('keywords', 'inputs', 'below_min', 'committed', 'promptVersion')}}
    return rounds.round_status(sid, n)


@router.post('/{sid}/rounds/{n}/commit')
def commit_round(sid: str, n: int, body: CommitRequest):
    decisions = [d.model_dump() for d in body.decisions]
    rounds.commit_round(sid, n, decisions, gen=body.gen)
    return {'status': 'ok', 'round': n, 'gen': body.gen}


@router.post('/{sid}/manual')
def manual(sid: str, body: ManualRequest):
    return rounds.add_manual(sid, **body.model_dump())


@router.post('/{sid}/suggest-words')
def suggest_words(sid: str, body: SuggestRequest):
    return rounds.suggest_words(sid, body.axis, body.sub)


@router.post('/{sid}/coverage')
def coverage(sid: str):
    return rounds.compute_coverage(sid)


@router.get('/{sid}')
def keywords(sid: str, version: str | None = None):
    path = store.session_dir(sid)
    if version:
        path = versions.version_dir(sid, version)
    data = store.read_json(path / 'session.json')
    if data is None:
        raise store.StoreError('세션이 없습니다', 404, 'not_found')
    feedback = path / 'keyword_feedback.md'
    return {key: data.get(key, {} if key != 'keywords' else []) for key in ('keywords', 'keywordRounds', 'coverage')} | {
        'feedback_md': feedback.read_text(encoding='utf-8') if feedback.exists() else ''}


@router.post('/{sid}/events')
def event(sid: str, body: EventRequest):
    ev = KeywordEvent(ts=store.now(), **body.model_dump())
    if ev.type != 'direction':
        def patch(data):
            all_kws = {k.id: k.model_dump() for k in rounds._all_keywords(data)}
            if ev.kwId not in all_kws:
                raise store.StoreError('키워드가 없습니다', 422, 'validation')
            kw = all_kws[ev.kwId]
            ev.kw = kw['kw']
            if ev.type == 'move':
                dest = ev.to or {}
                if not is_valid(dest.get('axis', ''), dest.get('sub', '')):
                    raise store.StoreError('이동할 분류를 확인하세요', 422, 'validation')
                ev.from_ = {'axis': kw['axis'], 'sub': kw['sub']}
                kw.update(axis=dest['axis'], sub=dest['sub'])
            else:
                kw['status'] = 'rejected' if ev.type == 'reject' else 'approved'
                kw['reject'] = {'tags': ev.tags, 'note': ev.note} if ev.type == 'reject' else None
            return {'keywords': [all_kws[k['id']] for k in data.get('keywords', [])],
                    'keywordRounds': {n: {'keywords': [all_kws[k['id']] for k in r.get('keywords', [])]}
                                      for n, r in data.get('keywordRounds', {}).items()}}
        rounds.mutate(sid, patch)
    append_event(sid, ev)
    feedback = write_feedback_md(sid)
    return {'status': 'ok', 'feedback_md': feedback}
