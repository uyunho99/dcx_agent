"""Shared guards for API, compatibility entry point, and detached workers."""
from types import SimpleNamespace

from app.context import store
from app.crawl import control
from app.prep.config import PrepConfig, prep_key

COLLECTION_UNFINISHED = '수집이 끝난 뒤에 전처리를 실행할 수 있습니다.'


def assert_ready(sid, data, cfg):
    cid = data.get('collectionId')
    if control.phase_state(sid, cid) != 'done':
        raise store.StoreError(COLLECTION_UNFINISHED, 409, 'crawl_unfinished')
    identity = SimpleNamespace(name=cfg.embedder, model=cfg.embedModel, dim=cfg.embedDim)
    ref = dict(collectionId=cid, prepKey=prep_key(cid, cfg, identity))
    if ref != data.get('prep', {}).get('derivedRef'):
        store.assert_labeling_not_started(data)
    return ref


def legacy_config(data, config):
    values = {**data.get('prep', {}).get('config', {}),
              **{k: v for k, v in config.items() if k not in {'sid', 'version'}}}
    excluded = config.get('excludeCafes', [])
    if isinstance(excluded, str):
        excluded = [x.strip() for x in excluded.split(',') if x.strip()]
    if excluded:
        values['excludeSources'] = values.get('excludeSources', []) + excluded
    return PrepConfig.model_validate(values)
