"""Deterministic, offline quality metric contracts."""
import math

import numpy as np
import pytest
from sklearn.metrics import adjusted_rand_score, silhouette_samples
from threadpoolctl import threadpool_limits

from app.segment import l1, params, quality


def test_cohesion_is_mean_document_centroid_cosine():
    vectors = np.array([[2, 0], [0, 3]], dtype=np.float16)
    assert quality.cohesion(vectors, np.array([4, 0])) == pytest.approx(.5)
    normalized = np.eye(2, dtype=np.float16)
    assert quality.cohesion(normalized) == pytest.approx(1 / math.sqrt(2))
    assert quality.cohesion(np.array([[1, 0], [-1, 0]])) == 0
    assert quality.cohesion(np.empty((0, 2))) is None


def test_boundary_is_negative_silhouette_ratio():
    vectors = np.array([[1, 0], [1, .1], [0, 1], [.1, 1], [1, .2]], dtype=np.float16)
    labels = np.array([0, 0, 1, 1, 1])
    scores = silhouette_samples(vectors.astype(np.float32), labels, metric='cosine')
    assert quality.boundary(vectors, labels) == pytest.approx(np.mean(scores < 0))
    assert quality.boundary(vectors, labels, target_label=1) == pytest.approx(np.mean(scores[labels == 1] < 0))


def test_boundary_uses_sample(monkeypatch):
    n = params.WARD_SAMPLE + 500
    vectors = np.arange(n * 2, dtype=np.float32).reshape(n, 2)
    labels = np.arange(n) % 3
    seen = []

    def silhouette(sample, assigned, metric):
        assert len(sample) == params.WARD_SAMPLE == 20000
        assert sample.dtype == np.float32
        assert metric == 'cosine'
        rows = (sample[:, 0] / 2).astype(int)
        assert len(np.unique(rows)) == len(rows)
        np.testing.assert_array_equal(assigned, labels[rows])
        assert not np.array_equal(rows, np.arange(len(rows)))
        seen.append(rows)
        return np.where(assigned == 0, -.2, .2)

    monkeypatch.setattr(quality, 'silhouette_samples', silhouette)
    first = quality.boundary(vectors, labels)
    assert first == quality.boundary(vectors, labels)
    np.testing.assert_array_equal(seen[0], seen[1])


@pytest.mark.parametrize('labels', [[], [0], [0, 0], [0, 1]])
def test_boundary_undefined(labels):
    assert quality.boundary(np.ones((len(labels), 2)), np.array(labels)) is None


@pytest.mark.parametrize('level,repeats', [('L1', 5), ('L2', 3)])
def test_resample_ari_callback(level, repeats):
    labels = np.repeat([0, 1], 10)
    vectors = np.eye(2)[labels].astype(np.float16)
    calls, expected = [], []

    def recluster(indices, rng):
        assert len(indices) == 16
        assert len(np.unique(indices)) == 16
        assert isinstance(rng, np.random.Generator)
        calls.append(indices.copy())
        predicted = labels[indices].copy()
        predicted[0] = 1 - predicted[0]
        expected.append(adjusted_rand_score(labels[indices], predicted))
        return predicted

    score = quality.resample_ari(vectors, labels, level=level, recluster=recluster)
    assert len(calls) == repeats
    assert score == pytest.approx(np.mean(expected))
    original = calls.copy()
    quality.resample_ari(vectors, labels, level=level, recluster=recluster)
    for a, b in zip(original, calls[repeats:]):
        np.testing.assert_array_equal(a, b)
    assert not np.array_equal(original[0], original[1])


def test_resample_ari_l1_default(monkeypatch):
    labels = np.repeat([0, 1], 20)
    vectors = np.eye(2)[labels].astype(np.float16)
    real_cluster = l1.cluster
    calls = []

    def cluster(sample, k, rng):
        calls.append(len(sample))
        assert k == 2
        return real_cluster(sample, k, rng)

    monkeypatch.setattr(l1, 'cluster', cluster)
    with threadpool_limits(limits=1):
        assert quality.resample_ari(vectors, labels) == 1
    assert calls == [32] * 5


def test_resample_ari_validation():
    with pytest.raises(ValueError, match='recluster'):
        quality.resample_ari(np.eye(3), np.arange(3), level='L2')
    with pytest.raises(ValueError, match='level'):
        quality.resample_ari(np.eye(3), np.arange(3), level='L3')
    assert quality.resample_ari(np.ones((1, 2)), np.array([0])) is None


def test_npmi_hand_calculated_three_word_corpus():
    # df(a,b,c)=(3,2,2), pairs(ab,ac,bc)=(2,1,1), N=4.
    docs = [['a', 'a', 'b'], ['a', 'b', 'c'], ['a'], ['c']]
    expected = (math.log(.5 / (.75 * .5)) / -math.log(.5)
                + math.log(.25 / (.75 * .5)) / -math.log(.25)
                + 0) / 3
    assert quality.npmi(['a', 'b', 'c'], docs) == pytest.approx(expected)


def test_npmi_degenerate_and_top_ten():
    assert quality.npmi(['a', 'b'], [['a'], ['b']]) == -1
    assert quality.npmi(['a', 'b'], [['a', 'b']]) == 1
    assert quality.npmi(['a', 'missing'], [['a']]) == -1
    assert quality.npmi(['a'], [['a']]) is None
    assert quality.npmi(['a', 'b'], []) is None
    words = [str(i) for i in range(10)]
    assert quality.npmi(words + ['missing'], [words]) == 1
    assert quality.npmi(['a', 'a', 'b'], [['a'], ['b']]) == -1


@pytest.mark.parametrize('level,threshold', [('L1', .7), ('L2', .6)])
def test_badge_thresholds(level, threshold):
    assert quality.flags(cohesion=.6, boundary=.15, ari=threshold, level=level) == []
    assert quality.flags(cohesion=.599, boundary=.151, ari=threshold - .001, level=level) == [
        'low_cohesion', 'high_boundary', 'unstable']
    assert quality.flags(cohesion=None, boundary=None, ari=None, level=level) == []


def test_channel_distribution_uses_collection_source():
    docs = [{'source': 'youtube', 'judge_source': 'human'} for _ in range(8)]
    docs += [{'source': 'blog', 'judge_source': 'model'} for _ in range(2)]
    assert quality.channel_distribution(docs) == {'channels': {'youtube': .8, 'blog': .2}, 'channel_skew': True}
    docs[0]['source'] = 'blog'
    assert quality.channel_distribution(docs)['channel_skew'] is False
    assert quality.channel_distribution([]) == {'channels': {}, 'channel_skew': False}
    assert quality.channel_distribution([{'judge_source': 'human'}])['channels'] == {'': 1.0}
