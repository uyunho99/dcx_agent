import numpy as np
import pytest
import torch

from app.model import registry
from app.model.net import MultiHeadMLP, HEADS
from app.model.train import EnsembleResult

EMBEDDER = dict(name='fake', model='voyage-4', dim=1024)


def result(anchor=12.):
    members = []
    for i in range(4):
        net = MultiHeadMLP(linear=i == 3)
        with torch.no_grad():
            for p in net.parameters():
                p.zero_()
            for key in ('anchor', 'sem', 'situation'):
                net.heads[key].bias.fill_(anchor)
        members.append(net.state_dict())
    return EnsembleResult(members, {'grade_accuracy': .9}, {}, dict.fromkeys(HEADS, 1.), {}, np.array(['d']))


def save_model(**kwargs):
    return registry.save(result(**kwargs), dict(embedder=EMBEDDER, trainedFrom={'sid': 'origin', 'version': 'v1'},
        bk='test', oneLiner='definition', parent=None))


def test_registry_embedder_mismatch_not_selectable(data_dir):
    mid = save_model()
    assert registry.list_models(EMBEDDER)[0]['selectable'] is True
    row = registry.list_models({**EMBEDDER, 'model': 'other'})[0]
    assert row['modelId'] == mid and row['selectable'] is False
    assert row['reason'] == '다른 임베딩으로 학습된 모델입니다'
    assert row['kind'] == 'ensemble' and row['metrics']['evaluation_split'] == 'validation'
    assert registry.load(mid) is registry.load(mid)
    assert len(registry.load(mid).members) == 4
    assert (data_dir / 'models' / mid / 'members/m3.pt').exists()


def test_registry_rejects_path_escape(data_dir):
    with pytest.raises(Exception):
        registry.load('../outside')


def test_registry_missing_embedder_not_selectable(data_dir):
    from app.context import store
    mid = save_model()
    path = data_dir / 'models' / mid / 'meta.json'
    meta = store.read_json(path)
    del meta['embedder']
    store.write_json(path, meta)
    row = registry.list_models(EMBEDDER)[0]
    assert row['selectable'] is False
    assert row['reason'] == registry.MISMATCH
