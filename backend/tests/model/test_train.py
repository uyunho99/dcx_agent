import json
import numpy as np
import pytest
import torch
from app.label import rule


def setup_module():
    torch.manual_seed(12)
    torch.set_num_threads(2)


def row(i=0, source='human', anchor=True):
    tags = dict(anchor=anchor, sem={s: int(s == 'sense') for s in rule.SEM},
                situation=False, signal='pain', reason_code='other')
    return dict(doc_id=str(i), source=source, route='accepted', tags_json=json.dumps(tags),
                votes_json=json.dumps({'gpt': tags}), signal='pain', reason_code='other',
                channel='naver_cafe')


def test_soft_targets():
    from app.model.train import build_targets
    r = row(source='agreed')
    tags = json.loads(r['tags_json'])
    tags['sem']['feel'] = 1  # merged tag differs from GPT
    r['tags_json'] = json.dumps(tags)
    t = build_targets([r, row(1)], {'0': {'probs': dict.fromkeys(rule.GRADE_FIELDS, .8),
                                          'reason_probs': {'other': 1}}})
    assert t.values['sem'][0, 0] == pytest.approx(.9)
    assert t.values['sem'][0, 1] == pytest.approx(.4)
    assert t.values['signal'][0].tolist() == [1, 0, 0, 0, 0]
    assert t.weights.tolist() == [1, 3]


def test_one_dim_doc_is_supporting_and_trained():
    from app.model.train import build_targets
    t = build_targets([row()], {})
    assert t.grades.tolist() == ['supporting']
    assert t.masks['signal'].tolist() == [True]
    assert t.masks['sem'].tolist() == [True]


@pytest.fixture(scope='module')
def synthetic():
    from app.model.train import build_targets
    rng = np.random.default_rng(42)
    n = 3000
    bits = rng.integers(0, 2, (n, 8))
    signal = rng.integers(0, 5, n)
    reason = rng.integers(0, 4, n)
    x = rng.normal(0, .15, (n, 1032)).astype('float32')
    x[:, :8] += (2 * bits - 1) * 8
    x[np.arange(n), 8 + signal] += 16
    x[np.arange(n), 13 + reason] += 16
    rows = []
    for i in range(n):
        r = row(i)
        tags = dict(anchor=bool(bits[i, 0]), sem=dict(zip(rule.SEM, bits[i, 1:7].tolist())),
                    situation=bool(bits[i, 7]))
        r.update(tags_json=json.dumps(tags), signal=['pain','unmet','workaround','delight','none'][signal[i]],
                 reason_code=['ad','no_needs','pure_criticism','other'][reason[i]],
                 channel=['naver_cafe','naver_blog','youtube','ppomppu','clien'][i % 5])
        rows.append(r)
    return x, build_targets(rows, {})


def test_ensemble_learns_synthetic(synthetic):
    from app.model.train import train_ensemble
    x, t = synthetic
    result = train_ensemble(x, t)
    assert len(result.members) == 4
    assert all(v['f1'] >= .9 for v in result.perHead.values()), result.perHead
    assert result.metrics['grade_accuracy'] >= .9
    assert len(result.metrics['members']) == 4
    splits = result.splits
    assert [len(splits[k]) for k in ('train', 'validation', 'calibration')] == [2400, 300, 300]
    assert not set(splits['train']) & set(splits['calibration'])
    pred = result.predict(x[:11])
    assert pred['std']['sem'].shape == (11, 6)
    assert np.all((pred['grade_disagreement'] >= 0) & (pred['grade_disagreement'] <= 1))


def test_temperature_reduces_ece():
    from app.model.calibrate import fit_temperature, ece
    logits = torch.full((1000, 1), 5.)
    y = torch.zeros_like(logits)
    y[:700] = 1
    temperature = fit_temperature(logits, y)
    assert temperature > 1
    assert ece(torch.sigmoid(logits / temperature), y) < ece(torch.sigmoid(logits), y) / 5


def test_head_min_samples():
    from app.model.train import build_targets, train_ensemble
    rows = [row(i, anchor=i < 18) for i in range(100)]
    t = build_targets(rows, {})
    x = np.random.default_rng(1).normal(size=(100, 1032)).astype('float32')
    result = train_ensemble(x, t, max_epochs=1)
    assert not result.perHead['signal']['trained']
    assert result.perHead['signal']['reason'] == 'insufficient_samples'
    for member in result.members:
        assert not member['heads.signal.weight'].any()


def test_seed_reproducible(synthetic):
    from app.model.train import train_member
    x, t = synthetic
    a = train_member(x, t, seed=7, bootstrap=True, linear=True, max_epochs=2)
    b = train_member(x, t, seed=7, bootstrap=True, linear=True, max_epochs=2)
    assert all(torch.equal(a[k], b[k]) for k in a)


def test_features_alignment_and_flags():
    from app.model.features import build_features
    docs = [dict(doc_id='a', channel='youtube', body='abc', is_snippet=True, jev_truncated=True)]
    x = build_features(docs, {'a': np.ones(1024)})
    assert x.shape == (1, 1032)
    np.testing.assert_array_equal(x[0, 1024:1029], [0, 0, 1, 0, 0])
    np.testing.assert_allclose(x[0, 1029:], [np.log1p(3), 1, 1])


def test_filters_preserve_alignment():
    from app.model.train import build_targets, train_ensemble
    rows = [row(i) for i in range(100)]
    rows[0].update(source='agreed', route='escalated:grade_mismatch')
    t = build_targets(rows, {})
    assert '0' not in t.doc_ids
    x = np.ones((99, 1032), dtype='float32')
    x[0, :1024] = 0
    result = train_ensemble(x, t, max_epochs=1)
    assert sum(map(len, result.splits.values())) == 98


def test_real_store_contracts(tmp_path):
    from app.model.features import build_features
    from app.model.train import build_targets
    from app.vectors.store import VectorStore
    from app.label.votes import VoteCache
    store = VectorStore(tmp_path / 'vectors')
    store.write_shard(['b', 'a'], np.stack([np.full(1024, 2), np.ones(1024)]), [False, False])
    docs = [dict(doc_id=i, source='clien', fetch_level='snippet', body='text') for i in ['a', 'missing', 'b']]
    x = build_features(docs, store)
    assert x[:, 0].tolist() == [1, 0, 2]
    assert x[:, 1028].tolist() == [1, 1, 1]
    assert x[:, 1030].tolist() == [1, 1, 1]
    cache = VoteCache(tmp_path / 'votes')
    cache.seed(['0'])
    cache.put('0', dict(probs=dict.fromkeys(rule.GRADE_FIELDS, .8), reason_probs={'other': 1}))
    t = build_targets([row(source='agreed')], cache)
    assert t.values['anchor'][0, 0] == pytest.approx(.9)


def test_split_strata_and_missing_labels(synthetic):
    from app.model.train import stratified_split, build_targets
    _, t = synthetic
    splits = stratified_split(t)
    assert len(set(np.concatenate(list(splits.values())))) == 3000
    for grade in set(t.grades):
        for channel in set(t.channels):
            mask = (t.grades == grade) & (t.channels == channel)
            for name, fraction in [('train', .8), ('validation', .1), ('calibration', .1)]:
                assert abs(mask[splits[name]].sum() - fraction * mask.sum()) <= 2
    r = row()
    r['signal'] = None
    missing = build_targets([r], {})
    assert not missing.masks['signal'].any()
