import math

import pytest

from app.keywords.coverage import compute, js_distance
from app.keywords.models import Keyword


def keyword(text, monthly=None, axis='physical'):
    return Keyword(id=text, kw=text, axis=axis, sub='test', round=1,
                   origin='llm', volume={'monthly': monthly})


@pytest.fixture
def sample():
    return ([('에어컨 소음', 100), ('에어컨 냄새', 50), ('실외기', 30), ('리모컨', 20)],
            [keyword('소음', 900), keyword('실외기', 400), keyword('결로', 5)])


def test_m1_volume_weighted(sample):
    assert compute(*sample, None).m1 == pytest.approx(130 / 200)


def test_m2_deciles_len_10(sample):
    result = compute(*sample, None)
    assert len(result.m2) == 10
    assert sum(value is None for value in result.m2) == 6
    human = [(f'q{i:02}', 100 - i) for i in range(20)]
    assert compute(human, [keyword('q00')], None).m2 == [100 / 199] + [0.0] * 9


def test_js_identical_zero_disjoint_one():
    assert js_distance({'a': 2, 'b': 1}, {'a': 4, 'b': 2}) == 0.0
    assert js_distance({'a': 1}, {'b': 1}) == 1.0
    assert js_distance({'a': 1}, {'a': 1, 'b': 1}) == pytest.approx(math.sqrt(0.31127812445913283))


def test_m7_llm_only(sample):
    result = compute(*sample, None)
    assert result.m7 == pytest.approx(1 / 3)
    assert result.llm_only_ids == ['결로']


def test_missing_top_sorted_by_volume(sample):
    assert compute(*sample, None).missing_top == [('에어컨 냄새', 50), ('리모컨', 20)]
    assert compute([(str(i), i) for i in range(30)], [], None).missing_top == [(str(i), i) for i in range(29, 9, -1)]


def test_m6_none_without_axes(sample):
    assert compute(*sample, None).m6 is None


def test_m6_axis_counts(sample):
    human, llm = sample
    assert compute(human, llm, {q: 'physical' for q, _ in human}).m6 == 0
    assert compute(human, llm, {q: 'behavioral' for q, _ in human}).m6 == 1


def test_normalized_bidirectional_match_and_purity():
    llm = [keyword('a B'), keyword('에어컨 소음', 0)]
    before = [kw.model_dump() for kw in llm]
    result = compute([('AB C', 10), ('소 음', 20)], llm, None)
    assert result.m1 == 1
    assert result.m7 == 0
    assert [kw.model_dump() for kw in llm] == before


def test_empty_and_unknown_volume():
    result = compute([], [keyword('unknown'), keyword('low', 5)], None)
    assert result.m1 is None
    assert result.m2 == [None] * 10
    assert result.m6 is None
    assert result.m7 == 0.5
    assert compute([], [], None).m7 is None
    assert compute([('zero', 0)], [], None).m1 is None


@pytest.mark.parametrize('volume', [None, {}, {'monthly': None, 'source': 'unconnected'}])
def test_m7_none_without_known_volume(volume):
    unknown = keyword('unknown')
    unknown.volume = volume
    result = compute([('human', 100)], [unknown], None)
    assert result.m7 is None
    assert result.llm_only_ids == []


def test_m7_known_zero_volume_is_available():
    assert compute([], [keyword('zero', 0)], None).m7 == 1.0


def test_rank_weighting_m1():
    human = [('alpha', 1), ('beta', 2), ('gamma', 4)]
    assert compute(human, [keyword('alpha'), keyword('gamma')], weighting='rank').m1 == pytest.approx(
        (1 + 0.25) / (1 + 0.5 + 0.25)
    )


def test_rank_bands_three_with_empty_band_none():
    human = [('alpha', 1), ('beta', 3), ('gamma', 7), ('delta', 10)]
    result = compute(human, [keyword('alpha'), keyword('delta')], weighting='rank')
    assert result.m2 is None
    assert result.m2_bands == [
        {'label': '1~3위', 'value': pytest.approx(1 / (1 + 1 / 3))},
        {'label': '4~6위', 'value': None},
        {'label': '7~10위', 'value': pytest.approx(0.1 / (1 / 7 + 0.1))},
    ]
    middle = compute([('alpha', 4), ('beta', 6)], [keyword('alpha')], weighting='rank')
    assert middle.m2_bands[1]['value'] == pytest.approx(0.25 / (0.25 + 1 / 6))


def test_rank_mode_m7_none_with_reason():
    result = compute([('human', 1)], [keyword('low', 5), keyword('zero', 0)], weighting='rank')
    assert result.m7 is None
    assert result.m7_reason == 'no_volume'
    assert result.llm_only_ids == []


def test_rank_missing_top_sorted_by_rank_limit_20():
    human = [(f'q{i:02}', rank) for i, rank in enumerate(list(range(10, 0, -1)) * 3)]
    result = compute(human, [keyword('q09')], weighting='rank')
    expected = sorted((row for row in human if row[0] != 'q09'), key=lambda row: row[1])[:20]
    assert result.missing_top == expected
    assert len(result.missing_top) == 20


def test_volume_mode_rank_fields_are_none(sample):
    for result in (compute(*sample), compute(*sample, weighting='volume')):
        assert result.m2_bands is None
        assert result.m7_reason is None
        assert result.m1 == pytest.approx(130 / 200)


def test_rank_empty_and_axis_counts(sample):
    empty = compute([], [], weighting='rank')
    assert empty.m1 is None
    assert empty.m2 is None
    assert [band['value'] for band in empty.m2_bands] == [None] * 3
    assert empty.m6 is None
    assert empty.m7 is None
    assert empty.m7_reason == 'no_volume'
    human, llm = sample
    ranks = [(query, rank) for rank, (query, _) in enumerate(human, 1)]
    before = [kw.model_dump() for kw in llm]
    assert compute(ranks, llm, {q: 'physical' for q, _ in ranks}, weighting='rank').m6 == 0
    assert compute(ranks, llm, {q: 'behavioral' for q, _ in ranks}, weighting='rank').m6 == 1
    assert [kw.model_dump() for kw in llm] == before


@pytest.mark.parametrize('query,word', [('에어컨 소음', '소음'), ('에어컨추천', '추천'),
                                      ('에어컨 소음', '소음원인')])
def test_rank_product_filter_and_partial_matching(query, word):
    human = [(' 에 어 컨 ', 1), (query, 2)]
    result = compute(human, [keyword(word)], {query: 'physical'}, weighting='rank', bk='에어컨')
    assert result.m1 == 1
    assert result.missing_top == []
    assert result.m2_bands[0]['value'] == 1
    assert result.m6 == 0
    assert len(human) == 2


def test_rank_only_product_has_no_human_metrics():
    result = compute([('에어컨', 1)], [keyword('소음')], weighting='rank', bk='에어컨')
    assert result.m1 is None and result.m6 is None
    assert result.missing_top == []
    assert all(band['value'] is None for band in result.m2_bands)


def test_volume_ignores_product_context():
    human = [('에어컨', 100), ('에어컨 소음', 50)]
    llm = [keyword('소음원인', 0)]
    assert compute(human, llm, bk='에어컨') == compute(human, llm)
    assert compute(human, llm, bk='에어컨').m1 == 0
