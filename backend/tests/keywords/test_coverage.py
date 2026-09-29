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
    assert compute([], [], None).m7 == 0
    assert compute([('zero', 0)], [], None).m1 is None
