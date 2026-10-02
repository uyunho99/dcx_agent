"""Offline L1 contracts, including bounded float16 streaming allocations."""
import json
import tracemalloc

import numpy as np
import pytest
from sklearn.metrics import adjusted_rand_score
from threadpoolctl import threadpool_limits

from app.segment import l1, params
from app.segment.ctfidf import ctfidf
from app.segment.inputs import load_input
from tests.fixtures.segment_synth import make_segment_session


@pytest.fixture(autouse=True)
def single_thread():
    with threadpool_limits(limits=1):
        yield


def vectors_for(sizes, dim=64):
    rng = np.random.default_rng(params.SEED)
    truth = np.repeat(np.arange(len(sizes)), sizes)
    values = rng.normal(0, .015, (len(truth), dim)).astype(np.float32)
    values[np.arange(len(truth)), truth] += 1
    values /= np.linalg.norm(values, axis=1, keepdims=True)
    return values.astype(np.float16), truth


def test_suggest_k_finds_five(data_dir):
    session = make_segment_session(data_dir, docs_per_context=8)
    values = load_input(session.sid, session.version).vectors
    result = l1.suggest_k(values, np.random.default_rng(params.SEED))
    assert result['k'] == session.expected['k'] == 5
    assert set(result['silhouette']) == set(range(3, 9))
    assert set(result['inertia']) == set(range(3, 9))
    assert all(np.isfinite(v) for v in result['silhouette'].values())
    assert all(a >= b for a, b in zip(result['inertia'].values(), list(result['inertia'].values())[1:]))
    from scipy.cluster.hierarchy import linkage
    np.testing.assert_allclose(result['dendrogram'], linkage(values.astype(np.float32), method='ward')[-30:])
    assert result == l1.suggest_k(values, np.random.default_rng(params.SEED))
    json.dumps(result)


def test_ward_uses_sample_cap(monkeypatch):
    values, _ = vectors_for([6000] * 5, dim=8)
    seen = []

    def ward(sample, method):
        assert method == 'ward'
        assert sample.shape == (20000, 8) and sample.dtype == np.float32
        seen.append(sample.copy())
        return np.zeros((len(sample) - 1, 4))

    def silhouette(sample, labels):
        np.testing.assert_array_equal(sample, seen[0])
        return .5

    # Instrument the expensive quadratic routines; the small integration above
    # exercises real Ward/silhouette and checks the exact merge summary.
    monkeypatch.setattr(l1, 'linkage', ward)
    monkeypatch.setattr(l1, 'silhouette_score', silhouette)
    result = l1.suggest_k(values, np.random.default_rng(params.SEED))
    assert result['sample'] == 20000
    assert result['k'] == 3  # deterministic lower-k tie break
    assert len(result['dendrogram']) == 30
    assert not np.array_equal(seen[0], values[:20000])


def test_cluster_deterministic():
    values, truth = vectors_for([100, 200, 300, 400, 500])
    before = values.copy()
    a, ca = l1.cluster(values, 5, np.random.default_rng(params.SEED))
    b, cb = l1.cluster(values, 5, np.random.default_rng(params.SEED))
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(ca, cb)
    np.testing.assert_array_equal(values, before)
    assert adjusted_rand_score(truth, a) == 1


def test_minibatch_above_threshold(monkeypatch):
    monkeypatch.setattr(params, 'KMEANS_FULL_MAX', 100)
    values, truth = vectors_for([2000] * 5)
    original_fit = l1.MiniBatchKMeans.partial_fit
    original_predict = l1.MiniBatchKMeans.predict
    fitted, predicted = [], []

    def partial_fit(self, batch, *args, **kwargs):
        assert batch.dtype == np.float32 and len(batch) <= params.MINIBATCH
        assert self.n_init == 5 and self.batch_size == 4096
        fitted.append(len(batch))
        return original_fit(self, batch, *args, **kwargs)

    def predict(self, batch, *args, **kwargs):
        assert batch.dtype == np.float32 and len(batch) <= params.MINIBATCH
        predicted.append(len(batch))
        return original_predict(self, batch, *args, **kwargs)

    monkeypatch.setattr(l1.MiniBatchKMeans, 'partial_fit', partial_fit)
    monkeypatch.setattr(l1.MiniBatchKMeans, 'predict', predict)
    a, ca = l1.cluster(values, 5, np.random.default_rng(params.SEED))
    assert fitted == [4096, 4096, 1808]
    assert predicted == [4096, 4096, 1808]
    assert adjusted_rand_score(truth, a) == 1
    b, cb = l1.cluster(values, 5, np.random.default_rng(params.SEED))
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(ca, cb)


def test_large_input_streams(record_property):
    values, truth = vectors_for([40000] * 5)
    tracemalloc.start()
    try:
        labels, centers = l1.cluster(values, 5, np.random.default_rng(params.SEED))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    record_property('tracemalloc_peak_bytes', peak)
    print(f'\ntracemalloc_peak_bytes={peak}')
    assert len(np.unique(labels)) == 5
    assert centers.shape == (5, 64)
    assert adjusted_rand_score(truth, labels) == 1
    assert peak < values.size * 4  # no full float32 materialization


def test_ids_ordered_by_size():
    values, _ = vectors_for([150, 400, 80, 250, 120])
    labels, centers = l1.cluster(values, 5, np.random.default_rng(params.SEED))
    assert np.bincount(labels).tolist() == [400, 250, 150, 120, 80]
    for i, center in enumerate(centers):
        np.testing.assert_allclose(center, values[labels == i].astype(np.float32).mean(axis=0), atol=3e-6)


def test_ctfidf_distinguishes():
    unique = {f'CL{i}': [f'명사{i}_{j}' for j in range(10)] for i in range(5)}
    groups = {key: [words + ['에어컨'] for _ in range(20)] for key, words in unique.items()}
    result = ctfidf(groups, params.CTFIDF_TOP)
    for key, words in result.items():
        assert len(words) == 10
        assert len(set(words) & set(unique[key])) >= 7
        assert '에어컨' not in words
    assert result == ctfidf(dict(reversed(list(groups.items()))), params.CTFIDF_TOP)


def test_ctfidf_empty_and_ties():
    assert ctfidf({}, 10) == {}
    assert ctfidf({'empty': [[], []], 'a': [['zz', 'aa']]}, 10) == {'empty': [], 'a': ['aa', 'zz']}
    assert ctfidf({'a': [['word']]}, 0) == {'a': []}
    with pytest.raises(ValueError):
        ctfidf({'a': []}, -1)


@pytest.mark.parametrize('values,k', [(np.empty((0, 4), dtype=np.float16), 3),
                                     (np.ones((2, 4), dtype=np.float16), 3)])
def test_invalid_cluster_sizes(values, k):
    with pytest.raises(ValueError):
        l1.cluster(values, k, np.random.default_rng(params.SEED))


def test_suggest_small_input():
    values, _ = vectors_for([2, 2])
    result = l1.suggest_k(values, np.random.default_rng(params.SEED))
    assert list(result['silhouette']) == [3]
    assert result['sample'] == 4
    with pytest.raises(ValueError):
        l1.suggest_k(values[:3], np.random.default_rng(params.SEED))


def test_ctfidf_uses_corpus_term_frequency():
    # Equal document frequencies, unequal corpus TF: class-based IDF must
    # penalize yy enough that zz wins in class a despite its lower local count.
    groups = {'a': [['yy'] * 4 + ['zz'] * 3],
              'b': [['yy'] * 100 + ['zz']]}
    assert ctfidf(groups, 2)['a'] == ['zz', 'yy']
