from copy import deepcopy
from unittest.mock import Mock

import numpy as np
import pytest

from app.evidence.rerank import coverage, dpp_greedy, quality, select


DIMS = ('sense', 'feel', 'think', 'act', 'relate', 'outcome')


def pool(scores):
    ids = [f'd{i}' for i in range(len(scores))]
    candidates = [dict(doc_id=i, relevance=q, band='core') for i, q in zip(ids, scores)]
    tags = {i: dict(relevant=True, pain_point=None, unmet_need=None) for i in ids}
    vectors = dict(zip(ids, np.eye(len(ids))))
    docs = {i: dict(tagProbs={dim: 1. for dim in DIMS}, combo_rarity=None) for i in ids}
    return candidates, tags, vectors, docs


def test_quality_formula():
    assert quality(0.8, 0.5) == pytest.approx(0.92)
    assert quality(0.8, None) == 0.8
    assert quality(0.8, 0.5, w_r=0.6) == pytest.approx(1.04)


def test_dpp_avoids_duplicates():
    vectors = np.array([[2., 0.], [1., 0.], [3., 0.], [0., 2.]])
    assert dpp_greedy(np.array([1., .9, .8, .7]), vectors, 4) == [0, 3]


def short_dpp_pool():
    candidates, tags, vectors, docs = pool(np.linspace(1., .5, 12))
    distinct = np.random.default_rng(2).normal(size=(10, 3))
    matrix = np.vstack([distinct[0], distinct[0], distinct])
    vectors.update(zip(vectors, matrix))
    return candidates, tags, vectors, docs


def test_dpp_short_fills_non_duplicates():
    args = short_dpp_pool()
    candidates, _, vectors, _ = args
    initial = dpp_greedy(
        np.array([row['relevance'] for row in candidates]),
        np.array(list(vectors.values())), 10,
    )
    assert len(initial) == 9
    result = select(*args)
    ids = [row['doc_id'] for row in result.rows]
    assert len(ids) == 10
    assert len(set(ids) & {'d0', 'd1', 'd2'}) == 1
    assert ids[:len(initial)] == [candidates[i]['doc_id'] for i in initial]
    assert ids[-1] == 'd4'
    assert [row['rank'] for row in result.rows] == list(range(1, 11))


def test_dpp_short_no_fill_when_only_duplicates():
    candidates, tags, vectors, docs = pool([1., .9, .8, .7, .6])
    vectors = {doc_id: np.array([2., 1.]) for doc_id in vectors}
    result = select(candidates, tags, vectors, docs)
    assert [row['doc_id'] for row in result.rows] == ['d0']
    assert result.dpp_fill == 0


def test_selection_reports_dpp_fill():
    assert select(*short_dpp_pool()).dpp_fill == 1
    assert select(*pool([1., .9])).dpp_fill == 0
    assert select(*short_dpp_pool(), k=0).dpp_fill == 0
    assert select([], {}, {}, {}).dpp_fill == 0


def test_dpp_nonpositive_pivot_and_small_quality_scale():
    # The exact requested kernel can be indefinite; do not repair its spectrum.
    angles = np.array([-.2, 0., .2])
    vectors = np.column_stack([np.cos(angles), np.sin(angles)])
    q = np.array([1., .9, .8])
    assert dpp_greedy(q, vectors, 3) == [0, 2]
    assert dpp_greedy(q * 1e-10, vectors, 3) == [0, 2]


@pytest.mark.parametrize('q,v,sigma', [
    ([1.], [[0., 0.]], .3),
    ([1.], [[1., 0.]], 0.),
    ([1.], [[1., 0.]], float('nan')),
    ([float('nan')], [[1., 0.]], .3),
    ([1.], [[float('inf'), 0.]], .3),
    ([1., 2.], [[1., 0.]], .3),
])
def test_dpp_rejects_invalid_inputs(q, v, sigma):
    with pytest.raises(ValueError):
        dpp_greedy(np.array(q), np.array(v), 2, sigma)


@pytest.mark.parametrize('seed', range(5))
def test_dpp_matches_bruteforce_small(seed):
    rng = np.random.default_rng(seed)
    vectors = rng.normal(size=(8, 12))
    q = rng.uniform(.4, 1.2, 8)
    unit = vectors / np.linalg.norm(vectors, axis=1)[:, None]
    kernel = q[:, None] * np.exp(-(1 - unit @ unit.T) ** 2 / .3 ** 2) * q[None, :]
    expected = []
    previous = 0.
    for _ in range(3):
        gains = {}
        for i in set(range(8)) - set(expected):
            indices = expected + [i]
            sign, logdet = np.linalg.slogdet(kernel[np.ix_(indices, indices)])
            gains[i] = logdet - previous if sign > 0 else -np.inf
        chosen = max(gains, key=gains.get)
        previous += gains[chosen]
        expected.append(chosen)
    assert dpp_greedy(q, vectors, 3) == expected


def test_known_not_penalized():
    candidates, tags, vectors, docs = pool([.8, .7])
    docs['d0']['combo_rarity'] = .5
    before = select(candidates, tags, vectors, docs)
    tags['d0']['known_match'] = 'ki-1'
    assert select(candidates, tags, vectors, docs) == before
    assert before.rows[0]['quality'] == pytest.approx(.92)


@pytest.mark.parametrize('improves', [True, False])
def test_coverage_supplement_once(improves):
    candidates, tags, vectors, docs = pool([.9, .8, 1.])
    for doc in docs.values():
        doc['tagProbs'] = dict.fromkeys(DIMS[:3], .5)
    if improves:
        docs['d2']['tagProbs'] = dict.fromkeys(DIMS[3:], .5)
    supplement = Mock(return_value=[candidates[2], candidates[0]])
    result = select(candidates[:2], tags, vectors, docs, supplement=supplement)
    supplement.assert_called_once_with(list(DIMS[3:]), 15)
    assert result.coverage_supplements == 1
    assert result.coverage == (6 if improves else 3)
    assert result.missing_dims == ([] if improves else list(DIMS[3:]))
    assert len(result.rows) == 3
    assert result.rows[0]['doc_id'] == 'd2'


def test_no_supplement_at_four_dims():
    candidates, tags, vectors, docs = pool([.9])
    docs['d0']['tagProbs'] = dict.fromkeys(DIMS[:4], .5)
    supplement = Mock()
    result = select(candidates, tags, vectors, docs, supplement=supplement)
    supplement.assert_not_called()
    assert result.coverage_supplements == 0
    assert result.coverage == 4


@pytest.mark.parametrize('already_rare, swaps', [(0, 2), (1, 1), (2, 0)])
def test_rare_fallback_only_when_below_two(already_rare, swaps):
    candidates, tags, vectors, docs = pool([1., .9, .8, .5, .4])
    for i in list(range(already_rare)) + [3, 4]:
        candidates[i]['band'] = 'edge'
        tags[f'd{i}']['unmet_need'] = 'A need'
    result = select(candidates, tags, vectors, docs, k=3)
    expected = {0, 1, 2} if swaps == 0 else ({0, 1, 3} if swaps == 1 else {0, 3, 4})
    assert {r['doc_id'] for r in result.rows} == {f'd{i}' for i in expected}
    assert result.rare_fallback == swaps
    assert sum(row['rare'] for row in result.rows) == 2
    assert [row['rank'] for row in result.rows] == [1, 2, 3]


@pytest.mark.parametrize('band,relevant,pain,need,rare', [
    ('edge', True, {'text': 'pain'}, None, True),
    ('edge', True, None, 'need', True),
    ('edge', True, None, None, False),
    ('edge', False, 'pain', 'need', False),
    ('core', True, 'pain', 'need', False),
])
def test_rare_definition(band, relevant, pain, need, rare):
    candidates, tags, vectors, docs = pool([1.])
    candidates[0]['band'] = band
    tags['d0'].update(relevant=relevant, pain_point=pain, unmet_need=need)
    result = select(candidates, tags, vectors, docs)
    assert [r['rare'] for r in result.rows] == ([rare] if relevant else [])


def test_tag_probs_null_counts_zero():
    assert coverage(['null', 'absent'], {'null': None}) == 0
    assert coverage(['a', 'b'], {
        'a': dict(sense=.5, feel=.499, anchor=1., situation=1., Sense=1.),
        'b': dict(sense=.9, outcome=.5),
    }) == 2
    candidates, tags, vectors, docs = pool([1.])
    docs['d0']['tagProbs'] = None
    result = select(candidates, tags, vectors, docs)
    assert result.coverage == 0
    assert result.missing_dims == list(DIMS)


def test_empty_zero_budget_and_untagged():
    assert dpp_greedy(np.array([]), np.empty((0, 2)), 10) == []
    assert dpp_greedy(np.zeros(2), np.eye(2), 10) == []
    candidates, tags, vectors, docs = pool([1., .9])
    assert select(candidates, tags, vectors, docs, k=0).rows == []
    assert select([], {}, {}, {}).rows == []
    del tags['d0']
    tags['d1']['relevant'] = False
    assert select(candidates, tags, vectors, docs).rows == []


def test_default_ten_and_inputs_unchanged():
    args = pool(np.linspace(1., .1, 12))
    before = deepcopy(args)
    result = select(*args)
    assert len(result.rows) == 10
    assert args[0] == before[0] and args[1] == before[1] and args[3] == before[3]
    for key in args[2]:
        np.testing.assert_array_equal(args[2][key], before[2][key])


def test_coverage_recomputed_after_rare_swap():
    candidates, tags, vectors, docs = pool([1., .9, .5])
    docs['d0']['tagProbs'] = dict.fromkeys(DIMS[:4], 1.)
    docs['d1']['tagProbs'] = dict.fromkeys(DIMS[4:], 1.)
    docs['d2']['tagProbs'] = None
    candidates[2]['band'] = 'edge'
    tags['d2']['pain_point'] = 'pain'
    result = select(candidates, tags, vectors, docs, k=2)
    assert result.rare_fallback == 1
    assert result.coverage == 4
    assert result.missing_dims == list(DIMS[4:])
