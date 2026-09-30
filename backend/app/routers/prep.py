"""Stage-three API and the detached preparation worker entry point."""
from pathlib import Path
import re
from types import SimpleNamespace

from fastapi import APIRouter
from pydantic import ConfigDict

from app.config import settings
from app.context import store, versions
from app.prep.config import PrepConfig, prep_key
from app.routers.context import ContextRoute
from app.vectors.embedder import FakeEmbedder, VoyageEmbedder
from app.work import runner

router = APIRouter(prefix='/prep', route_class=ContextRoute)
UNCONNECTED = '임베딩 API가 연결되지 않았습니다. 연결하거나 내부용 설정에서 가짜 임베더로 바꾸세요.'


class Config(PrepConfig):
    model_config = ConfigDict(extra='forbid')


def _session(sid, version=None, writable=False):
    data = versions._data(sid, version) if version and not writable else store.load_session(sid)
    if data is None:
        raise store.StoreError('Session not found', 404, 'not_found')
    if store.is_legacy(data):
        raise store.StoreError('구버전 세션은 3단계를 실행할 수 없습니다.', 409, 'legacy_session')
    if writable:
        store.assert_writable(sid, version)
    return data


def _root(sid, cid, key):
    if not isinstance(cid, str) or not re.fullmatch(r'c[1-9][0-9]*', cid):
        raise store.StoreError('수집본을 먼저 준비하세요.', 409, 'collection_required')
    if not isinstance(key, str) or not re.fullmatch(r'p_[0-9a-f]{12}', key):
        raise store.StoreError('Invalid preparation key', 400, 'validation')
    return Path(settings.local_data_dir) / 'derived' / sid / cid / key


def _save(sid, **values):
    # Caller holds locked(sid). Replace config dictionaries (including deletions),
    # while retaining unrelated session/prep fields in one atomic write.
    data = store.load_session(sid)
    prep = {**data.get('prep', {}), **values, 'savedAt': store.now()}
    if 'config' in values:
        data['prep'] = prep
        data['updatedAt'] = store.now()
        store.write_json(store.session_dir(sid) / 'session.json', data)
    else:
        store._update_locked(sid, {'prep': prep})
    return prep


def _view(sid, data):
    prep = data.get('prep', {})
    state = prep.get('status', 'none')
    work = next((row for row in runner.status(sid)
                 if row['kind'] == 'prep' and row['runId'] == prep.get('runId')), None)
    error = None
    if work and state != 'stale':
        state = work['state']
        if state == 'failed':
            error = dict(kind='embedder_unconnected', message=UNCONNECTED) if work['error'] == 'EmbedderUnconnected' else dict(
                kind='prep_failed', message='전처리에 실패했습니다. 설정을 확인하고 다시 실행하세요.')
    report = None
    ref = prep.get('derivedRef')
    if state == 'done' and ref:
        report = store.read_json(_root(sid, ref['collectionId'], ref['prepKey']) / 'stage_3.json')
    return dict(status=state, progress=work['progress'] if work else (1 if state == 'done' else 0),
                detail=work['detail'] if work else {}, runId=prep.get('runId'),
                derivedRef=ref, stage3=report, error=error)


@router.put('/{sid}/config')
def config(sid: str, body: Config, version: str | None = None):
    with store.locked(sid):
        data = _session(sid, version, writable=True)
        store.assert_labeling_not_started(data)
        if _view(sid, data)['status'] in ('running', 'paused'):
            raise store.StoreError('전처리 작업이 끝난 뒤 설정을 바꾸세요.')
        if (body.embedModel, body.embedDim) != (settings.embed_model, settings.embed_dim):
            raise store.StoreError('임베딩 모델과 차원 설정을 확인하세요.', 422, 'validation')
        prep = _save(sid, config=body.model_dump(), status='none', derivedRef=None, runId=None)
        return dict(status='ok', prep=prep)


@router.post('/{sid}/run')
def run(sid: str, version: str | None = None):
    with store.locked(sid):
        data = _session(sid, version, writable=True)
        current = _view(sid, data)
        if current['status'] in ('running', 'paused'):
            return current
        cfg = PrepConfig.model_validate(data.get('prep', {}).get('config', {}))
        identity = SimpleNamespace(name=cfg.embedder, model=cfg.embedModel, dim=cfg.embedDim)
        cid = data.get('collectionId')
        key = prep_key(cid, cfg, identity)
        root = _root(sid, cid, key)
        ref = dict(collectionId=cid, prepKey=key)
        manifest = store.read_json(root / 'manifest.json')
        # Only fully published results can bypass the worker (and provider setup).
        if (manifest and manifest.get('status') == 'done' and manifest.get('compatWritten')
                and (root / 'stage_3.json').exists()
                and (Path(settings.local_data_dir) / manifest['compatRef']).exists()):
            _save(sid, config=cfg.model_dump(), derivedRef=ref, status='done', runId=None)
            return {**_view(sid, store.load_session(sid)), 'reused': True}
        work = runner.start(sid, data['version'], 'prep', {'config': cfg.model_dump()})
        _save(sid, config=cfg.model_dump(), derivedRef=ref, status=work['state'], runId=work['runId'])
        return dict(status=work['state'], runId=work['runId'], progress=work['progress'], reused=False)


@router.get('/{sid}/status')
def status(sid: str, version: str | None = None):
    with store.locked(sid):
        data = _session(sid, version)
        result = _view(sid, data)
        if (version is None or version == store.load_session(sid)['version']) and result['status'] != data.get('prep', {}).get('status', 'none'):
            _save(sid, status=result['status'])
        return result


def run_worker(ctx):
    """Fail disconnected production runs before T04 can publish zero vectors."""
    from app.prep.pipeline import run_prep

    cfg = PrepConfig.model_validate(ctx.args['config'])
    embedder = FakeEmbedder() if cfg.embedder == 'fake' else VoyageEmbedder()
    if (embedder.model, embedder.dim) != (cfg.embedModel, cfg.embedDim):
        raise ValueError('Preparation embedding model/dimension must match configured embedder')
    run_prep(ctx, ctx.sid, ctx.version)
