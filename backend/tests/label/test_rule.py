from collections import Counter
from itertools import product
from random import Random

import pytest

from app.label.rule import GRADE_FIELDS, RULE_VERSION, SEM, grade, grade_probs


FIELDS = ("anchor", "sense", "feel", "think", "act", "relate", "outcome", "situation")
EXAMPLE = dict(zip(FIELDS, (0.95, 0.10, 0.90, 0.20, 0.85, 0.05, 0.30, 0.80)))


def test_rule_contract():
    assert SEM == ("sense", "feel", "think", "act", "relate", "outcome")
    assert GRADE_FIELDS == FIELDS
    assert RULE_VERSION == "r1"


@pytest.mark.parametrize(
    "text,values,expected",
    [
        ("새벽에 애 깨워서 분유 타는데 온도 맞추느라 매번 끓였다 식혀요", (1, 1, 0, 1, 1, 1, 0, 1), "core"),
        ("새벽에 쓰는데 좀 시끄럽긴 하네요", (1, 1, 0, 0, 0, 0, 0, 1), "supporting"),
        ("새벽에 짜증나서 그냥 껐다", (1, 0, 1, 0, 1, 0, 0, 1), "core"),
        ("완전 좋아요 ㅎㅎ", (1, 0, 0, 0, 0, 0, 0, 0), "non"),
        ("그냥 쓰레기", (1, 0, 0, 0, 0, 0, 0, 0), "non"),
        ("역대급 특가 링크 ↓", (0, 0, 0, 0, 0, 0, 0, 0), "non"),
    ],
)
def test_plan_table(text, values, expected):
    assert grade(dict(zip(FIELDS, values))) == expected, text


def test_all_binary_tags_and_degenerate_probabilities():
    for values in product((0, 1), repeat=8):
        tags = dict(zip(FIELDS, values))
        count = sum(values[1:7])
        expected = "non"
        if values[0] and count >= 1:
            expected = "core" if count >= 2 and values[7] else "supporting"
        assert grade(tags) == expected
        assert grade_probs(tags) == {
            name: float(name == expected) for name in ("core", "supporting", "non")
        }


def test_grade_probs_sum_one():
    rng = Random(143)
    cases = [EXAMPLE, dict.fromkeys(FIELDS, 0.0), dict.fromkeys(FIELDS, 1.0)]
    cases.extend({field: rng.random() for field in FIELDS} for _ in range(100))
    for probabilities in cases:
        result = grade_probs(probabilities)
        assert set(result) == {"core", "supporting", "non"}
        assert all(0.0 <= value <= 1.0 for value in result.values())
        assert sum(result.values()) == pytest.approx(1.0, abs=1e-12)


def test_grade_probs_matches_montecarlo():
    rng = Random(143)
    samples = 100_000
    counts = Counter(
        grade({field: int(rng.random() < EXAMPLE[field]) for field in FIELDS})
        for _ in range(samples)
    )
    for name, probability in grade_probs(EXAMPLE).items():
        assert abs(probability - counts[name] / samples) < 0.01


def test_grade_probs_worked_example():
    result = grade_probs(EXAMPLE)
    assert result["core"] == pytest.approx(0.67, abs=0.01)
    assert result["supporting"] == pytest.approx(0.27, abs=0.01)
