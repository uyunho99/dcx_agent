import unicodedata

import pytest
from pydantic import ValidationError

from app.keywords.models import Keyword
from app.keywords.normalize import BANNED, clean_generated, norm_key
from app.keywords.taxonomy import AXES, is_valid


def generated(kw, axis="physical", sub="sense"):
    return {"kw": kw, "axis": axis, "sub": sub}


def keyword(kw):
    return Keyword(id="k_r1_0007", kw=kw, axis="physical", sub="sense",
                   round=1, origin="llm", status="pending")


def test_normalize_merges_spacing_variants():
    passed, _ = clean_generated([generated("실외기 소음")], [keyword("실외기소음")], BANNED)
    assert passed == []


def test_drops_short_and_banned():
    passed, logs = clean_generated([generated("a"), generated("후기")], [], BANNED)
    assert passed == []
    assert len(logs) == 2


def test_unknown_sub_coerced_to_first():
    passed, logs = clean_generated([generated("실외기소음", sub="xxx")], [], BANNED)
    assert passed == [generated("실외기소음", sub="time")]
    assert len(logs) == 1


def test_custom_sub_allowed():
    item = generated("실외기소음", sub="custom:설치환경")
    assert clean_generated([item], [], BANNED) == ([item], [])


def test_norm_key_removes_unicode_whitespace_and_composes_before_lowercase():
    assert norm_key(" \t" + unicodedata.normalize("NFD", "실외기") + "\u00a0소\u2003음\nABC") == "실외기소음abc"


def test_batch_deduplicates_by_normalized_key_keeping_first():
    first = generated("실외기 소음")
    duplicate = generated(unicodedata.normalize("NFD", "실외기소음"), sub="body")
    passed, logs = clean_generated([first, duplicate, generated("AB"), generated("a b")], [], BANNED)
    assert passed == [first, generated("AB")]
    assert len(logs) == 2


def test_normalized_length_and_banned_keys():
    items = [generated(kw) for kw in [" \t", " A\u00a0", unicodedata.normalize("NFD", "가"), "후 기", " Re VIEW ", "가격 소음"]]
    passed, logs = clean_generated(items, [], BANNED | {"Review"})
    assert passed == [generated("가격 소음")]
    assert len(logs) == 5


def test_builtin_banned_words_apply_with_empty_additional_set():
    assert clean_generated([generated("후 기")], [], set())[0] == []


def test_unknown_axis_dropped_and_logged():
    passed, logs = clean_generated([generated("실외기소음", axis="unknown")], [], BANNED)
    assert passed == []
    assert len(logs) == 1


@pytest.mark.parametrize("axis", ["physical", "psychological", "behavioral"])
def test_axis_specific_fallback_and_custom_sub(axis):
    passed, logs = clean_generated([generated("실외기소음", axis, "xxx")], [], BANNED)
    assert passed[0]["sub"] == AXES[axis][0]
    assert len(logs) == 1
    assert is_valid(axis, "custom:설치환경")


def test_taxonomy_exact_codes():
    assert AXES == {
        "physical": ["time", "space", "social", "sense", "body", "product_physical"],
        "psychological": ["emotion", "goal_ladder", "perceived_risk", "belief", "identity"],
        "behavioral": ["trigger", "constraint", "coping", "info_search", "switching"],
    }
    assert all(is_valid(axis, sub) for axis, subs in AXES.items() for sub in subs)
    assert not is_valid("unknown", "custom:설치환경")
    assert not is_valid("physical", "emotion")
    assert not is_valid("physical", "custom:")


def test_clean_generated_preserves_inputs_and_is_deterministic():
    item = generated("실외기 소음", sub="xxx")
    first = clean_generated([item], [], BANNED)
    assert first == clean_generated([item], [], BANNED)
    assert item == generated("실외기 소음", sub="xxx")
    assert first[0][0] is not item


def test_banned_exact_values():
    assert BANNED == {"후기", "비교", "추천", "가격", "장단점", "선택", "고민", "리뷰", "평가", "만족", "불만"}


def test_keyword_fields_and_independent_defaults():
    first = keyword("실외기소음")
    second = keyword("설치환경")
    first.badges.append("llm_only")
    assert second.badges == []
    assert first.reject is None
    assert first.volume is None
    data = first.model_dump()
    data.update(status="rejected", reject={"tags": ["common"], "note": "너무 흔함"},
                volume={"monthly": 1240, "source": "searchad", "at": "2026-09-28"})
    assert Keyword(**data).model_dump() == data
    assert set(data) == {"id", "kw", "axis", "sub", "round", "origin", "status", "reject", "volume", "badges"}


@pytest.mark.parametrize("field,value", [("axis", "other"), ("round", 0), ("round", 5), ("origin", "other"), ("status", "other")])
def test_keyword_rejects_invalid_enumerations_and_round(field, value):
    data = keyword("실외기소음").model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        Keyword(**data)
