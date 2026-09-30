"""Immutable local ensembles, published only after every artifact is complete."""
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

import torch

from app.config import settings
from app.context import store
from app.label import questions, rule
from app.model.net import HEADS, MultiHeadMLP

MISMATCH = '다른 임베딩으로 학습된 모델입니다'


def _root():
    return Path(settings.local_data_dir).resolve() / 'models'


def _path(model_id):
    if not isinstance(model_id, str) or not re.fullmatch(r'm_[a-f0-9]{32}', model_id):
        raise store.StoreError('Invalid model id', 400, 'validation')
    return _root() / model_id


def metadata(model_id):
    value = store.read_json(_path(model_id) / 'meta.json')
    if value is None:
        raise store.StoreError('모델을 찾을 수 없습니다.', 404, 'not_found')
    return value


def save(result, meta, *, training_data=None) -> str:
    if len(result.members) != 4 or set(result.temperatures) != set(HEADS):
        raise ValueError('An ensemble requires four members and all head temperatures')
    model_id = 'm_' + uuid4().hex
    root = _path(model_id)
    staging = root.with_name('.' + model_id)
    staging.mkdir(parents=True)
    try:
        (staging / 'members').mkdir()
        for i, state in enumerate(result.members):
            torch.save(state, staging / 'members' / f'm{i}.pt')
        if training_data is not None:
            torch.save(training_data, staging / 'training.pt')
        store.write_json(staging / 'calib.json', result.temperatures)
        info = dict(meta, modelId=model_id, kind='ensemble', members=4,
            createdAt=store.now(), n=len(result.doc_ids), perHead=result.perHead,
            metrics={**result.metrics, 'evaluation_split': 'validation'},
            rule_version=rule.RULE_VERSION, questions_version=questions.QVER,
            parent=meta.get('parent'), trainingData=training_data is not None)
        store.write_json(staging / 'meta.json', info)
        os.replace(staging, root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return model_id


def list_models(embedder) -> list[dict]:
    rows = []
    for path in sorted(_root().glob('m_*/meta.json')):
        meta = json.loads(path.read_text(encoding='utf-8'))
        selectable = meta['embedder'] == embedder
        rows.append(dict(meta, selectable=selectable, reason=None if selectable else MISMATCH))
    return rows


@dataclass
class Ensemble:
    meta: dict
    members: list
    temperatures: dict


@lru_cache(maxsize=8)
def _load(path):
    root = Path(path)
    meta = store.read_json(root / 'meta.json')
    if meta is None:
        raise store.StoreError('모델을 찾을 수 없습니다.', 404, 'not_found')
    if meta['kind'] != 'ensemble' or meta['members'] != 4:
        raise store.StoreError('지원하지 않는 모델입니다.', 409, 'model')
    members = []
    for i in range(4):
        net = MultiHeadMLP(linear=i == 3)
        net.load_state_dict(torch.load(root / 'members' / f'm{i}.pt', map_location='cpu', weights_only=True))
        members.append(net.eval())
    return Ensemble(meta, members, store.read_json(root / 'calib.json'))


def load(model_id):
    # Include the storage root in the cache key, including when tests change it.
    return _load(str(_path(model_id)))


def dataset(model_id):
    path = _path(model_id) / 'training.pt'
    if not path.exists():
        raise store.StoreError('기존 학습셋이 없는 모델입니다.', 409, 'model')
    return torch.load(path, map_location='cpu', weights_only=True)


def require_compatible(model_id, embedder):
    meta = metadata(model_id)
    if meta['embedder'] != embedder:
        raise store.StoreError(MISMATCH, 409, 'embedder_mismatch')
    return meta
