"""Offline L3 contracts; perf is opt-in with -m perf."""
from time import perf_counter

import numpy as np
import pytest

from app.segment import l3, params
from app.segment.inputs import load_input
from tests.fixtures.segment_synth import make_segment_session


def persona(sizes=(40, 40, 40), dim=16):
    rng = np.random.default_rng(params.SEED)
    ids, tokens, vectors = [], {}, {}
    for group, size in enumerate(sizes):
        for _ in range(size):
            key = str(len(ids))
            ids.append(key)
            tokens[key] = [f'w{group}_{j}' for j in range(20)]
            vector = rng.normal(0, .15, dim)
            vector[group % dim] += 1
            vectors[key] = (vector / np.linalg.norm(vector)).astype(np.float16)
    return ids, tokens, vectors


@pytest.fixture(scope='module')
def real_result():
    return l3.contexts(*persona())


def test_topic_count_by_cv(real_result):
    assert set(real_result.scan) == set(range(2, 11))
    assert max(real_result.scan, key=lambda k: real_result.scan[k]['cv']) == 3
    assert len(real_result.centroids) == 3
    assert all(np.isfinite(list(row.values())).all() for row in real_result.scan.values())
    assert all(set(row) == {'cv', 'perplexity'} for row in real_result.scan.values())


def test_session_fixture(data_dir):
    session = make_segment_session(data_dir, clusters=1, personas=(1,), contexts=(3,))
    data = load_input(session.sid, session.version)
    result = l3.contexts(data.ids, data.tokens, dict(zip(data.ids, data.vectors)))
    expected = session.expected['assignments']
    groups = {}
    for doc, context in result.assign.items():
        groups.setdefault(context, set()).add(expected[doc]['context'])
    assert len(groups) == 3 and all(len(group) == 1 for group in groups.values())


def controlled(monkeypatch, sizes, best=6, unused=()):
    """Instrument selection/boundaries independently of statistical recovery."""
    calls = []
    class Model:
        def __init__(self, *, corpus, id2word, num_topics, passes, random_state):
            assert passes == 10 and random_state == params.SEED
            self.num_topics = num_topics
            calls.append(num_topics)
        def log_perplexity(self, corpus):
            return -2.
        def get_document_topics(self, bow, minimum_probability):
            assert minimum_probability == 0
            index = self.index
            self.index += 1
            active = [k for k in range(self.num_topics) if k not in unused]
            group = int(np.searchsorted(np.cumsum(sizes), index, side='right'))
            winner = active[group % len(active)]
            return [(k, .9 if k == winner else .1 / (self.num_topics - 1)) for k in range(self.num_topics)]
        index = 0
        def show_topic(self, topicid, topn):
            return [(f'topic{topicid}', 1.)]
    class Coherence:
        def __init__(self, *, model, texts, dictionary, coherence, processes):
            assert coherence == 'c_v' and processes == 1
            self.k = model.num_topics
        def get_coherence(self):
            return 1. if self.k == best else .2
    monkeypatch.setattr(l3, 'LdaModel', Model)
    monkeypatch.setattr(l3, 'CoherenceModel', Coherence)
    return calls


def test_granularity_warning(monkeypatch):
    calls = controlled(monkeypatch, [10] * 6)
    result = l3.contexts(*persona([10] * 6))
    assert calls == list(range(2, 11))
    assert len(result.centroids) == 6
    assert result.flags == ['granularity_exceeded']


def test_assignment_argmax_theta(real_result):
    assert set(real_result.assign) == set(persona()[0])
    for doc, posterior in real_result.theta_all.items():
        assert sum(posterior) == pytest.approx(1., abs=1e-6)
        assert real_result.assign[doc] == real_result.topic_ids[int(np.argmax(posterior))]
        assert real_result.theta[doc] == max(posterior)


@pytest.mark.parametrize('size,empty_dictionary', [(29, False), (30, True)])
def test_few_docs_or_empty_dictionary_single_context(monkeypatch, size, empty_dictionary):
    def forbidden(**kwargs):
        pytest.fail('LDA must not run')
    monkeypatch.setattr(l3, 'LdaModel', forbidden)
    ids, tokens, vectors = persona([size])
    if empty_dictionary:
        tokens = {doc: ['common', f'unique{doc}'] for doc in ids}
    result = l3.contexts(ids, tokens, vectors)
    assert set(result.assign.values()) == {'C1'}
    assert result.flags == ['few_docs'] and result.scan == {}
    assert all(value == 1 for value in result.theta.values())


def test_centroid_and_bands(monkeypatch):
    controlled(monkeypatch, [100] * 3, best=3)
    args = persona([100] * 3)
    result = l3.contexts(*args)
    for context, centroid in result.centroids.items():
        ids = [doc for doc in args[0] if result.assign[doc] == context]
        matrix = np.asarray([args[2][doc] for doc in ids], dtype=np.float32)
        expected = matrix.mean(axis=0)
        expected /= np.linalg.norm(expected)
        np.testing.assert_allclose(centroid, expected, atol=1e-6)
        distances = 1 - matrix @ expected / np.linalg.norm(matrix, axis=1)
        np.testing.assert_allclose([result.dist[doc] for doc in ids], distances, atol=1e-6)
        assert [sum(result.band[doc] == band for doc in ids) for band in ('core', 'fringe', 'edge')] == [50, 40, 10]


@pytest.mark.parametrize('minority,low,flagged', [(14, -.5, True), (15, -.5, False), (14, .1, False)])
def test_counter_flag(monkeypatch, minority, low, flagged):
    sizes = [minority, 100 - minority]
    controlled(monkeypatch, sizes, best=2)
    args = persona(sizes)
    sentiments = {doc: low if int(doc) < minority else .2 for doc in args[0]}
    result = l3.contexts(*args, sentiment_by_id=sentiments)
    assert ('counter_context' in result.context_flags['C1']) is flagged
    assert ('counter_context' in result.flags) is flagged
    assert result.context_flags['C2'] == []
    assert l3.contexts(*args).context_flags == {'C1': [], 'C2': []}


def test_deterministic(real_result):
    second = l3.contexts(*persona())
    assert second.assign == real_result.assign
    assert second.theta_all == real_result.theta_all
    assert second.scan == real_result.scan


def test_empty_topics_removed(monkeypatch):
    controlled(monkeypatch, [20, 20], best=4, unused=(0, 2))
    result = l3.contexts(*persona([20, 20]))
    assert set(result.assign.values()) == {'C1', 'C2'}
    assert set(result.topic_words) == set(result.centroids) == {'C1', 'C2'}
    assert result.topic_ids == [None, 'C1', None, 'C2']
    assert all(len(row) == 4 for row in result.theta_all.values())
    assert all(value == .9 for value in result.theta.values())


def test_empty_persona():
    result = l3.contexts([], {}, {})
    assert result.assign == result.centroids == result.theta_all == {}
    assert result.flags == ['few_docs']


@pytest.mark.perf
def test_l3_perf(record_property):
    args = persona([6667, 6667, 6666], dim=1024)
    start = perf_counter()
    result = l3.contexts(*args)
    elapsed = perf_counter() - start
    record_property('l3_20000_seconds', elapsed)
    print(f'\nl3_20000_seconds={elapsed:.3f}; contexts={len(result.centroids)}')
    assert len(result.assign) == 20000 and len(result.scan) == 9


def test_cv_tie_prefers_smaller_k(monkeypatch):
    controlled(monkeypatch, [20, 20], best=99)
    result = l3.contexts(*persona([20, 20]))
    assert len(result.topic_ids) == 2


def test_counter_exact_gap(monkeypatch):
    controlled(monkeypatch, [10, 90], best=2)
    args = persona([10, 90])
    # Sparse observations: one minority and four majority observations give
    # an exactly representable mean gap after scaling by 1/4.
    sentiment = {args[0][0]: 0., **{doc: .25 for doc in args[0][10:14]}}
    result = l3.contexts(*args, sentiment_by_id=sentiment)
    assert result.context_flags['C1'] == ['counter_context']
